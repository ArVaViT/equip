"""Shared helpers for inspecting incoming HTTP requests.

Kept out of the middleware/service layers so that rate limiting, audit logging,
and anything else that needs a reliable client IP share one implementation.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

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
_TRUSTED_PROXY = bool(os.environ.get("VERCEL") or os.environ.get("TRUST_FORWARDED_HEADERS"))


def get_client_ip(request: Request, fallback: str | None = None) -> str | None:
    """Resolve the real client IP, honoring standard proxy-forwarding headers
    only when a trusted reverse proxy is in front of us.

    On Vercel (and any other configured reverse-proxy deploy)
    ``request.client.host`` is the proxy worker's IP, not the user's
    real IP. ``X-Forwarded-For`` is set by the proxy to ``<client>,
    <proxy>, <proxy>...`` (left-to-right), so the left-most entry is
    the original client; everything after is proxy chain.

    Outside that trusted-proxy environment we ignore both forwarded
    headers and use ``request.client.host`` directly — otherwise any
    client can spoof their IP per request and defeat per-IP throttling.
    Returns ``fallback`` when we truly cannot determine the IP (for the
    rate limiter, pass ``"unknown"``; for audit logging, pass ``None``
    so the DB column stays NULL).
    """
    if _TRUSTED_PROXY:
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
