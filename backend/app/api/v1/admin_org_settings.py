"""What the school decides about itself — readable and writable at last.

`org_settings` holds the name printed on every ведомость, the city under it,
the scheme new courses inherit, and the band boundaries every letter and «5» on
the platform is resolved through. All of it has been read-only since it was
introduced: the row was seeded by a migration and there has never been a route
that writes it.

Two consequences, and the second is the serious one.

Onboarding a school meant somebody opening the production database and running
an UPDATE to put their name on their own documents. And `validate_bands` — the
function that exists precisely to stop a band table that maps some scores to
nothing, or shows «3 (удовлетворительно)» to a student who is failing — had no
callers at all. It could not refuse anything, because nothing asked it.

Bands are shared, so editing them re-labels every live grade on the platform at
once: the same 84% that read «B» yesterday reads «A» today. That is what a
school changing its own scale means, and it is why the write is admin-only and
audited with the whole previous table kept. Documents do not move: a closed
ведомость and an issued certificate carry snapshots, and there are tests below
that say so in as many words.
"""

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_director
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.user import User
from app.schemas.org_settings import OrgSettingsResponse, OrgSettingsUpdate
from app.services.audit_service import log_action
from app.services.grading_scheme import (
    BAND_SCHEMES,
    get_org_settings,
    validate_bands,
    validate_scheme_threshold,
)

router = APIRouter(prefix="/admin/org-settings", tags=["admin-org-settings"])

AUDIT_RESOURCE = "org_settings"
AUDIT_ACTION = "org_settings_updated"


@router.get("", response_model=OrgSettingsResponse)
def read_org_settings(
    director: User = Depends(require_director),
    db: Session = Depends(get_db),
):
    """Everything the school has decided, as one row."""
    return get_org_settings(db)


@router.put("", response_model=OrgSettingsResponse)
def update_org_settings(
    data: OrgSettingsUpdate,
    request: Request,
    director: User = Depends(require_director),
    db: Session = Depends(get_db),
):
    """Change it, with the previous values kept.

    Fields left out are left alone: a director fixing a typo in the city should
    not have to resend the band table, and a request that omitted it would
    otherwise wipe the school's scale.

    The scheme and the pass line are validated **as a pair** (D8.1) — a
    five-point school whose pass line sits above 75 has an unreachable «3», and
    that can only be seen by looking at both. Bands are validated against the
    scheme they belong to, which is where the «3»-versus-threshold check lives.
    """
    settings = get_org_settings(db)
    payload = data.model_dump(exclude_unset=True)
    if not payload:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Nothing to update",
            context={"resource_type": AUDIT_RESOURCE},
        )

    scheme = payload.get("default_grading_scheme", settings.default_grading_scheme)
    threshold = Decimal(str(payload.get("default_pass_threshold", settings.default_pass_threshold)))
    error = validate_scheme_threshold(scheme, threshold)
    if error:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message=error,
            context={"resource_type": AUDIT_RESOURCE, "default_grading_scheme": scheme},
        )

    if "grade_bands" in payload:
        bands = payload["grade_bands"] or {}
        if not isinstance(bands, dict):
            raise equip_error(
                ErrorCode.VALIDATION_FAILED,
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                message="Bands must be an object keyed by scheme",
                context={"resource_type": AUDIT_RESOURCE},
            )
        for band_scheme, table in bands.items():
            if band_scheme not in BAND_SCHEMES:
                raise equip_error(
                    ErrorCode.VALIDATION_FAILED,
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    message=f"'{band_scheme}' has no bands: only {', '.join(BAND_SCHEMES)} are resolved through them",
                    context={"resource_type": AUDIT_RESOURCE, "scheme": band_scheme},
                )
            # The «3» floor is checked against the pass line the five-point
            # courses will actually be measured by — the one being written in
            # this same request, not the one on the row.
            error = validate_bands(table, band_scheme, threshold if band_scheme == "five_point" else None)
            if error:
                raise equip_error(
                    ErrorCode.VALIDATION_FAILED,
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    message=error,
                    context={"resource_type": AUDIT_RESOURCE, "scheme": band_scheme},
                )

    previous: dict[str, Any] = {
        key: (str(getattr(settings, key)) if isinstance(getattr(settings, key), Decimal) else getattr(settings, key))
        for key in payload
    }

    for key, value in payload.items():
        setattr(settings, key, value)
    settings.updated_by = director.id
    db.commit()
    db.refresh(settings)

    # The whole previous value, not a diff. Six months on, "who changed the
    # scale and what was it before" is the only question anyone asks of this
    # row, and a diff that says «grade_bands: changed» does not answer it.
    log_action(
        db,
        user_id=director.id,
        action=AUDIT_ACTION,
        resource_type=AUDIT_RESOURCE,
        resource_id="org",
        details={
            "changed": sorted(payload),
            "previous": previous,
            "current": {key: (str(value) if isinstance(value, Decimal) else value) for key, value in payload.items()},
        },
        request=request,
    )
    db.commit()
    return settings
