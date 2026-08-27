from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import status

from app.core.config import settings
from app.core.errors import ErrorCode, equip_error
from app.models.invitation import Invitation, InvitationStatus
from app.models.user import User
from app.schemas.locale import LocaleCode  # noqa: TC001 — annotation is evaluated at runtime by FastAPI
from app.services.audit_service import log_action
from app.services.email_service import send_invitation_email
from app.services.user_locale import preferred_locale_of

if TYPE_CHECKING:
    import uuid
    from uuid import UUID

    from fastapi import Request
    from sqlalchemy.orm import Session

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


def create_or_resend_invitation(
    db: Session,
    *,
    email: str,
    role: str,
    invited_by: UUID,
    organization_id: UUID,
    request: Request | None = None,
) -> tuple[Invitation, bool]:
    """Create a new invitation, or resend the existing pending one.

    Returns ``(invitation, is_new)``. Dedup key is ``(email, role)`` while
    ``status == 'pending'`` -- mirrors the partial unique index in the
    migration, which is the real race guard; this lookup is the
    happy-path short-circuit that avoids hitting it on a normal "resend"
    click. A resend does NOT rotate the token or reset ``expires_at`` --
    a link already shared/clicked stays valid on its original clock.

    An expired-but-still-``pending`` row is revoked first so the fresh
    insert doesn't collide with the partial unique index.
    """
    normalized_email = email.strip().lower()

    existing = (
        db.query(Invitation)
        .filter(
            Invitation.email == normalized_email,
            Invitation.role == role,
            Invitation.status == InvitationStatus.PENDING.value,
        )
        .first()
    )
    if existing is not None and not is_invitation_expired(existing):
        send_invitation_email(
            to_email=normalized_email,
            role=role,
            accept_url=_accept_url(existing.token),
            locale=_inviter_locale(db, invited_by),
        )
        return existing, False

    if existing is not None:
        existing.status = InvitationStatus.REVOKED.value

    invitation = Invitation(
        organization_id=organization_id,
        email=normalized_email,
        role=role,
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
        details={"email": normalized_email, "role": role},
        request=request,
    )

    send_invitation_email(
        to_email=normalized_email,
        role=role,
        accept_url=_accept_url(invitation.token),
        locale=_inviter_locale(db, invited_by),
    )
    return invitation, True


def list_invitations(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 50,
    role: str | None = None,
    status_filter: str | None = None,
) -> list[Invitation]:
    query = db.query(Invitation)
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


def accept_invitation(
    db: Session,
    *,
    token: str,
    current_user_id: UUID,
    current_user_email: str,
    request: Request | None = None,
) -> Invitation:
    """Redeem a token: validate, atomically flip it to accepted, then
    promote the caller's role.

    The caller must already be authenticated as a user whose email
    matches the invitation -- see the migration/module docstrings for why
    the backend doesn't mint the Supabase Auth user itself. Role
    promotion piggybacks on the same DB session/commit as the invitation
    UPDATE isn't strictly atomic with it (two statements), but the
    single-use guard (UPDATE ... WHERE status='pending') is what prevents
    a double-redeem; a crash between the two commits leaves, at worst, an
    accepted invitation with the role not yet flipped, which is safely
    retryable (accept is idempotent for the row's owner: hitting it again
    just meets `already_used` -- to recover, an admin can re-invite).
    """
    invitation = get_invitation_by_token(db, token)

    if invitation.status != InvitationStatus.PENDING.value:
        raise equip_error(
            ErrorCode.INVITATION_ALREADY_USED,
            status_code=status.HTTP_409_CONFLICT,
            message="This invitation has already been used",
            context={"resource_type": "invitation"},
        )
    if is_invitation_expired(invitation):
        raise equip_error(
            ErrorCode.INVITATION_EXPIRED,
            status_code=status.HTTP_410_GONE,
            message="This invitation has expired",
            context={"resource_type": "invitation"},
        )
    if invitation.email != current_user_email.strip().lower():
        raise equip_error(
            ErrorCode.INVITATION_EMAIL_MISMATCH,
            status_code=status.HTTP_403_FORBIDDEN,
            message="This invitation was sent to a different email address",
            context={"resource_type": "invitation"},
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
        raise equip_error(
            ErrorCode.INVITATION_ALREADY_USED,
            status_code=status.HTTP_409_CONFLICT,
            message="This invitation has already been used",
            context={"resource_type": "invitation"},
        )

    db.query(User).filter(User.id == current_user_id).update({User.role: invitation.role})
    db.commit()
    db.refresh(invitation)

    log_action(
        db,
        current_user_id,
        "accept",
        "invitation",
        str(invitation.id),
        details={"role": invitation.role},
        request=request,
    )

    return invitation
