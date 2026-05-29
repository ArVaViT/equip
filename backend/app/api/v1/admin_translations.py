"""Admin tooling for the translation pipeline.

The orchestrator is fire-and-forget per spec: when Gemini fails a row
hits ``status='failed'`` and increments ``attempts``. After
``CONTENT_VERSION_MAX_ATTEMPTS`` (5) it promotes to
``failed_permanent`` — a terminal state where the auto-pipeline
refuses further retries. That's correct for the common case (a true
permanent failure: safety filter, oversize input) but trap-shaped for
the operator: a transient outage that ran out the budget leaves rows
stuck until someone touches the DB directly.

This module exposes the admin-only escape hatch: reset a list of cv
rows from ``failed_permanent`` back to ``failed`` and ``attempts=0``,
so the next reconcile pass picks them up.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003 — used by Pydantic schema at runtime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session  # noqa: TC002 — used by FastAPI Depends at runtime

from app.api.dependencies import require_admin
from app.core.database import get_db
from app.models.content_version import ContentVersion
from app.services.audit_service import log_action

if TYPE_CHECKING:
    from app.models.user import User


router = APIRouter(prefix="/admin/translations", tags=["admin-translations"])


class ResetByIdsRequest(BaseModel):
    """Reset a specific set of cv rows by primary key.

    Use this when the operator already knows which rows are stuck
    (e.g., from a Datadog alert that named the offending ids).
    """

    ids: list[UUID] = Field(..., min_length=1, max_length=500)


class ResetByEntityRequest(BaseModel):
    """Reset every failed row matching one ``(entity_type, entity_id,
    field, locale)`` selector — useful when the operator wants to
    unstick a whole entity without listing each row.
    """

    entity_type: str = Field(..., max_length=64)
    entity_id: str = Field(..., max_length=64)
    field: str = Field(..., max_length=64)
    locale: str = Field(..., max_length=10)


class ResetResponse(BaseModel):
    reset: int


@router.post(
    "/reset-by-ids",
    response_model=ResetResponse,
    summary="Reset failed_permanent cv rows by primary key",
    responses={
        200: {"description": "Rows reset; ``reset`` counts those actually touched."},
        404: {"description": "None of the supplied ids matched a failed_permanent row."},
    },
)
def reset_by_ids(
    payload: ResetByIdsRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ResetResponse:
    """Flip the listed rows from ``failed_permanent`` to ``failed`` and
    zero their ``attempts`` so the next orchestrator pass retries them.

    Rows in any other status are ignored — the endpoint is idempotent
    and refuses to silently mutate ``ok`` rows. Audit-logged.
    """
    try:
        affected = (
            db.query(ContentVersion)
            .filter(
                ContentVersion.id.in_(payload.ids),
                ContentVersion.status == "failed_permanent",
            )
            .update(
                {
                    ContentVersion.status: "failed",
                    ContentVersion.attempts: 0,
                },
                synchronize_session=False,
            )
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    if affected == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No failed_permanent rows matched the supplied ids.",
        )
    log_action(
        db,
        admin.id,
        "reset_failed_permanent",
        "content_version",
        ",".join(str(i) for i in payload.ids[:10]),
        details={"count": affected, "total_requested": len(payload.ids)},
        request=request,
    )
    return ResetResponse(reset=affected)


@router.post(
    "/reset-by-entity",
    response_model=ResetResponse,
    summary="Reset failed_permanent cv rows matching one (entity, field, locale)",
    responses={
        200: {"description": "Rows reset; ``reset`` counts those actually touched."},
        404: {"description": "No failed_permanent row matched the selector."},
    },
)
def reset_by_entity(
    payload: ResetByEntityRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ResetResponse:
    """Flip every ``failed_permanent`` row matching the selector back
    to ``failed`` with ``attempts=0``. Audit-logged.
    """
    try:
        affected = (
            db.query(ContentVersion)
            .filter(
                ContentVersion.entity_type == payload.entity_type,
                ContentVersion.entity_id == payload.entity_id,
                ContentVersion.field == payload.field,
                ContentVersion.locale == payload.locale,
                ContentVersion.status == "failed_permanent",
            )
            .update(
                {
                    ContentVersion.status: "failed",
                    ContentVersion.attempts: 0,
                },
                synchronize_session=False,
            )
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    if affected == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No failed_permanent row matched the selector.",
        )
    log_action(
        db,
        admin.id,
        "reset_failed_permanent",
        "content_version",
        f"{payload.entity_type}:{payload.entity_id}:{payload.field}:{payload.locale}",
        details={"count": affected},
        request=request,
    )
    return ResetResponse(reset=affected)
