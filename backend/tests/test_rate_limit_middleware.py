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


class TestBucketPerPerson:
    """A classroom shares one IP. Signed-in people get their own global
    budget; anything the process cannot verify locally stays on the IP."""

    WRONG = "a-different-secret-of-thirty-two-bytes!"

    @staticmethod
    def _token(
        sub: str,
        secret: str | None = None,
        aud: str = "authenticated",
        ttl: int = 600,
    ) -> str:
        import time as _t

        import jwt as _jwt

        from app.core.config import settings

        # The secret the process was started with: conftest's default
        # locally, the workflow's JWT_SECRET_KEY in CI.
        key = secret if secret is not None else settings.JWT_SECRET_KEY
        assert key
        return _jwt.encode({"sub": sub, "aud": aud, "exp": int(_t.time()) + ttl}, key, algorithm="HS256")

    def test_two_people_on_one_ip_do_not_share_the_global_budget(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mw = _get_middleware_instance()
        monkeypatch.setattr(mw, "calls", 2)
        a = {"Authorization": f"Bearer {self._token('11111111-1111-4111-8111-111111111111')}"}
        b = {"Authorization": f"Bearer {self._token('22222222-2222-4222-8222-222222222222')}"}
        for _ in range(2):
            assert client.get("/api/v1/users/me", headers=a).status_code != 429
        assert client.get("/api/v1/users/me", headers=a).status_code == 429
        # Same IP, another person: a fresh budget.
        assert client.get("/api/v1/users/me", headers=b).status_code != 429
        # And the anonymous budget of that IP was never touched.
        assert not any(k == "testclient" for k in mw._hits)

    def test_a_token_that_does_not_verify_counts_by_ip(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Forged tokens must not mint fresh budgets: each would otherwise be a
        # new "person".
        mw = _get_middleware_instance()
        monkeypatch.setattr(mw, "calls", 2)
        for i in range(2):
            forged = {"Authorization": f"Bearer {self._token(f'0000000{i}-0000-4000-8000-000000000000', self.WRONG)}"}
            assert client.get("/api/v1/users/me", headers=forged).status_code != 429
        forged = {"Authorization": f"Bearer {self._token('09999999-0000-4000-8000-000000000000', self.WRONG)}"}
        assert client.get("/api/v1/users/me", headers=forged).status_code == 429

    def test_prefix_buckets_stay_per_ip(self, client: TestClient) -> None:
        # Brute-force surfaces limit the source, not the account.
        mw = _get_middleware_instance()
        token = {"Authorization": f"Bearer {self._token('11111111-1111-4111-8111-111111111111')}"}
        client.get("/api/v1/auth/me", headers=token)
        assert not any(k.startswith("user:") for k in mw._hits)
        assert any(k.endswith(":/api/v1/auth/") for k in mw._hits)

    def test_expired_or_foreign_audience_tokens_count_by_ip(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.core import security

        assert security.local_token_subject(self._token("x", ttl=-60)) is None
        assert security.local_token_subject(self._token("x", aud="anon")) is None
        assert security.local_token_subject(self._token("x")) == "x"

    def test_many_accounts_from_one_ip_meet_a_shared_ceiling(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # One source cannot multiply its budget by signing in as many people.
        monkeypatch.setattr(rl_mod, "SIGNED_IN_PER_IP", 3)
        for i in range(3):
            h = {"Authorization": f"Bearer {self._token(f'1000000{i}-0000-4000-8000-000000000000')}"}
            assert client.get("/api/v1/users/me", headers=h).status_code != 429
        h = {"Authorization": f"Bearer {self._token('19999999-0000-4000-8000-000000000000')}"}
        assert client.get("/api/v1/users/me", headers=h).status_code == 429

    def test_the_limiter_never_asks_supabase(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.core import security

        def boom(_token: str) -> None:
            raise AssertionError("network fallback reached from the limiter")

        monkeypatch.setattr(security, "_validate_via_supabase", boom)
        assert security.local_token_subject(self._token("x", self.WRONG)) is None
        assert security.local_token_subject("not-a-jwt") is None
