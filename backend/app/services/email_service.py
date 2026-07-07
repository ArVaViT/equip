"""Direct backend -> Resend transactional email.

``supabase/functions/send-email`` is a Supabase Auth "send email" webhook
hook -- it only fires for Auth lifecycle events (signup/recovery/
magic_link/email_change) carrying a signed payload from Supabase Auth
itself. An invitation is not an Auth event, so it can't go through that
hook. This module calls the Resend API directly instead, mirroring that
edge function's brand styling (``BRAND`` / ``FROM`` / the inline CSS
constants) so invite emails look consistent with the rest of Equip's mail.

Failure here is non-blocking by design, same rationale as the edge
function: a Resend hiccup (or a missing ``RESEND_API_KEY`` in a preview
deployment) must not fail invite *creation* -- the row and token already
exist, an admin can re-trigger the send via the resend path, and the
accept link still works if shared manually.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_RESEND_URL = "https://api.resend.com/emails"
_BRAND = "Equip"
_FROM = "Equip <noreply@equipbible.com>"
_BTN_STYLE = (
    "display: inline-block; background: #2563eb; color: #fff; text-decoration: none; "
    "padding: 12px 32px; border-radius: 8px; font-weight: 600; margin: 24px 0;"
)
_WRAP_STYLE = (
    "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; "
    "max-width: 560px; margin: 0 auto; padding: 40px 20px;"
)
_H1_STYLE = "color: #1a1a2e; font-size: 24px; margin-bottom: 16px;"
_P_STYLE = "color: #4a4a6a; font-size: 16px; line-height: 1.6;"
_SMALL_STYLE = "color: #8888a8; font-size: 13px;"

_ROLE_LABEL = {"teacher": "teacher", "student": "student"}


def _invitation_html(role: str, accept_url: str) -> str:
    role_label = _ROLE_LABEL.get(role, role)
    return f"""
      <div style="{_WRAP_STYLE}">
        <h1 style="{_H1_STYLE}">You're invited to {_BRAND}</h1>
        <p style="{_P_STYLE}">You've been invited to join {_BRAND} as a {role_label}. Click below to accept the invitation and set up your account.</p>
        <a href="{accept_url}" style="{_BTN_STYLE}">Accept Invitation</a>
        <p style="{_SMALL_STYLE}">This invitation expires in 7 days. If you weren't expecting this, you can safely ignore this email.</p>
      </div>
    """


def send_invitation_email(*, to_email: str, role: str, accept_url: str) -> bool:
    """Send the invite email via Resend. Returns whether it was sent.

    Never raises -- a delivery failure is logged and swallowed so the
    invite row (and its usable token/link) still exists regardless of
    whether the actual email got out. Callers should not treat a
    ``False`` return as invite creation having failed.
    """
    api_key = settings.RESEND_API_KEY.get_secret_value() if settings.RESEND_API_KEY else None
    if not api_key:
        logger.warning("RESEND_API_KEY not configured; skipping invitation email to %s", to_email)
        return False

    role_label = _ROLE_LABEL.get(role, role)
    try:
        resp = httpx.post(
            _RESEND_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "from": _FROM,
                "to": [to_email],
                "subject": f"You're invited to join {_BRAND} as a {role_label}",
                "html": _invitation_html(role, accept_url),
            },
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        logger.warning("Resend delivery failed for invitation to %s: %s", to_email, exc)
        return False

    if resp.status_code >= 400:
        logger.warning("Resend rejected invitation email to %s: %s %s", to_email, resp.status_code, resp.text)
        return False
    return True
