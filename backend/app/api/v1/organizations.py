"""An organization's own page: `equipbible.com/o/<slug>`.

This is where a certificate points. A student's employer reads a
document, sees a school name and a number, and follows the link to find
out whether the school is real — so the page has to exist, be public,
and answer without a token.

What it serves: the organization's name and country, whether it is
active, and its public courses. What it does not serve is anything
marked ``institute`` — those belong to the organization's own people and
are reached through ``GET /courses/my-organizations``, which lists them
for its members.

A suspended organization keeps its page and loses its courses. Deleting
the page would break every certificate it ever issued, and a certificate
records that a student did the work while the school was in good
standing — withdrawing that punishes the student for somebody else's
conduct. The page says the organization is no longer active, which is
the honest answer without being a retroactive one.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_optional_user
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.certificate import Certificate
from app.models.course import Chapter, Course, CourseStatus
from app.models.org_settings import OrgSettings
from app.models.organization import Organization, OrganizationMember
from app.models.user import User, UserRole
from app.schemas.locale import LocaleCode, normalize_locale
from app.schemas.organization import (
    LockedCourse,
    OrganizationCard,
    OrganizationPerson,
    OrganizationProfileUpdate,
    OrganizationPublicResponse,
    OrganizationStats,
)
from app.services.memberships import belongs_to, directs
from app.services.staged_edits.visibility import chapter_awaits_first_release
from app.services.translation.resolve_for_display import build_localized_course_summaries

router = APIRouter(prefix="/organizations", tags=["organizations"])

#: An organization that is no longer serving its courses. Its page stays
#: up for the certificates that point at it.
_INACTIVE = "suspended"

#: Below these, a count says something about people rather than about the
#: organization: "4 members" beside a director's name is nearly a list, and
#: "2 teachers" is two names. Not shown below them.
_MEMBERS_SHOWN_FROM = 10
_TEACHERS_SHOWN_FROM = 3


def _not_found(slug: str) -> Exception:
    return equip_error(
        ErrorCode.RESOURCE_NOT_FOUND,
        status_code=status.HTTP_404_NOT_FOUND,
        message=f"No organization at '{slug}'",
        context={"resource_type": "organization", "slug": slug},
    )


def _active_members(db: Session, organization_id: UUID, roles: tuple[str, ...]) -> int:
    """How many people hold one of ``roles`` here today.

    An active membership on a deactivated account is nobody: the account
    cannot sign in, and a count that includes it says the organization is
    larger than it is. Until 2026-10-03 it was counted.
    """
    return (
        db.query(func.count())
        .select_from(OrganizationMember)
        .join(User, User.id == OrganizationMember.user_id)
        .filter(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.status == "active",
            OrganizationMember.role.in_(roles),
            User.deactivated_at.is_(None),
        )
        .scalar()
        or 0
    )


@router.get("", response_model=list[OrganizationCard])
def list_organizations(
    limit: int = Query(60, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[OrganizationCard]:
    """ "Organizations on Equip" — the showcase. No token required.

    Only what the platform stands behind and somebody runs: verified, at
    least one active director, at least one published course. Verified
    first is the filter itself; then the ones teaching most. The paragraph
    is not translated, so the answer does not vary by language.
    """
    course_counts = (
        db.query(Course.organization_id, func.count(Course.id))
        .filter(Course.status == CourseStatus.PUBLISHED, Course.deleted_at.is_(None))
        .group_by(Course.organization_id)
        .all()
    )
    courses_by_org = {org_id: n for org_id, n in course_counts if org_id is not None}
    # "Somebody runs it" means a director who can sign in: the page's own
    # list of directors leaves out a deactivated account, and the showcase
    # must not stand behind an organization on the strength of one.
    directed = {
        row[0]
        for row in db.query(OrganizationMember.organization_id)
        .join(User, User.id == OrganizationMember.user_id)
        .filter(
            OrganizationMember.role == "director",
            OrganizationMember.status == "active",
            User.deactivated_at.is_(None),
        )
        .distinct()
        .all()
    }
    rows = db.query(Organization).filter(Organization.status == "verified").all()
    cards = [
        OrganizationCard(
            slug=o.slug,
            public_name=o.public_name,
            country=o.country,
            logo_url=o.logo_url,
            description=o.description,
            courses=courses_by_org.get(o.id, 0),
        )
        for o in rows
        if o.id in directed and courses_by_org.get(o.id, 0) > 0
    ]
    cards.sort(key=lambda c: (-c.courses, c.public_name.lower()))
    return cards[:limit]


@router.get("/{slug}", response_model=OrganizationPublicResponse)
def get_organization_page(
    slug: str,
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    limit: int = Query(100, ge=1, le=200),
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> OrganizationPublicResponse:
    """The public page behind ``/o/<slug>``. No token required.

    An organization admitted but not yet verified (``pending``,
    ``approved``) is a 404 to strangers and visible to its own people and
    the platform's staff: the platform has not yet said it stands behind it.
    """
    response.headers["Vary"] = "Accept-Language"
    organization = db.query(Organization).filter(Organization.slug == slug).first()
    if organization is None:
        raise _not_found(slug)
    is_admin = current_user is not None and current_user.role == UserRole.ADMIN.value
    member = belongs_to(db, current_user, organization.id) if current_user is not None else False
    if organization.status not in ("verified", _INACTIVE) and not (member or is_admin):
        raise _not_found(slug)

    active = organization.status != _INACTIVE
    display_locale: LocaleCode = normalize_locale(accept_language)
    published = (
        db.query(Course)
        .filter(
            Course.organization_id == organization.id,
            Course.status == CourseStatus.PUBLISHED,
            Course.deleted_at.is_(None),
        )
        .order_by(Course.created_at.desc())
        .limit(limit)
        .all()
    )
    courses = []
    locked: list[LockedCourse] = []
    if active:
        # A member's closed courses are theirs: full cards. Everybody else
        # sees a closed course as its cover, its title and a lock.
        open_rows = [c for c in published if c.access_mode == "public" or member or is_admin]
        closed_rows = [c for c in published if c not in open_rows]
        courses = build_localized_course_summaries(db, open_rows, display_locale)
        locked = [
            LockedCourse(id=summary.id, title=summary.title, image_url=summary.image_url)
            for summary in build_localized_course_summaries(db, closed_rows, display_locale)
        ]

    course_ids = [c.id for c in published]
    lessons = (
        db.query(func.count(Chapter.id))
        .filter(Chapter.course_id.in_(course_ids), Chapter.deleted_at.is_(None), ~chapter_awaits_first_release())
        .scalar()
        if course_ids
        else 0
    ) or 0
    certificates = (
        db.query(func.count(Certificate.id))
        .filter(Certificate.organization_id == organization.id, Certificate.status == "approved")
        .scalar()
        or 0
    )
    members = _active_members(db, organization.id, ("director", "teacher", "student"))
    teachers = _active_members(db, organization.id, ("director", "teacher"))
    directors = (
        db.query(User.full_name, User.avatar_url)
        .join(OrganizationMember, OrganizationMember.user_id == User.id)
        .filter(
            OrganizationMember.organization_id == organization.id,
            OrganizationMember.status == "active",
            OrganizationMember.role == "director",
            User.deactivated_at.is_(None),
        )
        .order_by(OrganizationMember.joined_at)
        .all()
    )
    settings_row = db.get(OrgSettings, organization.id)
    can_edit = current_user is not None and directs(db, current_user, organization.id)

    return OrganizationPublicResponse(
        slug=organization.slug,
        public_name=organization.public_name,
        country=organization.country,
        active=active,
        verified=organization.status == "verified",
        courses=courses,
        description=organization.description,
        logo_url=organization.logo_url,
        website_url=organization.website_url,
        city=settings_row.city if settings_row is not None else None,
        # A director without a name on their profile is not shown by
        # address instead: no name, no line.
        directors=[OrganizationPerson(full_name=name, avatar_url=avatar) for name, avatar in directors if name],
        stats=OrganizationStats(
            courses=len(published),
            lessons=lessons,
            certificates=certificates,
            members=members if organization.show_member_count and members >= _MEMBERS_SHOWN_FROM else None,
            teachers=teachers if teachers >= _TEACHERS_SHOWN_FROM else None,
        ),
        locked_courses=locked,
        viewer_is_member=member,
        viewer_can_edit=can_edit,
        id=organization.id if can_edit else None,
        show_member_count=organization.show_member_count if can_edit else None,
        since=organization.created_at,
    )


@router.patch("/{organization_id}/profile", response_model=OrganizationPublicResponse)
def update_organization_profile(
    organization_id: UUID,
    data: OrganizationProfileUpdate,
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrganizationPublicResponse:
    """What the organization says about itself — its director's to write.

    The name, the slug and the status stay with the platform (they are on
    certificates and in the contract); the paragraph, the website and
    whether to show a member count are the organization's own.
    """
    organization = db.get(Organization, organization_id)
    # 404, not 403, for somebody else's organization: whether it exists is
    # not theirs to learn from this route either.
    if organization is None or not directs(db, current_user, organization.id):
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Organization not found",
            context={"resource_type": "organization", "resource_id": str(organization_id)},
        )
    updates = data.model_dump(exclude_unset=True)
    if "description" in updates:
        text = (updates["description"] or "").strip()
        organization.description = text or None
    if "website_url" in updates:
        organization.website_url = (updates["website_url"] or "").strip() or None
    if updates.get("show_member_count") is not None:
        organization.show_member_count = bool(updates["show_member_count"])
    db.commit()
    return get_organization_page(organization.slug, response, accept_language, 100, current_user, db)
