"""HTTP rate limiting middleware.

## Design decision: in-memory + Vercel WAF, not Upstash Redis

We considered three strategies for rate limiting in this deployment:

1. **In-memory per-instance (current).** Simple, zero-dependency, no network
   round-trip. Drawback: Vercel serverless functions run on N independent
   workers, so an attacker distributing requests across cold workers sees
   ~N times the effective budget. For a ~100-user Equip app with no API
   keys to harvest, this is acceptable "defense-in-depth" — not a hard
   enforcement boundary.

2. **Upstash Redis / @vercel/kv.** Shared counter across all workers; true
   enforcement. Drawbacks: +$10/mo minimum, +5-10ms per request, and an
   extra SPOF in the critical path. Not justified at current scale.

3. **Vercel WAF / Edge rate limiting.** Runs before any function invocation,
   so it's free and catches bursts the in-memory limiter can't see. This is
   the recommended hard limit for `/api/v1/auth/*` in production. Configure
   via Vercel Dashboard → Firewall → Rate Limit Rules:
       - 10 requests / 60s for `/api/v1/auth/login` and `/auth/register`

Decision: keep this in-memory limiter as per-instance defense, point
production at Vercel WAF for the hard auth limits, and revisit
Upstash if the user count crosses 1000 active/day.

## IP detection

On Vercel (and any proxy-fronted deploy) `request.client.host` is the proxy
IP, NOT the user's real IP — so every user shares one bucket per worker
and the limiter is effectively disabled. We now read `X-Forwarded-For` first.
"""

import time
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.http import get_client_ip

# Per-endpoint overrides. Resolution is a longest-prefix-style ``startswith``
# (see ``_resolve_limit``), so any sub-route inherits the bucket of the closest
# matching prefix. Pick conservative ceilings for unauthenticated routes and
# anything that can be enumerated or that fans out to a paid upstream API.
#
# Limits in (max_calls, window_seconds) per client IP per bucket.
ENDPOINT_LIMITS: dict[str, tuple[int, int]] = {
    # Authenticated identity probe. Tight to keep token-brute attempts pricy.
    # Frontend hits this once per page load + on auth state change, so 10/min
    # is comfortably above legitimate usage.
    "/api/v1/auth/": (10, 60),
    # Unauthenticated certificate-number lookup. Each call enumerates one
    # value; cap at 30/min/IP so the verify page stays usable for the
    # legitimate share-your-credential flow while making bulk enumeration
    # impractical. Certificate numbers are random UUIDs already, so the cap
    # is defence-in-depth, not the primary control.
    "/api/v1/certificates/verify/": (30, 60),
    # Verse-of-the-day proxies through an upstream Bible API on cache miss.
    # The route is unauthenticated so it shows up on the marketing page in
    # the future; 60/min/IP is well above the once-per-page-load real use
    # case and prevents trivial cost-amplification attacks against the
    # upstream quota.
    "/api/v1/verse-of-the-day": (60, 60),
}

MAX_BUCKETS = 10_000
CLEANUP_INTERVAL = 300


class RateLimitMiddleware(BaseHTTPMiddleware):
    """In-memory rate limiter with per-endpoint overrides."""

    def __init__(self, app, calls: int = 100, window: int = 60):
        super().__init__(app)
        self.calls = calls
        self.window = window
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._last_cleanup: float = time.time()

    def _resolve_limit(self, path: str) -> tuple[str | None, int, int]:
        """Return ``(matched_prefix, max_calls, window)``.

        ``matched_prefix`` is the ``ENDPOINT_LIMITS`` key that matched
        ``path``, or ``None`` when no override matched and the global
        default applies. The caller uses the prefix (not the full path)
        as the per-IP bucket key so a brute-force enumeration of
        ``/certificates/verify/{cert_number}`` doesn't get a fresh budget
        for every guess — every guess from one IP shares one bucket.
        """
        for prefix, limit in ENDPOINT_LIMITS.items():
            if path.startswith(prefix):
                return prefix, *limit
        return None, self.calls, self.window

    def _cleanup_stale_buckets(self, now: float) -> None:
        if now - self._last_cleanup < CLEANUP_INTERVAL and len(self._hits) < MAX_BUCKETS:
            return
        self._last_cleanup = now
        max_window = max(w for _, w in ENDPOINT_LIMITS.values()) if ENDPOINT_LIMITS else self.window
        max_window = max(max_window, self.window)
        cutoff = now - max_window
        stale_keys = [k for k, v in self._hits.items() if not v or v[-1] < cutoff]
        for k in stale_keys:
            del self._hits[k]

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        client_ip = get_client_ip(request, fallback="unknown") or "unknown"
        path = request.url.path
        matched_prefix, max_calls, window = self._resolve_limit(path)

        # Bucket on the matched PREFIX, not the full path. ``/certificates/
        # verify/abc`` and ``/certificates/verify/xyz`` share one bucket per
        # IP — otherwise an attacker enumerating cert numbers gets a fresh
        # 30/min budget for every guess. Falls back to plain ``client_ip``
        # for the global limiter so unrelated routes still share one bucket.
        bucket_key = f"{client_ip}:{matched_prefix}" if matched_prefix else client_ip
        now = time.time()
        cutoff = now - window

        self._cleanup_stale_buckets(now)

        hits = self._hits[bucket_key]
        self._hits[bucket_key] = [t for t in hits if t > cutoff]

        if len(self._hits[bucket_key]) >= max_calls:
            return Response(
                content='{"detail":"Too many requests"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": str(window)},
            )

        self._hits[bucket_key].append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_calls)
        response.headers["X-RateLimit-Remaining"] = str(max(0, max_calls - len(self._hits[bucket_key])))
        return response
