"""The one place the backend hands a message to Resend.

Three properties, each of which used to be somebody's one-off:

* **Delivery never fails the action.** An invitation exists whether or
  not its mail got out; the row and the token are already there and the
  link works if an admin shares it by hand. So this returns an outcome
  and never raises.
* **The telemetry says the domain, not the person.** The edge function
  has logged ``recipient_domain`` since it was written; the backend
  logged the full address at WARNING, which then went to Datadog. Same
  rule on both sides now.
* **There is a timeout.** Ten seconds, because this runs inside a
  request a person is waiting on.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from time import perf_counter

import httpx

from app.core.config import settings
from app.core.metrics import increment, timing

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"
#: Not configurable, and deliberately in one place: the domain is
#: verified with the provider and the DNS records are cut for it.
FROM_ADDRESS = "noreply@equipbible.com"
FROM = f"Equip <{FROM_ADDRESS}>"
_TIMEOUT_SECONDS = 10.0
#: Characters a display name may not carry into a header.
_FORBIDDEN_IN_A_NAME = frozenset('"\\<>\r\n\t')
#: Long enough for any real name, short of a header a client truncates.
_NAME_LIMIT = 64


def _from_header(sender_name: str | None) -> str:
    """Who the message is from, as a mail client shows it.

    "Equip" alone is a system nobody recognises. "Dmytro Kostantynov
    via Equip" is a person the reader knows, next to the product that
    sent it — the shape Google and the rest have used for years, and
    the one a spam filter has seen a billion times. The address stays
    the verified one; only the display name changes, so SPF, DKIM and
    DMARC are untouched.
    """
    if not sender_name:
        return FROM
    # The name is typed by a person and lands in a header, so it is
    # stripped down to what a display name may contain: quotes and
    # backslashes would close ours early, angle brackets would look
    # like a second address, and a newline would start a header of the
    # attacker's choosing.
    cleaned = "".join(" " if character in _FORBIDDEN_IN_A_NAME else character for character in sender_name)
    cleaned = " ".join(cleaned.split())[:_NAME_LIMIT].strip()
    return f'"{cleaned} via Equip" <{FROM_ADDRESS}>' if cleaned else FROM


@dataclass(frozen=True)
class Delivery:
    """What happened, in terms a caller or a log line can act on."""

    sent: bool
    #: Provider id when it took the message; the closest thing to a
    #: receipt until the deliveries table exists (ADR-012, step 4).
    provider_id: str | None = None
    #: Machine-readable: not_configured | http_error | rejected | ok.
    reason: str = "ok"


def _domain_of(address: str) -> str:
    _, _, domain = address.rpartition("@")
    return domain or "unknown"


def send_email(
    *,
    to: str,
    subject: str,
    html: str,
    kind: str,
    text: str | None = None,
    sender_name: str | None = None,
    reply_to: str | None = None,
) -> Delivery:
    """Hand one message to the provider.

    ``kind`` is the message type ("invitation"), carried into telemetry
    so a failure can be attributed without reading the body.

    ``text`` is the plain-text alternative, and it is not optional in
    spirit. Left out, the provider derives one by stripping tags, and a
    table-based layout comes back as "First session2026-09-12, 20:00
    EasternLessons4" — unreadable for anyone whose client prefers text,
    and a poor signal to every filter that reads it. Measured on a real
    message on 2026-09-12, which is how it was found.

    ``reply_to`` is the inviting person's own address. A message nobody
    can answer is a message a filter has every reason to distrust, and
    a person who replies "is this really you?" should reach a human.
    """
    if settings.RESEND_API_KEY is None or not settings.RESEND_API_KEY.get_secret_value():
        # A deployment without the key is a real configuration (preview
        # builds, local work), not an error to raise on a person.
        logger.warning("email skipped: no RESEND_API_KEY (kind=%s domain=%s)", kind, _domain_of(to))
        increment("equip.email.attempts_total", kind=kind, outcome="not_configured")
        return Delivery(sent=False, reason="not_configured")

    started = perf_counter()
    try:
        response = httpx.post(
            _RESEND_URL,
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY.get_secret_value()}",
                "Content-Type": "application/json",
            },
            json={
                "from": _from_header(sender_name),
                "to": [to],
                "subject": subject,
                "html": html,
                **({"text": text} if text else {}),
                **({"reply_to": reply_to} if reply_to else {}),
            },
            timeout=_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        logger.warning("email transport failed (kind=%s domain=%s): %s", kind, _domain_of(to), type(exc).__name__)
        increment("equip.email.attempts_total", kind=kind, outcome="http_error", error=type(exc).__name__)
        return Delivery(sent=False, reason="http_error")

    if response.status_code >= 400:
        logger.warning(
            "email rejected by provider (kind=%s domain=%s status=%s)",
            kind,
            _domain_of(to),
            response.status_code,
        )
        increment(
            "equip.email.attempts_total",
            kind=kind,
            outcome="rejected",
            status_code=str(response.status_code),
        )
        return Delivery(sent=False, reason="rejected")

    provider_id = None
    # A 2xx with a body we cannot parse still delivered the message.
    with contextlib.suppress(ValueError):
        provider_id = response.json().get("id")
    logger.info("email sent (kind=%s domain=%s id=%s)", kind, _domain_of(to), provider_id)
    increment("equip.email.attempts_total", kind=kind, outcome="sent")
    # How long a person waits on the provider inside their own request.
    timing("equip.email.provider_ms", (perf_counter() - started) * 1000, kind=kind)
    return Delivery(sent=True, provider_id=provider_id)
