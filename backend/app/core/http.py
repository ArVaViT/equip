"""Shared helpers for inspecting incoming HTTP requests.

Kept out of the middleware/service layers so that rate limiting, audit logging,
and anything else that needs a reliable client IP share one implementation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import env_flag

if TYPE_CHECKING:
    from fastapi import Request


# ``X-Forwarded-For`` is only trustworthy when we're behind a proxy that
# actively replaces it (Vercel does). On a bare deploy or local dev,
# clients can set the header themselves and farm fresh rate-limit
# buckets per spoofed IP. Gate the header on a trusted-proxy env signal
# so the unsafe path is opt-in rather than the default.
#
# Vercel sets ``VERCEL=1`` in every function invocation, and we also
# honour an explicit ``TRUST_FORWARDED_HEADERS=1`` for other reverse-
# proxy deployments (Cloudflare, custom Caddy/nginx, etc).
_TRUSTED_PROXY = env_flag("VERCEL", "TRUST_FORWARDED_HEADERS")


def get_client_ip(request: Request, fallback: str | None = None) -> str | None:
    """Resolve the real client IP, honoring standard proxy-forwarding headers
    only when a trusted reverse proxy is in front of us.

    On Vercel (and any other configured reverse-proxy deploy)
    ``request.client.host`` is the proxy worker's IP, not the user's
    real IP. We prefer ``x-vercel-forwarded-for``: Vercel sets it to the
    single, authoritative client IP and rewrites it on every request, so
    a client CANNOT spoof it. The standard ``x-forwarded-for`` is only a
    fallback — a client can PREPEND entries to it, so taking its left-most
    value would let an attacker farm a fresh rate-limit bucket per request.

    Outside that trusted-proxy environment we ignore the forwarded
    headers and use ``request.client.host`` directly — otherwise any
    client can spoof their IP per request and defeat per-IP throttling.
    Returns ``fallback`` when we truly cannot determine the IP (for the
    rate limiter, pass ``"unknown"``; for audit logging, pass ``None``
    so the DB column stays NULL).
    """
    if _TRUSTED_PROXY:
        # Authoritative, un-spoofable on Vercel — set by the platform.
        vercel_ip = request.headers.get("x-vercel-forwarded-for")
        if vercel_ip:
            ip = vercel_ip.split(",")[0].strip()
            if ip:
                return ip

        # Generic reverse-proxy fallback (Cloudflare/nginx/Caddy via
        # TRUST_FORWARDED_HEADERS). Left-most = original client when the
        # proxy is the one writing this header.
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            ip = forwarded.split(",")[0].strip()
            if ip:
                return ip

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()

    if request.client is not None and request.client.host:
        return request.client.host

    return fallback
