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

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"
#: Not configurable, and deliberately in one place: the domain is
#: verified with the provider and the DNS records are cut for it.
FROM = "Equip <noreply@equipbible.com>"
_TIMEOUT_SECONDS = 10.0


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


def send_email(*, to: str, subject: str, html: str, kind: str) -> Delivery:
    """Hand one message to the provider.

    ``kind`` is the message type ("invitation"), carried into telemetry
    so a failure can be attributed without reading the body.
    """
    if settings.RESEND_API_KEY is None or not settings.RESEND_API_KEY.get_secret_value():
        # A deployment without the key is a real configuration (preview
        # builds, local work), not an error to raise on a person.
        logger.warning("email skipped: no RESEND_API_KEY (kind=%s domain=%s)", kind, _domain_of(to))
        return Delivery(sent=False, reason="not_configured")

    try:
        response = httpx.post(
            _RESEND_URL,
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY.get_secret_value()}",
                "Content-Type": "application/json",
            },
            json={"from": FROM, "to": [to], "subject": subject, "html": html},
            timeout=_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        logger.warning("email transport failed (kind=%s domain=%s): %s", kind, _domain_of(to), type(exc).__name__)
        return Delivery(sent=False, reason="http_error")

    if response.status_code >= 400:
        logger.warning(
            "email rejected by provider (kind=%s domain=%s status=%s)",
            kind,
            _domain_of(to),
            response.status_code,
        )
        return Delivery(sent=False, reason="rejected")

    provider_id = None
    # A 2xx with a body we cannot parse still delivered the message.
    with contextlib.suppress(ValueError):
        provider_id = response.json().get("id")
    logger.info("email sent (kind=%s domain=%s id=%s)", kind, _domain_of(to), provider_id)
    return Delivery(sent=True, provider_id=provider_id)
