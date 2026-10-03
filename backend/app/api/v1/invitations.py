from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    acting_organization,
    get_current_user,
    get_live_course_or_404,
    organization_scope,
    requested_organization_id,
    require_director,
    require_teacher,
)
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.invitation import Invitation
from app.models.organization import MembershipRole
from app.models.user import User, UserRole
from app.schemas.invitation import (
    InvitationAcceptRequest,
    InvitationAcceptResponse,
    InvitationCreate,
    InvitationPreview,
    InvitationPreviewRequest,
    InvitationResponse,
    InvitationRoleLiteral,
    InvitationScopeLiteral,
    InvitationStatusLiteral,
)
from app.schemas.locale import normalize_locale
from app.services.invitation_service import (
    accept_invitation,
    course_title_for_invitation,
    create_or_resend_invitation,
    get_invitation_by_id,
    get_invitation_by_token,
    is_invitation_expired,
    list_invitations,
    revoke_invitation,
)
from app.services.memberships import belongs_to, directs

router = APIRouter(prefix="/invitations", tags=["invitations"])


def _to_response(invitation: Invitation) -> InvitationResponse:
    is_expired = invitation.status == "pending" and is_invitation_expired(invitation)
    return InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role=cast("InvitationRoleLiteral", invitation.role),
        scope=cast("InvitationScopeLiteral", invitation.scope),
        course_id=invitation.course_id,
        status=cast("InvitationStatusLiteral", invitation.status),
        invited_by=invitation.invited_by,
        created_at=invitation.created_at,
        accepted_at=invitation.accepted_at,
        fulfilled_at=invitation.fulfilled_at,
        expires_at=invitation.expires_at,
        is_expired=is_expired,
        age_attested_at=invitation.age_attested_at,
    )


@router.post("", response_model=InvitationResponse, status_code=201)
def create_invitation(
    body: InvitationCreate,
    teacher: User = Depends(require_teacher),
    requested: UUID | None = Depends(requested_organization_id),
    db: Session = Depends(get_db),
) -> InvitationResponse:
    """Invite an address onto a course, into the school, or to the platform.

    Who may do which:

    * **A course invitation** may be written by the person who owns the
      course, which is what makes the invitation come from the teacher
      the student is about to study under rather than from an
      administrator they have never met, and by a director of the
      course's organization. The organization is the course's own — not
      whichever one the inviter is acting in — so a director of two
      schools cannot invite onto A's course from B. For anyone who does
      not direct that organization the role must be ``student``: a
      teacher who could mint teachers would be an escalation with extra
      steps.
    * **Everything else** — inviting into the organization at large, or
      to the platform, and any invitation carrying a teaching role —
      stays with a director (of the organization the request acts in,
      ``acting_organization``) or a platform admin.

    Idempotent on re-invite while a prior invitation for the same
    (organization, email, role, course) is still pending and unexpired;
    see ``create_or_resend_invitation`` for the dedupe/resend contract.
    """
    if body.scope == "course" and body.course_id:
        course = get_live_course_or_404(db, body.course_id)
        # A closed course of an organization the inviter is not in does not
        # exist for them — the same 404 as the course page, before any 403
        # could confirm it is there.
        if course.access_mode == "institute" and not belongs_to(db, teacher, course.organization_id):
            raise equip_error(
                ErrorCode.RESOURCE_NOT_FOUND,
                status_code=status.HTTP_404_NOT_FOUND,
                message="Course not found",
                context={"resource_type": "course", "resource_id": body.course_id},
            )
        organization_id = course.organization_id
        is_director = directs(db, teacher, organization_id)
        if not is_director and str(course.created_by) != str(teacher.id):
            raise equip_error(
                ErrorCode.AUTH_FORBIDDEN,
                status_code=status.HTTP_403_FORBIDDEN,
                message="You do not own this course",
            )
    else:
        if teacher.role not in (UserRole.DIRECTOR.value, UserRole.ADMIN.value):
            raise equip_error(
                ErrorCode.AUTH_FORBIDDEN,
                status_code=status.HTTP_403_FORBIDDEN,
                message="A teacher can only invite people onto their own course",
                context={"resource_type": "invitation"},
            )
        organization_id = acting_organization(db, teacher, requested, role=MembershipRole.DIRECTOR.value)
        is_director = True
    if not is_director and body.role != UserRole.STUDENT.value:
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="A teacher can invite students; a teaching role is granted by a director",
            context={"resource_type": "invitation", "field": "role"},
        )

    invitation, _is_new = create_or_resend_invitation(
        db,
        email=body.email,
        role=body.role,
        scope=body.scope,
        course_id=body.course_id,
        invited_by=teacher.id,
        organization_id=organization_id,
    )
    return _to_response(invitation)


@router.get("", response_model=list[InvitationResponse])
def list_invitations_route(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    role: str | None = Query(None),
    invite_status: str | None = Query(None, alias="status"),
    director: User = Depends(require_director),
    requested: UUID | None = Depends(requested_organization_id),
    db: Session = Depends(get_db),
) -> list[InvitationResponse]:
    # A director sees the invitations of the organization they are acting
    # in; platform staff see all of them unless they named one — the same
    # split the cohort list uses (``organization_scope``).
    scope = organization_scope(db, director, requested)
    rows = list_invitations(
        db,
        organization_id=scope,
        skip=skip,
        limit=limit,
        role=role,
        status_filter=invite_status,
    )
    return [_to_response(r) for r in rows]


@router.delete("/{invitation_id}", response_model=InvitationResponse)
def revoke_invitation_route(
    invitation_id: str = Path(...),
    director: User = Depends(require_director),
    db: Session = Depends(get_db),
) -> InvitationResponse:
    """Withdraw a pending invitation, so its link stops working.

    There was no way to do this. `revoked` has been a legal status since
    the table was created and `accept_invitation` already refuses anything
    that is not `pending`, but nothing could set it — so an invitation sent
    to the wrong address stayed live for seven days, carrying a teacher
    role with it.

    The invitation names its organization, and the caller must direct that
    one (``directs``); a director of somewhere else is told the same thing
    as somebody asking about an invitation that does not exist.
    """
    existing = get_invitation_by_id(db, invitation_id)
    if existing is None or not directs(db, director, existing.organization_id):
        raise equip_error(
            ErrorCode.INVITATION_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Invitation not found",
            context={"resource_type": "invitation", "resource_id": str(invitation_id)},
        )
    invitation = revoke_invitation(
        db,
        invitation_id=invitation_id,
        actor=director,
        organization_id=existing.organization_id,
    )
    return _to_response(invitation)


def _preview(db: Session, response: Response, token: str, accept_language: str | None) -> InvitationPreview:
    invitation = get_invitation_by_token(db, token)
    # The course title is the only translated text on this route, and it
    # is resolved per reader, so the answer varies by header.
    response.headers["Vary"] = "Accept-Language"
    return InvitationPreview(
        email=invitation.email,
        role=cast("InvitationRoleLiteral", invitation.role),
        scope=cast("InvitationScopeLiteral", invitation.scope),
        # Only the title, and only for a course invitation: someone
        # deciding whether to accept is entitled to know what they are
        # being invited to, and a published course's title is public
        # anyway. In their own language or not at all -- they have no
        # profile yet, so the browser's header is the only thing that
        # knows what they read.
        course_title=course_title_for_invitation(db, invitation, display_locale=normalize_locale(accept_language)),
        status=cast("InvitationStatusLiteral", invitation.status),
        # A fulfilled invitation is still redeemable by its invitee (see
        # accept_invitation), on the same clock as a pending one.
        is_expired=invitation.status in ("pending", "fulfilled") and is_invitation_expired(invitation),
    )


@router.post("/preview", response_model=InvitationPreview)
def preview_invitation(
    body: InvitationPreviewRequest,
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    db: Session = Depends(get_db),
) -> InvitationPreview:
    """Unauthenticated preview of an invite, for the accept-invite page
    to render "you've been invited as a teacher" copy before the visitor
    has signed in. Deliberately returns 200 with ``is_expired``/``status``
    rather than 404/410 for a stale token, so the accept page can render
    a clear "this invite expired" state instead of a generic not-found.

    The token travels in the body. In the path it was written into every
    request log this backend has -- ours, which now redacts it, and
    Vercel's platform log (``[GET] /api/v1/invitations/token/<token>``),
    which nothing in this process can reach. Nobody logs a body. ``POST``
    for a read is the price of that, and ``/accept`` already pays it.
    """
    return _preview(db, response, body.token, accept_language)


@router.post("/accept", response_model=InvitationAcceptResponse)
def accept_invitation_route(
    body: InvitationAcceptRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvitationAcceptResponse:
    """Redeem an invite token for the signed-in caller.

    The caller must already have an account (self-registered as student,
    or logged in via Google) under the exact email the invite was sent
    to -- see the migration docstring for why the backend doesn't mint
    the Supabase Auth user itself.
    """
    invitation = accept_invitation(
        db,
        token=body.token,
        current_user_id=current_user.id,
        current_user_email=current_user.email,
    )
    return InvitationAcceptResponse(
        role=cast("InvitationRoleLiteral", invitation.role),
        scope=cast("InvitationScopeLiteral", invitation.scope),
        enrolled_course_id=invitation.course_id,
    )
