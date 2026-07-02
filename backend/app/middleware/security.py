from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import env_flag

# The API only ever serves JSON (or binary blobs via StreamingResponse). It
# should never execute scripts or load styles, so we lock CSP down as hard as
# possible. The frontend ships its own CSP from Vercel; this one is purely
# defence-in-depth for the raw API surface.
_STRICT_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

# HSTS on plain HTTP (local dev) has no effect unless the browser later sees
# the same host over HTTPS — but if a dev ever points a real hostname at a
# local tunnel, HSTS could pin the browser to HTTPS in confusing ways. Only
# advertise it in hosted environments.
_IS_PRODUCTION = env_flag("VERCEL", "PRODUCTION")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds standard security headers to every response."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "0"
        if _IS_PRODUCTION:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-site"
        response.headers["Content-Security-Policy"] = _STRICT_API_CSP
        return response
