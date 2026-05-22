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

import asyncio
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
    # Admin-mutation buckets. A compromised admin token falls under the
    # global 100/60s default otherwise, which is enough for an attacker
    # to script delete-100-users-per-minute. These per-prefix ceilings
    # are still generous for legitimate admin use (typing through 30
    # role changes a minute is unusual; deleting 30 users a minute is
    # very unusual). Reads on these prefixes also share the bucket --
    # that's a small UX cost for the safety net.
    "/api/v1/users/admin/": (30, 60),
    "/api/v1/cohorts": (60, 60),
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
        # Starlette BaseHTTPMiddleware runs ``dispatch`` concurrently for
        # overlapping requests on the same worker. Without a lock, two
        # requests can both read ``len(hits) < max_calls`` and both
        # append, briefly exceeding the cap. The same window also makes
        # ``X-RateLimit-Remaining`` racy. One asyncio.Lock around the
        # read-prune-check-append section serializes the hot path while
        # leaving the await on ``call_next`` outside the lock so
        # downstream handlers stay fully concurrent.
        self._lock = asyncio.Lock()

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

        async with self._lock:
            self._cleanup_stale_buckets(now)

            pruned = [t for t in self._hits[bucket_key] if t > cutoff]
            if len(pruned) >= max_calls:
                # Reassign so the cleanup loop sees the pruned state too.
                self._hits[bucket_key] = pruned
                return Response(
                    content='{"detail":"Too many requests"}',
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": str(window)},
                )
            pruned.append(now)
            self._hits[bucket_key] = pruned
            # Capture the post-append count under the lock so the
            # header value matches the same snapshot the gate used.
            remaining = max(0, max_calls - len(pruned))

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_calls)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
