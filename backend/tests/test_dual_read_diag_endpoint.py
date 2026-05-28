"""Phase 2d tests: the admin dual-read diagnostic endpoint.

``GET /api/v1/dual-read-diag/{entity_type}/{entity_id}`` runs the
comparator for every translatable field of one entity across every
supported locale and returns the verdicts. Used to triage a mismatch
alert without round-tripping through Datadog logs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.content_versions.write import record_human_version

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _seed_course(db: Session, *, course_id: str = "diag-course-1") -> str:
    from app.models.course import Course
    from tests.conftest import TEACHER_ID

    course = Course(
        id=course_id,
        title="Source Title",
        description="Source description.",
        created_by=TEACHER_ID,
        status="published",
        source_locale="en",
    )
    db.add(course)
    db.commit()
    return course_id


class TestDiagEndpointAuth:
    def test_non_admin_gets_403(self, client: TestClient, db: Session):
        # client fixture is logged in as the teacher; teacher is not admin.
        course_id = _seed_course(db)
        resp = client.get(f"/api/v1/dual-read-diag/course/{course_id}")
        assert resp.status_code == 403


class TestDiagEndpointResults:
    def test_returns_one_block_per_field_locale_pair(self, admin_client: TestClient, db: Session):
        course_id = _seed_course(db, course_id="diag-locales")
        # cv: english source row + russian translation for title
        record_human_version(
            db,
            entity_type="course",
            entity_id=course_id,
            field="title",
            locale="en",
            text="Source Title",
        )
        record_human_version(
            db,
            entity_type="course",
            entity_id=course_id,
            field="title",
            locale="ru",
            text="Заголовок",
        )
        db.commit()
        resp = admin_client.get(f"/api/v1/dual-read-diag/course/{course_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["entity_type"] == "course"
        assert data["entity_id"] == course_id
        assert data["source_locale"] == "en"
        # course has 2 fields (title, description) by 2 locales = 4 rows.
        assert len(data["diagnostics"]) == 4
        # Title at ru: cv has it but legacy is empty (overlay not seeded
        # in content_translations) → NEW_ONLY.
        ru_title = next(d for d in data["diagnostics"] if d["field"] == "title" and d["display_locale"] == "ru")
        assert ru_title["reason"] == "new_only"
        assert ru_title["new_recorded_locale"] == "ru"

    def test_returns_legacy_only_no_backfill_when_cv_empty(self, admin_client: TestClient, db: Session):
        course_id = _seed_course(db, course_id="diag-empty")
        # No cv rows for this entity.
        resp = admin_client.get(f"/api/v1/dual-read-diag/course/{course_id}")
        assert resp.status_code == 200
        data = resp.json()
        for d in data["diagnostics"]:
            assert d["reason"] == "legacy_only_no_backfill"

    def test_returns_404_for_missing_entity(self, admin_client: TestClient, db: Session):
        resp = admin_client.get("/api/v1/dual-read-diag/course/does-not-exist")
        assert resp.status_code == 404

    def test_long_text_is_truncated_in_preview(self, admin_client: TestClient, db: Session):
        course_id = _seed_course(db, course_id="diag-long")
        long_text = "x" * 1000
        record_human_version(
            db,
            entity_type="course",
            entity_id=course_id,
            field="title",
            locale="ru",
            text=long_text,
        )
        record_human_version(
            db,
            entity_type="course",
            entity_id=course_id,
            field="title",
            locale="en",
            text="Source Title",
        )
        db.commit()
        resp = admin_client.get(f"/api/v1/dual-read-diag/course/{course_id}")
        data = resp.json()
        ru_title = next(d for d in data["diagnostics"] if d["field"] == "title" and d["display_locale"] == "ru")
        # Preview kept under the truncation limit + a hint.
        assert ru_title["new_text_preview"] is not None
        assert "truncated" in ru_title["new_text_preview"]
        assert len(ru_title["new_text_preview"]) < 300
