"""In an English interface the analytics page named the course «Glossary in
Your Pocket» and the student-progress page beside it «Глоссарий в кармане»
(2026-09-29). Progress, gradebook and a student's detail now follow
``Accept-Language`` like the analytics do; without it, the author's words."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.course import Course
from app.services.content_versions.write import record_human_version, record_mt_version
from app.services.translation.hash import compute_source_hash
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _course(db: Session, course_id: str) -> None:
    db.add(Course(id=course_id, created_by=TEACHER_ID, status="published", source_locale="ru"))
    db.flush()
    record_human_version(db, entity_type="course", entity_id=course_id, field="title", locale="ru", text="Глоссарий")
    record_mt_version(
        db,
        entity_type="course",
        entity_id=course_id,
        field="title",
        locale="en",
        text="Glossary",
        source_locale="ru",
        source_hash=compute_source_hash("Глоссарий", locale="ru"),
    )
    db.commit()


def test_progress_and_gradebook_name_the_course_in_the_readers_language(client: TestClient, db: Session) -> None:
    _course(db, "c-prog-en")
    en = {"Accept-Language": "en"}
    assert client.get("/api/v1/progress/course/c-prog-en/students", headers=en).json()["course_title"] == "Glossary"
    assert client.get("/api/v1/progress/course/c-prog-en/gradebook", headers=en).json()["course_title"] == "Glossary"


def test_without_a_language_it_is_the_authors(client: TestClient, db: Session) -> None:
    _course(db, "c-prog-src")
    assert client.get("/api/v1/progress/course/c-prog-src/students").json()["course_title"] == "Глоссарий"


def test_with_translation_on_a_missing_translation_keeps_the_name(client: TestClient, db: Session, monkeypatch) -> None:
    # With a provider configured, "auto" means no fallback, and the page
    # named the course "" (review, 2026-09-29).
    monkeypatch.setattr("app.services.content_versions.read.is_translation_enabled", lambda: True)
    _course(db, "c-prog-on")
    de = {"Accept-Language": "de"}
    assert client.get("/api/v1/progress/course/c-prog-on/students", headers=de).json()["course_title"] == "Глоссарий"
    assert client.get("/api/v1/progress/course/c-prog-on/gradebook", headers=de).json()["course_title"] == "Глоссарий"
    assert client.get("/api/v1/analytics/course/c-prog-on", headers=de).json()["course_title"] == "Глоссарий"
