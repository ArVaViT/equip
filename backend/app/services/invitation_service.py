from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import status

from app.core.config import settings
from app.core.errors import ErrorCode, equip_error
from app.core.metrics import increment, timing
from app.models.course import Course
from app.models.invitation import Invitation, InvitationScope, InvitationStatus
from app.models.user import User, higher_role
from app.services.audit_service import log_action
from app.services.course_service._enrollment import enroll_user_in_course
from app.services.email.invitation import send_invitation_email
from app.services.translation.resolve_for_display import fetch_course_titles_by_id
from app.services.user_locale import preferred_locale_of

if TYPE_CHECKING:
    from uuid import UUID

    from fastapi import Request
    from sqlalchemy.orm import Session

    from app.schemas.locale import LocaleCode

_TOKEN_BYTES = 32


def _generate_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


def is_invitation_expired(invitation: Invitation) -> bool:
    expires_at = invitation.expires_at
    if expires_at.tzinfo is None:
        # SQLite (tests) round-trips naive datetimes; Postgres always
        # returns tz-aware. Normalise to UTC before comparing either way.
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at < datetime.now(UTC)


def _accept_url(token: str) -> str:
    return f"{settings.FRONTEND_URL.rstrip('/')}/invite/accept?token={token}"


def _inviter_locale(db: Session, invited_by: uuid.UUID | str | None) -> LocaleCode:
    """The language to write the invitation in.

    The person being invited has no account yet, so there is no
    preference to read. The next best thing is the language of whoever
    is doing the inviting: an admin writing to their own community
    almost always shares its language, and it beats defaulting everyone
    to English — which is what happened before, including for the
    German and Ukrainian schools this platform now serves.

    Only when there is no inviter to read does this land on the
    platform's last resort, which is English again — but by then it is
    an answer to "we know nothing", not a substitute for asking.
    """
    return preferred_locale_of(db, invited_by)


def _mail_the_invitation(db: Session, invitation: Invitation, *, invited_by: UUID) -> None:
    """Send the invitation, in the inviting person's language and name.

    Delivery is deliberately not checked: the row and its token already
    exist, the link works whether or not the mail got out, and a
    provider hiccup must not turn "invitation created" into an error on
    somebody's screen. What a failure does leave is a log line — see
    ``services/email/send.py``.
    """
    inviter = db.query(User).filter(User.id == invited_by).first()
    send_invitation_email(
        db,
        invitation,
        accept_url=_accept_url(invitation.token),
        locale=_inviter_locale(db, invited_by),
        inviter_name=inviter.full_name if inviter else None,
    )


def course_of_organization(db: Session, course_id: str, organization_id: UUID) -> Course:
    """The course this organization may invite onto, or 404.

    Same 404-for-everything rule the rest of the invitation surface
    uses: a course in another school and a course that does not exist
    are the same answer, because the difference is information the
    caller has not earned.

    Checked at creation *and* again at acceptance, because seven days
    pass in between and a course can be unpublished, deleted or moved
    in that time.
    """
    course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.organization_id == organization_id,
            Course.deleted_at.is_(None),
        )
        .first()
    )
    if course is None:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Course not found",
            context={"resource_type": "course", "resource_id": course_id},
        )
    return course


def course_title_for_invitation(db: Session, invitation: Invitation, *, display_locale: LocaleCode) -> str | None:
    """The title to show on the accept page, or ``None``.

    Only for a course invitation, and only in the reader's own language.
    The invited person has no account yet, so the language comes from
    their browser — and when the course has no title in it, the answer
    is nothing rather than a title in a language they did not ask for.
    The page leaves the line out; it does not print a blank.

    The temptation here is ``source_then_any``, so that every invitation
    names *something*. That is the fallback reserved for people looking
    at their own material — an author, a marker, a certificate that
    would otherwise go out with an empty line — and a stranger reading
    an invitation is none of those.
    """
    if invitation.scope != InvitationScope.COURSE.value or not invitation.course_id:
        return None
    titles = fetch_course_titles_by_id(db, [invitation.course_id], display_locale=display_locale)
    return titles.get(invitation.course_id) or None


def create_or_resend_invitation(
    db: Session,
    *,
    email: str,
    role: str,
    invited_by: UUID,
    organization_id: UUID,
    scope: str = InvitationScope.ORGANIZATION.value,
    course_id: str | None = None,
    request: Request | None = None,
) -> tuple[Invitation, bool]:
    """Create a new invitation, or resend the existing pending one.

    Returns ``(invitation, is_new)``. The dedup key is ``(organization,
    email, role, course)`` while ``status == 'pending'`` -- it mirrors
    the partial unique index, which is the real race guard; this lookup
    is the happy-path short-circuit that avoids hitting it on a normal
    "resend" click.

    The organization is part of that key and was not always: the lookup
    used to match ``(email, role)`` globally, so a second school
    inviting a person who had a pending invitation from a first school
    got the *first school's row* back and mailed out its token. One
    school inviting the same person onto two courses hit the same index
    from the other side.

    A resend does NOT rotate the token or reset ``expires_at`` -- a link
    already shared stays valid on its original clock. An
    expired-but-still-``pending`` row is revoked first so the fresh
    insert does not collide with the index.
    """
    normalized_email = email.strip().lower()
    if scope == InvitationScope.COURSE.value:
        # Raises 404 when the course is not this organization's to offer.
        course_of_organization(db, course_id or "", organization_id)
    elif course_id is not None:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message="course_id is only meaningful when scope is 'course'",
            context={"resource_type": "invitation"},
        )

    existing = (
        db.query(Invitation)
        .filter(
            Invitation.organization_id == organization_id,
            Invitation.email == normalized_email,
            Invitation.role == role,
            Invitation.course_id == course_id if course_id is not None else Invitation.course_id.is_(None),
            Invitation.status == InvitationStatus.PENDING.value,
        )
        .first()
    )
    if existing is not None and not is_invitation_expired(existing):
        increment("equip.invitations.created_total", scope=scope, role=role, kind="resend")
        _mail_the_invitation(db, existing, invited_by=invited_by)
        return existing, False

    if existing is not None:
        existing.status = InvitationStatus.REVOKED.value

    invitation = Invitation(
        organization_id=organization_id,
        email=normalized_email,
        role=role,
        scope=scope,
        course_id=course_id,
        token=_generate_token(),
        invited_by=invited_by,
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)

    log_action(
        db,
        invited_by,
        "create",
        "invitation",
        str(invitation.id),
        details={"email": normalized_email, "role": role, "scope": scope, "course_id": course_id},
        request=request,
    )

    increment("equip.invitations.created_total", scope=scope, role=role, kind="new")
    _mail_the_invitation(db, invitation, invited_by=invited_by)
    return invitation, True


def list_invitations(
    db: Session,
    *,
    organization_id: uuid.UUID | None = None,
    skip: int = 0,
    limit: int = 50,
    role: str | None = None,
    status_filter: str | None = None,
) -> list[Invitation]:
    """Pending and spent invitations, newest first.

    ``organization_id`` scopes the list to one organization and is what
    a director gets: an invitation carries the email address of a person
    who has not joined yet, and that is the neighbouring organization's
    recruiting, not theirs. ``None`` means platform staff, who
    administer every organization by definition.
    """
    query = db.query(Invitation)
    if organization_id is not None:
        query = query.filter(Invitation.organization_id == organization_id)
    if role is not None:
        query = query.filter(Invitation.role == role)
    if status_filter is not None:
        query = query.filter(Invitation.status == status_filter)
    return query.order_by(Invitation.created_at.desc()).offset(skip).limit(limit).all()


def get_invitation_by_token(db: Session, token: str) -> Invitation:
    invitation = db.query(Invitation).filter(Invitation.token == token).first()
    if invitation is None:
        raise equip_error(
            ErrorCode.INVITATION_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Invitation not found",
            context={"resource_type": "invitation"},
        )
    return invitation


def revoke_invitation(
    db: Session,
    *,
    invitation_id: UUID | str,
    actor: User,
    organization_id: UUID | str | None,
    request: Request | None = None,
) -> Invitation:
    """Withdraw a pending invitation so its link stops working.

    The status existed from the start — `chk_invitations_status` has
    allowed `revoked` since the table was created, and `accept_invitation`
    already refuses anything that is not `pending` — but nothing could set
    it. An admin who invited the wrong address, or invited somebody who
    should no longer be joining, had no way to take it back: the link stayed
    live for its full seven days, and it grants a teacher role.

    Only a pending invitation can be withdrawn. An accepted one is a person
    with an account (remove the role instead), and an already-revoked one is
    not an error worth raising twice — but it is not a silent success
    either, because "revoke" on a row somebody already redeemed would read
    as though the access were gone.
    """
    try:
        # A malformed id is "no such invitation", not a 500 from the driver.
        ident = uuid.UUID(str(invitation_id))
    except ValueError:
        ident = None
    invitation = db.query(Invitation).filter(Invitation.id == ident).first() if ident is not None else None
    if invitation is None or (organization_id is not None and str(invitation.organization_id) != str(organization_id)):
        # A director asking about another organization's invitation is told
        # the same thing as somebody asking about one that does not exist.
        raise equip_error(
            ErrorCode.INVITATION_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Invitation not found",
            context={"resource_type": "invitation", "resource_id": str(invitation_id)},
        )

    if invitation.status == InvitationStatus.ACCEPTED.value:
        raise equip_error(
            ErrorCode.INVITATION_ALREADY_USED,
            status_code=status.HTTP_409_CONFLICT,
            message="This invitation has already been accepted",
            context={"resource_type": "invitation", "resource_id": str(invitation.id)},
        )

    if invitation.status != InvitationStatus.REVOKED.value:
        invitation.status = InvitationStatus.REVOKED.value
        db.commit()
        db.refresh(invitation)
        log_action(
            db,
            actor.id,
            "revoke",
            "invitation",
            str(invitation.id),
            details={"email": invitation.email, "role": invitation.role},
            request=request,
        )
    return invitation


def accept_invitation(
    db: Session,
    *,
    token: str,
    current_user_id: UUID,
    current_user_email: str,
    request: Request | None = None,
) -> Invitation:
    """Redeem a token and grant everything the invitation promised.

    The caller must already be authenticated as a user whose email
    matches the invitation -- see the migration/module docstrings for
    why the backend does not mint the Supabase Auth user itself.

    One transaction, four writes, all or nothing: the invitation flips
    to accepted, the role moves (never downward), the person joins the
    organization, and a course invitation seats them on the course.
    Until 2026-09-12 this wrote the role and stopped there, so an
    invited teacher was left with a role and no school -- 403 on every
    organizational route, invisible catalogue -- and a director who
    accepted a student invitation was demoted by it.

    The single-use guard (``UPDATE ... WHERE status='pending'``) is
    still what defeats a double click: the second one loses the race in
    Postgres rather than in Python.

    The course is re-checked here even though it was checked when the
    invitation was written. Seven days is long enough for a course to be
    deleted or moved to another school, and the person clicking the link
    should meet an honest 404 rather than an enrolment on something that
    is no longer there.
    """
    invitation = get_invitation_by_token(db, token)

    if invitation.status != InvitationStatus.PENDING.value:
        increment("equip.invitations.refused_total", reason="already_used", scope=invitation.scope)
        raise equip_error(
            ErrorCode.INVITATION_ALREADY_USED,
            status_code=status.HTTP_409_CONFLICT,
            message="This invitation has already been used",
            context={"resource_type": "invitation"},
        )
    if is_invitation_expired(invitation):
        increment("equip.invitations.refused_total", reason="expired", scope=invitation.scope)
        raise equip_error(
            ErrorCode.INVITATION_EXPIRED,
            status_code=status.HTTP_410_GONE,
            message="This invitation has expired",
            context={"resource_type": "invitation"},
        )
    if invitation.email != current_user_email.strip().lower():
        increment("equip.invitations.refused_total", reason="email_mismatch", scope=invitation.scope)
        raise equip_error(
            ErrorCode.INVITATION_EMAIL_MISMATCH,
            status_code=status.HTTP_403_FORBIDDEN,
            message="This invitation was sent to a different email address",
            context={"resource_type": "invitation"},
        )

    # Everything that can refuse comes before anything that changes.
    # The course is re-checked here even though creation checked it:
    # seven days is long enough for it to be deleted or moved, and a
    # person meeting a 404 must not also lose their invitation to it.
    course = (
        course_of_organization(db, invitation.course_id or "", invitation.organization_id)
        if invitation.scope == InvitationScope.COURSE.value
        else None
    )

    # Single-use guard: only flips a row still 'pending'. A concurrent
    # accept (double click, retried request) loses the race here rather
    # than in application logic.
    updated = (
        db.query(Invitation)
        .filter(Invitation.id == invitation.id, Invitation.status == InvitationStatus.PENDING.value)
        .update(
            {Invitation.status: InvitationStatus.ACCEPTED.value, Invitation.accepted_at: datetime.now(UTC)},
            synchronize_session="fetch",
        )
    )
    if updated == 0:
        # Lost the race rather than arrived late: two devices, one token.
        increment("equip.invitations.refused_total", reason="lost_race", scope=invitation.scope)
        raise equip_error(
            ErrorCode.INVITATION_ALREADY_USED,
            status_code=status.HTTP_409_CONFLICT,
            message="This invitation has already been used",
            context={"resource_type": "invitation"},
        )

    user = db.query(User).filter(User.id == current_user_id).first()
    if user is None:
        # The session says who they are and the row says otherwise: a
        # deleted account holding a live token. Nothing to grant.
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Account not found",
            context={"resource_type": "user"},
        )

    previous_role = user.role
    previous_organization_id = user.organization_id
    granted_role = higher_role(previous_role, invitation.role)

    changes: dict[Any, Any] = {}
    if granted_role != previous_role:
        changes[User.role] = granted_role
    if invitation.scope != InvitationScope.PLATFORM.value:
        changes[User.organization_id] = invitation.organization_id
    if course is not None and user.onboarding_completed_at is None:
        # First-run exists to turn an empty dashboard into a course to
        # open, and the invitation is about to do exactly that. Left
        # unset, it sent an invited student to a picker to choose the
        # course they had already been enrolled on.
        #
        # Only the picker is skipped. Legal consent is a separate gate,
        # checked before this flag is ever read, and untouched here.
        changes[User.onboarding_completed_at] = datetime.now(UTC)

    if changes:
        db.query(User).filter(User.id == current_user_id).update(changes)

    enrolled_course_id: str | None = None
    if course is not None:
        enroll_user_in_course(db, current_user_id, course.id, commit=False)
        enrolled_course_id = course.id

    db.commit()
    db.refresh(invitation)

    increment(
        "equip.invitations.accepted_total",
        scope=invitation.scope,
        role=granted_role,
        # Whether the invitation actually moved the person's role, which
        # is the difference between "a new teacher" and "somebody who
        # was already one accepting a course invitation".
        role_changed=str(granted_role != previous_role).lower(),
        joined_organization=str(previous_organization_id != invitation.organization_id).lower(),
    )
    # How long an invitation sits before it is used. The tail of this is
    # what tells us a seven-day life is too short or too long.
    if invitation.created_at is not None:
        created = invitation.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        timing(
            "equip.invitations.time_to_accept_ms",
            (datetime.now(UTC) - created).total_seconds() * 1000,
            scope=invitation.scope,
        )

    log_action(
        db,
        current_user_id,
        "accept",
        "invitation",
        str(invitation.id),
        details={
            "scope": invitation.scope,
            "role": granted_role,
            # Both sides of every move, because "what did accepting this
            # actually change" is the question an audit row is kept for.
            "previous_role": previous_role,
            "organization_id": str(invitation.organization_id)
            if invitation.scope != InvitationScope.PLATFORM.value
            else None,
            "previous_organization_id": str(previous_organization_id) if previous_organization_id else None,
            "enrolled_course_id": enrolled_course_id,
        },
        request=request,
    )

    return invitation
