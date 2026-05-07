"""Tests for ``PATCH /api/v1/users/me/preferences`` and locale defaults."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class TestPreferredLocale:
    def test_default_locale_is_ru(self, client: TestClient):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["preferred_locale"] == "ru"

    def test_patch_updates_preferred_locale(self, client: TestClient):
        resp = client.patch(
            "/api/v1/users/me/preferences",
            json={"preferred_locale": "en"},
        )
        assert resp.status_code == 200
        assert resp.json()["preferred_locale"] == "en"

        # The change is persisted across requests.
        me = client.get("/api/v1/auth/me")
        assert me.json()["preferred_locale"] == "en"

    def test_patch_writes_audit_log(self, client: TestClient, db: Session):
        resp = client.patch(
            "/api/v1/users/me/preferences",
            json={"preferred_locale": "en"},
        )
        assert resp.status_code == 200

        log = (
            db.query(AuditLog).filter(AuditLog.action == "update", AuditLog.resource_type == "user_preferences").first()
        )
        assert log is not None
        assert log.details["preferred_locale"] == {"from": "ru", "to": "en"}

    def test_patch_rejects_unknown_locale(self, client: TestClient):
        resp = client.patch(
            "/api/v1/users/me/preferences",
            json={"preferred_locale": "fr"},
        )
        assert resp.status_code == 422

    def test_patch_is_idempotent(self, client: TestClient, db: Session):
        first = client.patch(
            "/api/v1/users/me/preferences",
            json={"preferred_locale": "en"},
        )
        assert first.status_code == 200

        second = client.patch(
            "/api/v1/users/me/preferences",
            json={"preferred_locale": "en"},
        )
        assert second.status_code == 200
        log_count = db.query(AuditLog).filter(AuditLog.resource_type == "user_preferences").count()
        assert log_count == 1

    def test_patch_with_unchanged_value_writes_no_audit_log(self, client: TestClient, db: Session):
        """Calling the endpoint with the value already in the DB must short-
        circuit before any audit row is written — otherwise the log would
        fill with no-op events on every page reload of the language switcher.
        """
        # Default locale is 'ru'; PATCH with 'ru' should be a no-op.
        resp = client.patch(
            "/api/v1/users/me/preferences",
            json={"preferred_locale": "ru"},
        )
        assert resp.status_code == 200
        assert resp.json()["preferred_locale"] == "ru"

        log_count = db.query(AuditLog).filter(AuditLog.resource_type == "user_preferences").count()
        assert log_count == 0
