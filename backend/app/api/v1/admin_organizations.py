"""Admitting an organization, and naming the person who runs it.

Until now organization #1 was inserted by hand, because the columns
arrived before the surface that fills them. That was fine for one; it is
not a way to admit a second, and "a second one *could* be created" is
the line the engineering plan draws for this step being finished.

Admission is platform staff's and is deliberately not self-serve. The
product decision says it at length; the short version is that the name
on a certificate is the scarce thing this platform defends, and a signup
form hands it to whoever types fastest.

What staff can do here: create an organization, edit what it is called
and what state it is in, and appoint its director. What nobody can do
here is change a slug — it is in the organization's URL and printed on
every certificate it has issued.
"""

import uuid

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.organization import (
    DirectorAppointment,
    OrganizationCreate,
    OrganizationResponse,
    OrganizationUpdate,
)
from app.services.audit_service import log_action

router = APIRouter(prefix="/admin/organizations", tags=["admin-organizations"])


def _get_or_404(db: Session, organization_id: uuid.UUID) -> Organization:
    organization = db.query(Organization).filter(Organization.id == organization_id).first()
    if organization is None:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Organization not found",
            context={"resource_type": "organization", "resource_id": str(organization_id)},
        )
    return organization


def _serialize_many(db: Session, organizations: list[Organization]) -> list[OrganizationResponse]:
    """Two grouped queries for the whole page rather than two per row."""
    if not organizations:
        return []
    ids = [o.id for o in organizations]

    # ``organization_id`` is nullable on ``profiles`` — platform staff
    # belong nowhere — so the rows come back as ``UUID | None`` and the
    # None bucket is dropped rather than counted under some organization.
    counts: dict[uuid.UUID, int] = {
        org_id: count
        for org_id, count in db.query(User.organization_id, func.count(User.id))
        .filter(User.organization_id.in_(ids), User.deactivated_at.is_(None))
        .group_by(User.organization_id)
        .all()
        if org_id is not None
    }
    directors: dict[uuid.UUID, list[str]] = {}
    for org_id, email in (
        db.query(User.organization_id, User.email)
        .filter(
            User.organization_id.in_(ids),
            User.role == UserRole.DIRECTOR.value,
            User.deactivated_at.is_(None),
        )
        .order_by(User.email)
        .all()
    ):
        directors.setdefault(org_id, []).append(email)

    return [
        OrganizationResponse.model_validate(
            {
                "id": o.id,
                "slug": o.slug,
                "public_name": o.public_name,
                "legal_name": o.legal_name,
                "country": o.country,
                "status": o.status,
                "verification_basis": o.verification_basis,
                "verified_at": o.verified_at,
                "created_at": o.created_at,
                "member_count": counts.get(o.id, 0),
                "director_emails": directors.get(o.id, []),
            }
        )
        for o in organizations
    ]


def _serialize(db: Session, organization: Organization) -> OrganizationResponse:
    return _serialize_many(db, [organization])[0]


@router.get("", response_model=list[OrganizationResponse])
def list_organizations(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[OrganizationResponse]:
    """Every organization on the platform, newest first."""
    rows = db.query(Organization).order_by(Organization.created_at.desc()).offset(skip).limit(limit).all()
    return _serialize_many(db, rows)


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
def create_organization(
    data: OrganizationCreate,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    """Admit an organization.

    A duplicate slug or public name is a 409 rather than a 500: both are
    unique, and both are things a person types twice by accident.
    """
    organization = Organization(
        id=uuid.uuid4(),
        slug=data.slug,
        public_name=data.public_name,
        legal_name=data.legal_name,
        country=data.country,
        status=data.status,
        created_by=admin.id,
    )
    db.add(organization)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_409_CONFLICT,
            message="An organization with this slug or public name already exists",
            context={"slug": data.slug, "public_name": data.public_name},
        ) from None

    log_action(
        db,
        admin.id,
        "create",
        "organization",
        str(organization.id),
        details={"slug": data.slug, "public_name": data.public_name, "status": data.status},
        request=request,
    )
    db.commit()
    db.refresh(organization)
    return _serialize(db, organization)


@router.get("/{organization_id}", response_model=OrganizationResponse)
def get_organization(
    organization_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    return _serialize(db, _get_or_404(db, organization_id))


@router.patch("/{organization_id}", response_model=OrganizationResponse)
def update_organization(
    organization_id: uuid.UUID,
    data: OrganizationUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    """Rename, re-country, or move an organization between states.

    ``verified`` stamps who verified it and when — the two questions
    asked later are "on what basis" and "by whom", and a status without
    them is a claim nobody can check. Leaving ``verified`` clears the
    stamp, so the record never says an organization was verified at a
    moment when it was not.
    """
    organization = _get_or_404(db, organization_id)
    patch = data.model_dump(exclude_unset=True)
    was_verified = organization.status == "verified"

    for field, value in patch.items():
        setattr(organization, field, value)

    if organization.status == "verified" and not was_verified:
        organization.verified_at = func.now()
        organization.verified_by = admin.id
    elif was_verified and organization.status != "verified":
        organization.verified_at = None
        organization.verified_by = None

    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_409_CONFLICT,
            message="Another organization already uses this public name",
            context={"organization_id": str(organization_id)},
        ) from None

    log_action(
        db,
        admin.id,
        "update",
        "organization",
        str(organization.id),
        details=patch,
        request=request,
    )
    db.commit()
    db.refresh(organization)
    return _serialize(db, organization)


@router.post("/{organization_id}/director", response_model=OrganizationResponse)
def appoint_director(
    organization_id: uuid.UUID,
    data: DirectorAppointment,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> OrganizationResponse:
    """Make an existing account the director of this organization.

    Two things happen together and must not drift apart: the person gets
    the ``director`` role, and they are moved into this organization.
    A director of nowhere administers nothing, and a director filed under
    the wrong organization holds the keys to somebody else's cohorts.

    Moving somebody who already belongs elsewhere is allowed and audited
    — one organization per account is the rule, so a move is the only
    way it can happen. What is refused is promoting platform staff:
    the roles are deliberately separate, and quietly demoting an admin
    into a director is not something an appointment should do.
    """
    organization = _get_or_404(db, organization_id)
    person = db.query(User).filter(func.lower(User.email) == data.email.strip().lower()).first()
    if person is None:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"No account with the email '{data.email}'",
            context={"resource_type": "user", "email": data.email},
        )
    if person.role == UserRole.ADMIN.value:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_409_CONFLICT,
            message=(
                "This account is platform staff. Platform administration and running an "
                "organization are separate roles on purpose — appoint a different account."
            ),
            context={"resource_type": "user", "email": person.email, "role": person.role},
        )

    previous_organization = person.organization_id
    previous_role = person.role
    person.role = UserRole.DIRECTOR.value
    person.organization_id = organization.id

    log_action(
        db,
        admin.id,
        "appoint_director",
        "organization",
        str(organization.id),
        details={
            "email": person.email,
            "previous_role": previous_role,
            "previous_organization_id": str(previous_organization) if previous_organization else None,
        },
        request=request,
    )
    db.commit()
    db.refresh(organization)
    return _serialize(db, organization)
