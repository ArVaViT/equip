"""An organization's own page: `equipbible.com/s/<slug>`.

This is where a certificate points. A student's employer reads a
document, sees a school name and a number, and follows the link to find
out whether the school is real — so the page has to exist, be public,
and answer without a token.

What it serves: the organization's name and country, whether it is
active, and its public courses. What it does not serve is anything
marked ``institute`` — those belong to the organization's own people and
are reached through ``GET /courses/my-organization``, which requires
being one of them.

A suspended organization keeps its page and loses its courses. Deleting
the page would break every certificate it ever issued, and a certificate
records that a student did the work while the school was in good
standing — withdrawing that punishes the student for somebody else's
conduct. The page says the organization is no longer active, which is
the honest answer without being a retroactive one.
"""

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.course import Course, CourseStatus
from app.models.organization import Organization
from app.schemas.locale import LocaleCode, normalize_locale
from app.schemas.organization import OrganizationPublicResponse
from app.services.translation.resolve_for_display import build_localized_course_summaries

router = APIRouter(prefix="/organizations", tags=["organizations"])

#: An organization that is no longer serving its courses. Its page stays
#: up for the certificates that point at it.
_INACTIVE = "suspended"


@router.get("/{slug}", response_model=OrganizationPublicResponse)
def get_organization_page(
    slug: str,
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
) -> OrganizationPublicResponse:
    """The public page behind ``/s/<slug>``. No token required."""
    response.headers["Vary"] = "Accept-Language"
    organization = db.query(Organization).filter(Organization.slug == slug).first()
    if organization is None:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"No organization at '{slug}'",
            context={"resource_type": "organization", "slug": slug},
        )

    active = organization.status != _INACTIVE
    courses = []
    if active:
        display_locale: LocaleCode = normalize_locale(accept_language)
        rows = (
            db.query(Course)
            .filter(
                Course.organization_id == organization.id,
                Course.status == CourseStatus.PUBLISHED,
                Course.access_mode == "public",
                Course.deleted_at.is_(None),
            )
            .order_by(Course.created_at.desc())
            .limit(limit)
            .all()
        )
        courses = build_localized_course_summaries(db, rows, display_locale)

    return OrganizationPublicResponse(
        slug=organization.slug,
        public_name=organization.public_name,
        country=organization.country,
        active=active,
        verified=organization.status == "verified",
        courses=courses,
    )
