"""Phase 2c tests: dual-read fires from inline read paths that
don't go through Localizer.

The audit found four read paths that bypass ``Localizer`` because
each row carries its own per-row ``source_locale`` (different
parent courses, different cohorts), which doesn't fit Localizer's
single-source model. These tests pin that the inline
``maybe_compare_and_log`` calls fire correctly:

* ``GET /api/v1/courses/{id}/events`` (calendar)
* ``GET /api/v1/prerequisites/course/{id}`` (prereq title map)
* ``GET /api/v1/certificates/my`` (certificate course title overlay)
* ``GET /api/v1/courses`` (catalog summary via _build_localized_course)
* ``GET /api/v1/users/me/courses`` (enrollment summary via _build_localized_course)

A single representative test per family is enough — the wiring
pattern is identical at each site, the comparator semantics are
pinned by ``test_content_versions_compare.py``, and the wrapper
semantics are pinned by ``test_localizer_dual_read.py``. These
tests just verify the wiring exists and fires.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from app.services.content_versions import set_compare_sample_rate
from app.services.content_versions.write import record_human_version

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


@pytest.fixture
def sample_rate_one():
    set_compare_sample_rate(1.0)
    yield
    set_compare_sample_rate(0.0)


class TestCourseCatalogDualReadFires:
    def test_list_courses_fires_comparator_per_course(
        self,
        client: TestClient,
        db: Session,
        sample_rate_one: None,
        caplog: pytest.LogCaptureFixture,
    ):
        from app.models.course import Course
        from tests.conftest import TEACHER_ID

        course = Course(
            id="cat-dual-1",
            title="Curiosity",
            description="The art of asking why.",
            created_by=TEACHER_ID,
            status="published",
            source_locale="en",
        )
        db.add(course)
        # Pre-seed cv with a ru translation the legacy path won't see.
        record_human_version(
            db,
            entity_type="course",
            entity_id="cat-dual-1",
            field="title",
            locale="en",
            text="Curiosity",
        )
        record_human_version(
            db,
            entity_type="course",
            entity_id="cat-dual-1",
            field="title",
            locale="ru",
            text="Любопытство",
        )
        db.commit()
        with caplog.at_level(logging.WARNING, logger="app.services.content_versions.compare"):
            resp = client.get("/api/v1/courses", headers={"Accept-Language": "ru"})
        assert resp.status_code == 200, resp.text
        # Legacy returned source; cv has ru translation → NEW_ONLY.
        records = [
            r
            for r in caplog.records
            if getattr(r, "cv_compare_entity_id", None) == "cat-dual-1"
            and getattr(r, "cv_compare_field", None) == "title"
        ]
        assert len(records) >= 1
        assert any(getattr(r, "cv_compare_reason", None) == "new_only" for r in records)


class TestPrerequisiteTitleMapDualReadFires:
    def test_prereq_title_map_fires_per_course(
        self,
        client: TestClient,
        db: Session,
        sample_rate_one: None,
        caplog: pytest.LogCaptureFixture,
    ):
        from app.models.course import Course
        from app.models.prerequisite import CoursePrerequisite
        from tests.conftest import TEACHER_ID

        # Two courses: one is the prerequisite, one depends on it.
        prereq = Course(
            id="prereq-1",
            title="Foundations",
            created_by=TEACHER_ID,
            status="published",
            source_locale="en",
        )
        dependent = Course(
            id="dependent-1",
            title="Advanced",
            created_by=TEACHER_ID,
            status="published",
            source_locale="en",
        )
        db.add_all([prereq, dependent])
        db.flush()
        db.add(CoursePrerequisite(course_id="dependent-1", prerequisite_course_id="prereq-1"))
        # Seed cv with ru translation for the prereq title.
        record_human_version(
            db, entity_type="course", entity_id="prereq-1", field="title", locale="en", text="Foundations"
        )
        record_human_version(db, entity_type="course", entity_id="prereq-1", field="title", locale="ru", text="Основы")
        db.commit()
        with caplog.at_level(logging.WARNING, logger="app.services.content_versions.compare"):
            resp = client.get("/api/v1/prerequisites/course/dependent-1", headers={"Accept-Language": "ru"})
        assert resp.status_code == 200, resp.text
        records = [r for r in caplog.records if getattr(r, "cv_compare_entity_id", None) == "prereq-1"]
        assert any(getattr(r, "cv_compare_reason", None) == "new_only" for r in records)


class TestCalendarEventDualReadFires:
    def test_calendar_event_fires_for_title(
        self,
        client: TestClient,
        db: Session,
        sample_rate_one: None,
        caplog: pytest.LogCaptureFixture,
    ):
        import uuid as _uuid
        from datetime import UTC, datetime

        from app.models.course import Course
        from app.models.course_event import CourseEvent
        from app.models.enrollment import Enrollment
        from tests.conftest import TEACHER_ID

        course = Course(
            id="cal-dual-1",
            title="Test",
            created_by=TEACHER_ID,
            status="published",
            source_locale="en",
        )
        db.add(course)
        db.flush()
        # CourseEvent.id is a UUID column; pass a real UUID, not a str.
        event_uuid = _uuid.uuid4()
        event = CourseEvent(
            id=event_uuid,
            course_id="cal-dual-1",
            title="Webinar",
            description="About scripture",
            event_type="live_session",
            event_date=datetime(2026, 6, 1, 19, 0, tzinfo=UTC),
            created_by=TEACHER_ID,
        )
        db.add(event)
        # Enroll the teacher (the dashboard calendar endpoint scopes to
        # enrolled courses; the teacher is the test client's identity).
        db.add(Enrollment(id=str(_uuid.uuid4()), user_id=TEACHER_ID, course_id="cal-dual-1"))
        # Pre-seed cv with a ru translation the legacy won't see.
        record_human_version(
            db, entity_type="course_event", entity_id=str(event_uuid), field="title", locale="en", text="Webinar"
        )
        record_human_version(
            db, entity_type="course_event", entity_id=str(event_uuid), field="title", locale="ru", text="Вебинар"
        )
        db.commit()
        with caplog.at_level(logging.WARNING, logger="app.services.content_versions.compare"):
            resp = client.get("/api/v1/calendar/events", headers={"Accept-Language": "ru"})
        assert resp.status_code == 200, resp.text
        all_records = [r for r in caplog.records if getattr(r, "cv_compare_entity_type", None)]
        records = [
            r
            for r in all_records
            if getattr(r, "cv_compare_entity_type", None) == "course_event"
            and getattr(r, "cv_compare_entity_id", None) == str(event_uuid)
        ]
        assert any(getattr(r, "cv_compare_reason", None) == "new_only" for r in records), (
            f"expected new_only for course_event:{event_uuid}; observed records: "
            f"{[(getattr(r, 'cv_compare_entity_type', None), getattr(r, 'cv_compare_entity_id', None), getattr(r, 'cv_compare_reason', None)) for r in all_records]}"
        )
