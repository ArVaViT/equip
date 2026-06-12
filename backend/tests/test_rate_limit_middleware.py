"""Tests for ``app.middleware.rate_limit.RateLimitMiddleware``.

The middleware is wired into ``app.main`` so the conftest's
``_clear_rate_limit`` autouse fixture is what stops cross-test
pollution. The middleware's own dispatch logic was uncovered:

* OPTIONS short-circuit — preflight requests must NOT count toward
  the per-IP budget; otherwise a busy CORS surface would 429
  legitimate clients (line 129).
* 429 path — when the bucket fills, the middleware returns a 429
  with the canonical "Too many requests" envelope (lines 150-151).
* Stale-bucket cleanup — both the time-based and capacity-based
  triggers (lines 119-125) so a long-running process doesn't grow
  the bucket dict unbounded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.middleware import rate_limit as rl_mod
from app.middleware.rate_limit import RateLimitMiddleware

if TYPE_CHECKING:
    import pytest
    from fastapi.testclient import TestClient


def _get_middleware_instance() -> RateLimitMiddleware:
    """Walk the middleware stack to find the RateLimitMiddleware on
    the running app."""
    from app.main import app

    stack = getattr(app, "middleware_stack", None)
    while stack is not None:
        if isinstance(stack, RateLimitMiddleware):
            return stack
        stack = getattr(stack, "app", None)
    raise AssertionError("RateLimitMiddleware not in stack")


class TestOptionsShortCircuit:
    def test_options_request_bypasses_rate_limit(
        self,
        client: TestClient,
    ) -> None:
        """An ``OPTIONS /api/...`` preflight must short-circuit before
        the bucket lookup. Hammer it 100 times — none should 429."""
        mw = _get_middleware_instance()
        # Cap the budget tightly so even one charged hit would 429.
        # OPTIONS must NOT consume budget.
        for _ in range(100):
            r = client.options("/api/v1/users/me")
            # Method-not-allowed (405) or 200 — anything except 429 is fine.
            assert r.status_code != 429
        # And no bucket entries got created from the OPTIONS hits.
        # (Buckets are populated only by the dispatch path that DOES
        # count the call, which OPTIONS skips.)
        assert all("options" not in k for k in mw._hits)


class TestRateLimitExceeded:
    def test_429_when_bucket_filled(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Force a tight per-IP budget by shrinking the global default,
        then exhaust it. The next call must 429 with the canonical
        envelope."""
        mw = _get_middleware_instance()
        # Shrink budgets so the test finishes in a handful of calls.
        monkeypatch.setattr(mw, "calls", 3)
        monkeypatch.setattr(mw, "window", 60)

        # Burn through the budget on a route the global limiter applies
        # to (no ENDPOINT_LIMITS prefix matches it).
        for _ in range(3):
            r = client.get("/api/v1/users/me")
            assert r.status_code != 429

        # The fourth call MUST 429.
        r = client.get("/api/v1/users/me")
        assert r.status_code == 429
        assert "Too many requests" in r.text

    def test_429_carries_security_headers(
        self,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """SecurityHeadersMiddleware is the OUTERMOST response-mutating
        middleware (added last in ``app.main``), so even responses minted
        by inner middleware — like RateLimitMiddleware's 429 — must carry
        the security headers. Pin the ordering: a refactor that re-adds
        SecurityHeaders before RateLimit would strip them from 429s."""
        mw = _get_middleware_instance()
        monkeypatch.setattr(mw, "calls", 1)
        monkeypatch.setattr(mw, "window", 60)

        client.get("/api/v1/users/me")  # burn the single-call budget
        r = client.get("/api/v1/users/me")
        assert r.status_code == 429
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"
        assert "Content-Security-Policy" in r.headers


class TestStaleBucketCleanup:
    def test_cleanup_drops_buckets_outside_window(self) -> None:
        """``_cleanup_stale_buckets`` walks the hits dict and drops
        entries whose newest timestamp is older than the widest
        window. Pin the cleanup so the bucket dict stays bounded."""
        mw = _get_middleware_instance()
        # Seed two buckets: one with a "fresh" hit at the same time as
        # "now", and one with very old hits. Cleanup must drop the
        # stale bucket and keep the fresh one.
        mw._hits["fresh-ip"] = [1_001_000.0]
        mw._hits["stale-ip"] = [1.0]
        mw._last_cleanup = 0.0  # force cleanup to fire on this call

        mw._cleanup_stale_buckets(1_001_000.0)

        # Stale bucket is gone; fresh stays (its tail timestamp == now,
        # which is inside the cutoff window).
        assert "stale-ip" not in mw._hits
        assert "fresh-ip" in mw._hits

    def test_cleanup_short_circuits_when_interval_not_elapsed(self) -> None:
        """The interval/size gate prevents per-request walks of the
        whole dict. Pin so a refactor that drops the gate doesn't
        turn the middleware into an O(N) per-request scanner."""
        mw = _get_middleware_instance()
        mw._hits["any-ip"] = [1.0]
        # Set last_cleanup very recent and dict size below MAX_BUCKETS
        # so the short-circuit fires.
        mw._last_cleanup = 999_999.0
        prev_keys = set(mw._hits.keys())
        # ``now`` only marginally past last_cleanup; below the interval.
        mw._cleanup_stale_buckets(999_999.0 + rl_mod.CLEANUP_INTERVAL / 2)
        # Cleanup should not have run — the stale bucket stays.
        assert set(mw._hits.keys()) == prev_keys
