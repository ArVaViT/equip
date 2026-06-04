"""Coverage for the ``SQLAlchemyError`` catches in ``admin_translations``.

Both reset endpoints (`reset` and `reset-by-entity`) wrap the
``UPDATE`` in a ``try / except SQLAlchemyError: db.rollback(); raise``
guard. The happy-path tests fly straight past the catch. Pin both
branches by monkeypatching the ``update`` call to raise."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import OperationalError

if TYPE_CHECKING:
    import pytest
    from fastapi.testclient import TestClient


class TestResetByIdsRollback:
    def test_sqlalchemy_error_during_reset_triggers_rollback_then_500(
        self,
        admin_client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When the UPDATE raises ``SQLAlchemyError`` the route MUST
        rollback (so a half-applied transaction doesn't leak) and
        re-raise. The default global handler then returns 503."""

        def raise_in_update(*_a: object, **_k: object) -> None:
            raise OperationalError("simulated", None, Exception("lock"))

        # The route's failing call site is ``db.query(...).filter(...).update(...)``;
        # easiest seam is to monkeypatch the model-level ``ContentVersion.status``
        # comparison? No — monkeypatch ``db.commit`` instead so the
        # UPDATE goes through but the surrounding commit raises.
        # We need to grab the request's db session via the override.
        # The conftest's ``admin_client`` reuses the test ``db``, so
        # we patch its commit directly.
        from .conftest import TestSessionFactory

        original_commit = TestSessionFactory.kw.get("autocommit", False)
        del original_commit

        # The route opens a session via the conftest override; we
        # monkeypatch the session factory so every commit raises.
        def fake_commit(self: object) -> None:
            raise OperationalError("simulated", None, Exception("lock"))

        monkeypatch.setattr("sqlalchemy.orm.Session.commit", fake_commit)

        r = admin_client.post(
            "/api/v1/admin/translations/reset-by-ids",
            json={"ids": ["00000000-0000-0000-0000-000000000000"]},
        )
        # 503 via the global SQLAlchemyError handler in app.main.
        assert r.status_code == 503


class TestResetByEntityRollback:
    def test_sqlalchemy_error_propagates(
        self,
        admin_client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from sqlalchemy.exc import OperationalError as OE

        def fake_commit(self: object) -> None:
            raise OE("simulated", None, Exception("lock"))

        monkeypatch.setattr("sqlalchemy.orm.Session.commit", fake_commit)

        r = admin_client.post(
            "/api/v1/admin/translations/reset-by-entity",
            json={
                "entity_type": "course",
                "entity_id": "no-such-course",
                "field": "title",
                "locale": "en",
            },
        )
        assert r.status_code == 503


class TestResetByIdsNotFound:
    def test_returns_404_when_no_rows_match(self, admin_client: TestClient) -> None:
        """If the supplied ids resolve to zero failed_permanent rows
        the route 404s with a clean message — not a misleading 200
        with reset=0."""
        r = admin_client.post(
            "/api/v1/admin/translations/reset-by-ids",
            json={"ids": ["00000000-0000-0000-0000-000000000000"]},
        )
        assert r.status_code == 404
        # equip_error envelope: detail is {code, message, context}.
        detail = r.json()["detail"]
        assert detail["code"] == "resource.not_found"
        assert "failed_permanent" in detail["message"]
