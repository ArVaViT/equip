# ruff: noqa: RUF001
"""Phase 1f integration tests: assignment / announcement /
course_event / cohort dual-writes.

Pins the same supersession + idempotency contract as the rest of
Phase 1 across the remaining translatable entity types.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.models.announcement import Announcement
from app.models.assignment import Assignment
from app.models.cohort import Cohort
from app.models.content_version import ContentVersion
from app.models.course import Chapter, Course, Module
from app.models.course_event import CourseEvent
from tests.conftest import ADMIN_ID, TEACHER_ID

# These tests count rows and provider calls, so the size of the
# supported set is one of their inputs. They describe the "ru" + "en"
# set they were written against; the wider set has tests of its own.
pytestmark = pytest.mark.usefixtures("two_locales")
if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _seed_chapter(db: Session) -> str:
    course = Course(
        id="course-others-dw",
        title="Учебник",
        created_by=TEACHER_ID,
        status="draft",
        source_locale="ru",
    )
    module = Module(id="mod-others-dw", course_id=course.id, title="Раздел", order_index=0)
    chapter = Chapter(
        id="ch-others-dw",
        module_id=module.id,
        title="Глава",
        order_index=0,
        chapter_type="assignment",
    )
    db.add_all([course, module, chapter])
    db.commit()
    return chapter.id


def _seed_course(db: Session) -> str:
    course = Course(
        id="course-others-dw-bare",
        title="Учебник",
        created_by=TEACHER_ID,
        status="draft",
        source_locale="ru",
    )
    db.add(course)
    db.commit()
    return course.id


def _active(db: Session, entity_type: str, entity_id: str) -> list[ContentVersion]:
    return (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == entity_id,
            ContentVersion.superseded_by.is_(None),
        )
        .order_by(ContentVersion.field)
        .all()
    )


class TestAssignmentDualWrite:
    def test_create_writes_title_and_description(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        resp = client.post(
            "/api/v1/assignments",
            json={
                "chapter_id": chapter_id,
                "title": "Эссе о Бытии",
                "description": "Напишите 500 слов о первой главе.",
            },
        )
        assert resp.status_code == 201, resp.text
        ass_id = resp.json()["id"]
        rows = {r.field: r for r in _active(db, "assignment", ass_id)}
        assert set(rows.keys()) == {"title", "description"}
        assert rows["title"].locale == "ru"

    def test_update_title_supersedes(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        resp = client.post(
            "/api/v1/assignments",
            json={"chapter_id": chapter_id, "title": "Старое", "description": "Описание."},
        )
        ass_id = resp.json()["id"]
        original = next(r for r in _active(db, "assignment", ass_id) if r.field == "title")
        resp = client.put(f"/api/v1/assignments/{ass_id}", json={"title": "Новое"})
        assert resp.status_code == 200, resp.text
        active = next(r for r in _active(db, "assignment", ass_id) if r.field == "title")
        assert active.text == "Новое"
        db.refresh(original)
        assert original.superseded_by == active.id


class TestAnnouncementDualWrite:
    def test_course_announcement_writes_title_and_content(self, client: TestClient, db: Session):
        course_id = _seed_course(db)
        resp = client.post(
            "/api/v1/announcements",
            json={
                "title": "Объявление о вебинаре",
                "content": "Завтра в 19:00 встречаемся в Zoom.",
                "course_id": course_id,
            },
        )
        assert resp.status_code == 201, resp.text
        ann_id = resp.json()["id"]
        rows = {r.field: r for r in _active(db, "announcement", ann_id)}
        assert set(rows.keys()) == {"title", "content"}
        assert rows["title"].locale == "ru"
        assert rows["title"].authored_by == TEACHER_ID

    def test_global_announcement_falls_back_to_admin_preferred_locale(self, admin_client: TestClient, db: Session):
        resp = admin_client.post(
            "/api/v1/announcements",
            json={"title": "Notice", "content": "Maintenance tonight.", "course_id": None},
        )
        assert resp.status_code == 201, resp.text
        ann_id = resp.json()["id"]
        rows = _active(db, "announcement", ann_id)
        assert len(rows) == 2
        # Detector sees Latin → 'en' for both fields.
        assert {r.locale for r in rows} == {"en"}

    def test_update_title_supersedes(self, client: TestClient, db: Session):
        course_id = _seed_course(db)
        resp = client.post(
            "/api/v1/announcements",
            json={"title": "Старое", "content": "Текст.", "course_id": course_id},
        )
        ann_id = resp.json()["id"]
        original = next(r for r in _active(db, "announcement", ann_id) if r.field == "title")
        resp = client.put(f"/api/v1/announcements/{ann_id}", json={"title": "Новое"})
        assert resp.status_code == 200, resp.text
        active = next(r for r in _active(db, "announcement", ann_id) if r.field == "title")
        assert active.text == "Новое"
        db.refresh(original)
        assert original.superseded_by == active.id


class TestCourseEventDualWrite:
    def test_create_writes_title_and_description(self, client: TestClient, db: Session):
        course_id = _seed_course(db)
        resp = client.post(
            f"/api/v1/courses/{course_id}/events",
            json={
                "title": "Вебинар",
                "description": "Обсуждение глав 1-3.",
                "event_type": "live_session",
                "event_date": "2026-06-01T19:00:00Z",
            },
        )
        assert resp.status_code == 201, resp.text
        ev_id = resp.json()["id"]
        rows = {r.field: r for r in _active(db, "course_event", ev_id)}
        assert set(rows.keys()) == {"title", "description"}
        assert rows["title"].locale == "ru"

    def test_update_title_supersedes(self, client: TestClient, db: Session):
        course_id = _seed_course(db)
        resp = client.post(
            f"/api/v1/courses/{course_id}/events",
            json={
                "title": "Старое",
                "description": "Описание.",
                "event_type": "live_session",
                "event_date": "2026-06-01T19:00:00Z",
            },
        )
        ev_id = resp.json()["id"]
        original = next(r for r in _active(db, "course_event", ev_id) if r.field == "title")
        resp = client.put(
            f"/api/v1/courses/{course_id}/events/{ev_id}",
            json={"title": "Новое"},
        )
        assert resp.status_code == 200, resp.text
        active = next(r for r in _active(db, "course_event", ev_id) if r.field == "title")
        assert active.text == "Новое"
        db.refresh(original)
        assert original.superseded_by == active.id


class TestCohortDualWrite:
    def test_create_writes_title_row_from_name(self, admin_client: TestClient, db: Session):
        resp = admin_client.post(
            "/api/v1/cohorts",
            json={
                "name": "Когорта весна 2026",
                "start_date": "2026-03-01T00:00:00Z",
                "end_date": "2026-06-01T00:00:00Z",
            },
        )
        assert resp.status_code == 201, resp.text
        cohort_id = resp.json()["id"]
        rows = _active(db, "cohort", cohort_id)
        # Cohort.name -> content_versions.field='title' per registry mapping.
        assert len(rows) == 1
        assert rows[0].field == "title"
        assert rows[0].text == "Когорта весна 2026"
        assert rows[0].locale == "ru"
        assert rows[0].authored_by == ADMIN_ID

    def test_update_name_supersedes(self, admin_client: TestClient, db: Session):
        resp = admin_client.post(
            "/api/v1/cohorts",
            json={
                "name": "Старая когорта",
                "start_date": "2026-03-01T00:00:00Z",
                "end_date": "2026-06-01T00:00:00Z",
            },
        )
        cohort_id = resp.json()["id"]
        original = _active(db, "cohort", cohort_id)[0]
        resp = admin_client.patch(
            f"/api/v1/cohorts/{cohort_id}",
            json={"name": "Новая когорта"},
        )
        assert resp.status_code == 200, resp.text
        active = _active(db, "cohort", cohort_id)[0]
        assert active.text == "Новая когорта"
        db.refresh(original)
        assert original.superseded_by == active.id


@pytest.fixture(autouse=True)
def _isolate(db: Session):
    yield
    db.query(ContentVersion).filter(
        ContentVersion.entity_type.in_(("assignment", "announcement", "course_event", "cohort"))
    ).delete()
    db.query(Assignment).delete()
    db.query(Announcement).delete()
    db.query(CourseEvent).delete()
    db.query(Cohort).delete()
    db.commit()
