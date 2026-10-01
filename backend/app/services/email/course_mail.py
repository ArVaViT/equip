"""Course mail: the kinds a person can turn off, and the link that turns one off.

The privacy policy says it in so many words (backend/app/legal/documents/
privacy.*.md, "Email the platform sends"): course mail and notifications
"can be turned off in your profile, and every such message carries an
unsubscribe link". Account mail — confirming an address, resetting a
password, an invitation — is the other kind, and never passes through here:
it cannot be turned off, because without it an account cannot be used.

Every course mail goes through :func:`send_course_mail`, which is the whole
promise in one place:

* the person's choice is read before anything is built for sending
  (``profiles.email_off``, a list of kinds; empty means everything);
* the message carries an unsubscribe link for its own kind, in the body
  and in the ``List-Unsubscribe`` headers Gmail and Yahoo require of a
  sender that wants to stay out of spam (RFC 8058 one-click);
* it never raises — the action that caused the mail has already happened.

The link is a signed token (``sub`` = the person, ``kind`` = the mail kind),
not a login: unsubscribing must work from a phone that has never signed in,
and from the mail client's own button. It does not expire — a link in an
old message must still work — and it can do exactly one thing: turn one kind
of mail off for one person.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING, Final, Literal, get_args
from urllib.parse import quote

import jwt

from app.core.config import settings
from app.core.i18n import t
from app.services.email.render import render, render_text
from app.services.email.send import Delivery, send_email

if TYPE_CHECKING:
    from app.models.user import User
    from app.schemas.locale import LocaleCode
    from app.services.email.render import Message

logger = logging.getLogger(__name__)

#: The kinds the policy names, in its order. The database holds the same
#: list in ``profiles_email_off_check``; a new kind is a value added to both.
MailKind = Literal["work_returned", "certificate_decided", "session_starting", "deadline_moved", "announcement"]
KINDS: Final[tuple[MailKind, ...]] = get_args(MailKind)

_AUDIENCE = "equip-unsubscribe"


def wants(person: User, kind: MailKind) -> bool:
    """Whether ``person`` still gets ``kind``. An address and a live account are checked too."""
    if not person.email or person.deactivated_at is not None:
        return False
    return kind not in (person.email_off or [])


def unsubscribe_token(person_id: str, kind: MailKind) -> str:
    """A token that turns ``kind`` off for ``person_id`` and can do nothing else."""
    if not settings.JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is not configured")
    return jwt.encode(
        {"sub": person_id, "kind": kind, "aud": _AUDIENCE},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def read_unsubscribe_token(token: str) -> tuple[str, MailKind] | None:
    """``(person_id, kind)`` for a valid token, ``None`` for anything else."""
    if not settings.JWT_SECRET_KEY or not token:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience=_AUDIENCE,
        )
    except jwt.PyJWTError as exc:
        logger.info("unsubscribe token rejected: %s", type(exc).__name__)
        return None
    sub, kind = payload.get("sub"), payload.get("kind")
    if not isinstance(sub, str) or kind not in KINDS:
        return None
    return sub, kind


def unsubscribe_page_url(token: str) -> str:
    """The page a person lands on from the link in the body: it asks, then turns the kind off.

    A page with a button, never a GET that unsubscribes: mail scanners open
    every link in a message, and would turn people's mail off for them.
    """
    return f"{settings.FRONTEND_URL.rstrip('/')}/unsubscribe?token={quote(token)}"


def one_click_url(token: str) -> str:
    """Where a mail client POSTs ``List-Unsubscribe=One-Click`` (RFC 8058)."""
    return f"{settings.API_PUBLIC_URL.rstrip('/')}/api/v1/email/unsubscribe?token={quote(token)}"


def send_course_mail(
    *,
    person: User,
    kind: MailKind,
    locale: LocaleCode,
    message: Message,
    subject: str,
    sender_name: str | None = None,
) -> Delivery | None:
    """Send one course mail, if the person still wants this kind. Never raises.

    ``None`` when nothing was attempted (the kind is off, no address, a
    closed account, or the link could not be signed); a ``Delivery``
    otherwise.
    """
    try:
        if not wants(person, kind):
            return None
        token = unsubscribe_token(str(person.id), kind)
        message = replace(
            message,
            unsubscribe_label=t(locale, f"email.unsubscribe.{kind}"),
            unsubscribe_url=unsubscribe_page_url(token),
        )
        headers = {
            "List-Unsubscribe": f"<{one_click_url(token)}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }
        return send_email(
            to=person.email,
            subject=subject,
            html=render(message),
            text=render_text(message),
            kind=kind,
            sender_name=sender_name,
            headers=headers,
        )
    except Exception:
        logger.exception("course mail %s: could not be sent to person %s", kind, person.id)
        return None
