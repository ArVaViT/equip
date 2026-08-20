"""Tests for ``PATCH /api/v1/users/me/preferences`` and locale defaults."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class TestPreferredLocale:
    def test_an_account_that_named_no_language_starts_in_english(self, client: TestClient):
        # The column is NOT NULL, so a signup that carried no language
        # still has to write something down. What it writes is the answer
        # for a person we know nothing about, and that is English — it was
        # 'ru' from the Russian-only days, which quietly turned "nobody
        # asked" into "this person reads Russian".
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["preferred_locale"] == "en"

    def test_patch_updates_preferred_locale(self, client: TestClient):
        # Patching to Russian, deliberately: it is a real change away from
        # the English the account starts in, so the assertions below cannot
        # pass by accident on a no-op.
        resp = client.patch(
            "/api/v1/users/me/preferences",
            json={"preferred_locale": "ru"},
        )
        assert resp.status_code == 200
        assert resp.json()["preferred_locale"] == "ru"

        # The change is persisted across requests.
        me = client.get("/api/v1/auth/me")
        assert me.json()["preferred_locale"] == "ru"

    def test_patch_writes_audit_log(self, client: TestClient, db: Session):
        resp = client.patch(
            "/api/v1/users/me/preferences",
            json={"preferred_locale": "ru"},
        )
        assert resp.status_code == 200

        log = (
            db.query(AuditLog).filter(AuditLog.action == "update", AuditLog.resource_type == "user_preferences").first()
        )
        assert log is not None
        assert log.details["preferred_locale"] == {"from": "en", "to": "ru"}

    def test_patch_rejects_unknown_locale(self, client: TestClient):
        resp = client.patch(
            "/api/v1/users/me/preferences",
            json={"preferred_locale": "fr"},
        )
        assert resp.status_code == 422

    def test_patch_is_idempotent(self, client: TestClient, db: Session):
        first = client.patch(
            "/api/v1/users/me/preferences",
            json={"preferred_locale": "ru"},
        )
        assert first.status_code == 200

        second = client.patch(
            "/api/v1/users/me/preferences",
            json={"preferred_locale": "ru"},
        )
        assert second.status_code == 200
        log_count = db.query(AuditLog).filter(AuditLog.resource_type == "user_preferences").count()
        assert log_count == 1

    def test_patch_with_unchanged_value_writes_no_audit_log(self, client: TestClient, db: Session):
        """Calling the endpoint with the value already in the DB must short-
        circuit before any audit row is written — otherwise the log would
        fill with no-op events on every page reload of the language switcher.
        """
        # The account starts in 'en'; PATCH with 'en' should be a no-op.
        resp = client.patch(
            "/api/v1/users/me/preferences",
            json={"preferred_locale": "en"},
        )
        assert resp.status_code == 200
        assert resp.json()["preferred_locale"] == "en"

        log_count = db.query(AuditLog).filter(AuditLog.resource_type == "user_preferences").count()
        assert log_count == 0
