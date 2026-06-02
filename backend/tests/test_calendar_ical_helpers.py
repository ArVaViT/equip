"""Coverage for the JWT helper paths in ``app.api.v1.calendar_ical``.

The end-to-end iCal feed tests in ``test_calendar_ical.py`` exercise
the happy path (token issue + decode + rotation gate). This file pins
the defensive ``JWT_SECRET_KEY``-missing guards on both ``issue_token``
and ``_verify_token``, and the scope/iat-shape rejects inside
``_verify_token``.
"""

from __future__ import annotations

import pytest

from app.api.v1 import calendar_ical as ical_mod


class TestIssueTokenGuard:
    def test_missing_jwt_secret_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A deployment without JWT_SECRET_KEY is misconfigured. Issuing
        a token would produce a string that no verifier could check —
        the route MUST raise instead of silently handing it back."""
        monkeypatch.setattr(ical_mod.settings, "JWT_SECRET_KEY", None)
        with pytest.raises(RuntimeError) as exc:
            ical_mod._sign_token(user_id="user-id")
        assert "JWT_SECRET_KEY" in str(exc.value)


class TestVerifyTokenGuards:
    def test_missing_secret_returns_none_no_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``_verify_token`` is the non-raising sibling — when the
        secret is missing it returns ``None`` so the feed handler
        returns 404 rather than 500."""
        monkeypatch.setattr(ical_mod.settings, "JWT_SECRET_KEY", None)
        assert ical_mod._verify_token("any-token") is None

    def test_malformed_token_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A garbage string isn't even valid base64. The PyJWTError
        catch must return ``None`` without leaking the exception
        upstream."""
        monkeypatch.setattr(ical_mod.settings, "JWT_SECRET_KEY", "x" * 32)
        monkeypatch.setattr(ical_mod.settings, "JWT_ALGORITHM", "HS256")
        assert ical_mod._verify_token("not-a-real-token") is None

    def test_wrong_scope_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Even with a valid signature, the payload's scope must equal
        ``_TOKEN_SCOPE``. A Supabase JWT shouldn't accidentally be
        accepted here just because it shares the secret."""
        monkeypatch.setattr(ical_mod.settings, "JWT_SECRET_KEY", "x" * 32)
        monkeypatch.setattr(ical_mod.settings, "JWT_ALGORITHM", "HS256")

        # Issue a token with the right audience but a different scope.
        from datetime import UTC, datetime, timedelta

        import jwt as pyjwt

        payload = {
            "sub": "u",
            "scope": "wrong-scope",
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "aud": "equip-ical",
        }
        token = pyjwt.encode(payload, "x" * 32, algorithm="HS256")
        assert ical_mod._verify_token(token) is None

    def test_missing_sub_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``sub`` is the user id — if it's missing the token can't
        identify whose feed to serve."""
        monkeypatch.setattr(ical_mod.settings, "JWT_SECRET_KEY", "x" * 32)
        monkeypatch.setattr(ical_mod.settings, "JWT_ALGORITHM", "HS256")

        from datetime import UTC, datetime, timedelta

        import jwt as pyjwt

        payload = {
            "scope": ical_mod._TOKEN_SCOPE,
            "iat": int(datetime.now(UTC).timestamp()),
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "aud": "equip-ical",
        }
        token = pyjwt.encode(payload, "x" * 32, algorithm="HS256")
        assert ical_mod._verify_token(token) is None

    def test_iat_not_int_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """``iat`` must be int. A string would skip past the rotation
        floor check (which expects int comparison)."""
        monkeypatch.setattr(ical_mod.settings, "JWT_SECRET_KEY", "x" * 32)
        monkeypatch.setattr(ical_mod.settings, "JWT_ALGORITHM", "HS256")

        from datetime import UTC, datetime, timedelta

        import jwt as pyjwt

        payload = {
            "sub": "u",
            "scope": ical_mod._TOKEN_SCOPE,
            "iat": "not-an-int",
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "aud": "equip-ical",
        }
        token = pyjwt.encode(payload, "x" * 32, algorithm="HS256")
        assert ical_mod._verify_token(token) is None
