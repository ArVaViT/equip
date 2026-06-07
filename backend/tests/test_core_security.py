"""Unit tests for ``app.core.security``.

``decode_access_token`` is the choke-point through which every
authenticated request enters the application. It handles three distinct
trust paths:

1. **Local JWT verification** — when ``JWT_SECRET_KEY`` is configured,
   we decode + verify the token locally and trust it on a clean
   signature.
2. **Supabase fallback** — when the local secret is missing OR a
   Supabase-signed token does not match our local secret, we call
   ``GET /auth/v1/user`` and trust Supabase's own validation.
3. **Per-token cache** — repeated calls within the TTL hit a small
   in-process LRU so a page refresh doesn't fan out into N upstream
   calls.

The wired-up routes always come through these unit-tested paths via the
``get_current_user`` FastAPI dependency, so a regression here turns
into "every authenticated route silently 401s" — exactly the kind of
bug that's worth pinning at the lowest layer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import jwt as pyjwt

from app.core import security as core_security

if TYPE_CHECKING:
    import pytest


class _FakeHttpxResponse:
    def __init__(self, *, status_code: int, json_body: dict | None = None) -> None:
        self.status_code = status_code
        self._json_body = json_body or {}

    def json(self) -> dict:
        return self._json_body


def _clear_cache() -> None:
    core_security._supabase_cache.clear()


class TestCacheRoundTrip:
    """``_cache_get`` / ``_cache_put`` are private helpers but they
    carry the TTL + eviction invariants the public flow depends on.
    Pin both so a future refactor (e.g. swapping to ``cachetools``)
    has a tight regression net.
    """

    def test_put_then_get_hits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_cache()
        # Freeze ``time.monotonic`` so we can step it manually.
        clock = {"now": 100.0}
        monkeypatch.setattr(core_security.time, "monotonic", lambda: clock["now"])

        core_security._cache_put("tok-A", {"sub": "user-1"})
        clock["now"] = 130.0  # inside the TTL window (60s)
        assert core_security._cache_get("tok-A") == {"sub": "user-1"}

    def test_expired_entries_are_evicted_on_get(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_cache()
        clock = {"now": 100.0}
        monkeypatch.setattr(core_security.time, "monotonic", lambda: clock["now"])

        core_security._cache_put("tok-B", {"sub": "user-2"})
        clock["now"] = 200.0  # past TTL
        assert core_security._cache_get("tok-B") is None
        # And the entry is gone — the next get is also a miss.
        assert core_security._cache_get("tok-B") is None
        assert "tok-B" not in core_security._supabase_cache

    def test_get_miss_returns_none(self) -> None:
        _clear_cache()
        assert core_security._cache_get("never-put") is None

    def test_ttl_clamped_to_token_expiry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A token that expires in 5s must not stay cached for the full 60s
        window. The cache TTL is ``min(60, token_exp - now)``.
        """
        _clear_cache()
        monkeypatch.setattr(core_security.time, "time", lambda: 1000.0)
        clock = {"mono": 0.0}
        monkeypatch.setattr(core_security.time, "monotonic", lambda: clock["mono"])
        # Token expires 5s after "now" (1000 -> 1005).
        monkeypatch.setattr(core_security, "_token_exp_epoch", lambda _t: 1005.0)

        core_security._cache_put("tok-short", {"sub": "u"})
        clock["mono"] = 4.0  # within the token's 5s remaining life
        assert core_security._cache_get("tok-short") == {"sub": "u"}
        clock["mono"] = 6.0  # past token exp, but well under the 60s fixed TTL
        assert core_security._cache_get("tok-short") is None

    def test_eviction_when_cache_is_full(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When the cache hits ``_SUPABASE_CACHE_MAX_ENTRIES`` the next
        ``_cache_put`` drops the oldest entry (insertion-order FIFO via
        ``next(iter(...))``). Pin the behaviour at a tiny capacity so the
        test stays fast and the intent is obvious.
        """
        _clear_cache()
        monkeypatch.setattr(core_security, "_SUPABASE_CACHE_MAX_ENTRIES", 3)
        for i in range(3):
            core_security._cache_put(f"tok-{i}", {"sub": f"user-{i}"})
        assert len(core_security._supabase_cache) == 3
        # Fourth insert must evict ``tok-0`` (oldest), not any other key.
        core_security._cache_put("tok-3", {"sub": "user-3"})
        assert "tok-0" not in core_security._supabase_cache
        assert {"tok-1", "tok-2", "tok-3"} == set(core_security._supabase_cache.keys())


class TestSupabaseFallback:
    """``_validate_via_supabase`` is the bridge to Supabase's hosted
    auth. The DSL is "match the local-decode payload shape on success,
    return None on every other outcome". Cache writes happen ONLY on
    success — failed lookups must not poison the cache.
    """

    def test_returns_none_when_supabase_url_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_cache()
        monkeypatch.setattr(core_security.settings, "SUPABASE_URL", None)
        assert core_security._validate_via_supabase("tok") is None

    def test_success_returns_normalised_payload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_cache()
        monkeypatch.setattr(
            core_security.settings,
            "SUPABASE_URL",
            "https://proj.supabase.co",
        )
        monkeypatch.setattr(core_security.settings, "SUPABASE_SERVICE_ROLE_KEY", "sk-test")

        fake_resp = _FakeHttpxResponse(
            status_code=200,
            json_body={
                "id": "user-42",
                "email": "vadym@example.com",
                "aud": "authenticated",
                "role": "authenticated",
            },
        )
        captured: dict = {}

        def fake_get(url: str, *, headers: dict, timeout: float) -> _FakeHttpxResponse:
            captured["url"] = url
            captured["headers"] = headers
            captured["timeout"] = timeout
            return fake_resp

        monkeypatch.setattr(core_security.httpx, "get", fake_get)

        payload = core_security._validate_via_supabase("tok-ok")

        assert payload == {
            "sub": "user-42",
            "email": "vadym@example.com",
            "aud": "authenticated",
            "role": "authenticated",
        }
        # The right endpoint, the right auth header shape (both
        # ``Authorization`` and ``apikey`` — Supabase REST rejects
        # service-role calls that omit either).
        assert captured["url"] == "https://proj.supabase.co/auth/v1/user"
        assert captured["headers"]["Authorization"] == "Bearer tok-ok"
        assert captured["headers"]["apikey"] == "sk-test"
        assert captured["timeout"] == 5.0
        # Success caches the payload — second call must not re-hit httpx.
        monkeypatch.setattr(
            core_security.httpx,
            "get",
            MagicMock(side_effect=AssertionError("cache miss")),
        )
        assert core_security._validate_via_supabase("tok-ok") == payload

    def test_non_200_returns_none_and_does_not_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_cache()
        monkeypatch.setattr(core_security.settings, "SUPABASE_URL", "https://proj.supabase.co")
        monkeypatch.setattr(core_security.settings, "SUPABASE_SERVICE_ROLE_KEY", "sk-test")
        monkeypatch.setattr(
            core_security.httpx,
            "get",
            lambda *_a, **_k: _FakeHttpxResponse(status_code=401),
        )
        assert core_security._validate_via_supabase("tok-bad") is None
        assert "tok-bad" not in core_security._supabase_cache

    def test_httpx_error_returns_none_and_does_not_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_cache()
        monkeypatch.setattr(core_security.settings, "SUPABASE_URL", "https://proj.supabase.co")
        monkeypatch.setattr(core_security.settings, "SUPABASE_SERVICE_ROLE_KEY", "sk-test")

        def fake_get(*_a: object, **_k: object) -> _FakeHttpxResponse:
            raise core_security.httpx.HTTPError("connection refused")

        monkeypatch.setattr(core_security.httpx, "get", fake_get)
        assert core_security._validate_via_supabase("tok-net") is None
        assert "tok-net" not in core_security._supabase_cache

    def test_missing_service_role_key_still_sends_empty_apikey(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``SUPABASE_SERVICE_ROLE_KEY or ""`` — when the key isn't
        configured, we still send the header with an empty value rather
        than omitting it. Supabase will 401 it, which is what we want.
        """
        _clear_cache()
        monkeypatch.setattr(core_security.settings, "SUPABASE_URL", "https://proj.supabase.co")
        monkeypatch.setattr(core_security.settings, "SUPABASE_SERVICE_ROLE_KEY", None)
        captured: dict = {}

        def fake_get(url: str, *, headers: dict, timeout: float) -> _FakeHttpxResponse:
            captured["headers"] = headers
            return _FakeHttpxResponse(status_code=401)

        monkeypatch.setattr(core_security.httpx, "get", fake_get)
        core_security._validate_via_supabase("tok")
        assert captured["headers"]["apikey"] == ""

    def test_wrong_audience_rejected_and_not_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A 200 from ``/auth/v1/user`` whose ``aud`` is NOT "authenticated"
        must be rejected — the fallback path must be no weaker than the
        local-secret path, which pins audience="authenticated".
        """
        _clear_cache()
        monkeypatch.setattr(core_security.settings, "SUPABASE_URL", "https://proj.supabase.co")
        monkeypatch.setattr(core_security.settings, "SUPABASE_SERVICE_ROLE_KEY", "sk-test")
        monkeypatch.setattr(
            core_security.httpx,
            "get",
            lambda *_a, **_k: _FakeHttpxResponse(
                status_code=200,
                json_body={"id": "u", "email": "e", "aud": "anon", "role": "anon"},
            ),
        )
        assert core_security._validate_via_supabase("tok-wrongaud") is None
        assert "tok-wrongaud" not in core_security._supabase_cache

    def test_missing_audience_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_cache()
        monkeypatch.setattr(core_security.settings, "SUPABASE_URL", "https://proj.supabase.co")
        monkeypatch.setattr(core_security.settings, "SUPABASE_SERVICE_ROLE_KEY", "sk-test")
        monkeypatch.setattr(
            core_security.httpx,
            "get",
            lambda *_a, **_k: _FakeHttpxResponse(
                status_code=200,
                json_body={"id": "u", "email": "e", "role": "authenticated"},
            ),
        )
        assert core_security._validate_via_supabase("tok-noaud") is None


class TestDecodeAccessToken:
    """The public entry point. Local-secret path is the happy case;
    every JWT exception type has its own handling, and the
    ``InvalidSignatureError`` branch *must* fall back to Supabase
    (token issued by Supabase rotation, not by us).
    """

    def test_no_local_secret_uses_supabase_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_cache()
        monkeypatch.setattr(core_security.settings, "JWT_SECRET_KEY", None)
        monkeypatch.setattr(
            core_security,
            "_validate_via_supabase",
            lambda token: {"sub": "fallback-user", "token": token},
        )
        assert core_security.decode_access_token("any-token") == {
            "sub": "fallback-user",
            "token": "any-token",
        }

    def test_happy_path_decodes_with_local_secret(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_cache()
        monkeypatch.setattr(core_security.settings, "JWT_SECRET_KEY", "test-secret-32bytes-min-padding!!")
        monkeypatch.setattr(core_security.settings, "JWT_ALGORITHM", "HS256")
        monkeypatch.setattr(
            core_security.jwt,
            "decode",
            lambda token, secret, algorithms, audience: {
                "sub": "user-99",
                "aud": audience,
                "_received_secret": secret,
                "_received_algos": algorithms,
            },
        )
        payload = core_security.decode_access_token("token-xyz")
        assert payload is not None
        assert payload["sub"] == "user-99"
        assert payload["aud"] == "authenticated"
        assert payload["_received_secret"] == "test-secret-32bytes-min-padding!!"
        assert payload["_received_algos"] == ["HS256"]

    def test_expired_signature_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_cache()
        monkeypatch.setattr(core_security.settings, "JWT_SECRET_KEY", "test-secret")

        def fake_decode(*_a: object, **_k: object) -> dict:
            raise pyjwt.ExpiredSignatureError("expired")

        monkeypatch.setattr(core_security.jwt, "decode", fake_decode)
        assert core_security.decode_access_token("expired-token") is None

    def test_invalid_audience_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_cache()
        monkeypatch.setattr(core_security.settings, "JWT_SECRET_KEY", "test-secret")

        def fake_decode(*_a: object, **_k: object) -> dict:
            raise pyjwt.InvalidAudienceError("aud mismatch")

        monkeypatch.setattr(core_security.jwt, "decode", fake_decode)
        assert core_security.decode_access_token("wrong-aud") is None

    def test_invalid_signature_falls_back_to_supabase(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Critical path: a Supabase-issued token that doesn't match our
        local secret (rotation, env-skew) must NOT 401 — we re-verify it
        through Supabase's own ``/auth/v1/user`` endpoint.
        """
        _clear_cache()
        monkeypatch.setattr(core_security.settings, "JWT_SECRET_KEY", "wrong-secret")

        def fake_decode(*_a: object, **_k: object) -> dict:
            raise pyjwt.InvalidSignatureError("sig mismatch")

        monkeypatch.setattr(core_security.jwt, "decode", fake_decode)
        monkeypatch.setattr(
            core_security,
            "_validate_via_supabase",
            lambda token: {"sub": "supabase-user", "via": "fallback"},
        )
        assert core_security.decode_access_token("rotated-token") == {
            "sub": "supabase-user",
            "via": "fallback",
        }

    def test_generic_pyjwt_error_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Catch-all for malformed tokens, missing claims, etc. Must NOT
        fall back to Supabase — those tokens are genuinely invalid.
        """
        _clear_cache()
        monkeypatch.setattr(core_security.settings, "JWT_SECRET_KEY", "test-secret")

        def fake_decode(*_a: object, **_k: object) -> dict:
            raise pyjwt.DecodeError("malformed header")

        monkeypatch.setattr(core_security.jwt, "decode", fake_decode)
        # Sentinel: if Supabase fallback got called, this assertion fires.
        monkeypatch.setattr(
            core_security,
            "_validate_via_supabase",
            MagicMock(side_effect=AssertionError("must not fall back")),
        )
        assert core_security.decode_access_token("malformed") is None
