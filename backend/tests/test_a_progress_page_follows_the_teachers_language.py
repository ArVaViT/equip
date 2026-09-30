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


def test_the_gradebook_headings_follow_the_teacher_too(client: TestClient, db: Session, monkeypatch, student) -> None:
    # The course name above the matrix followed the teacher; its module and
    # lesson headings stayed in the author's language (2026-09-29).
    from app.models.course import Chapter, Module
    from app.models.enrollment import Enrollment
    from tests.conftest import STUDENT_ID

    monkeypatch.setattr("app.services.content_versions.read.is_translation_enabled", lambda: True)
    _course(db, "c-prog-heads")
    db.add(Module(id="c-prog-heads-m", course_id="c-prog-heads", order_index=0))
    db.add(
        Chapter(
            id="c-prog-heads-ch",
            course_id="c-prog-heads",
            module_id="c-prog-heads-m",
            order_index=0,
            chapter_type="reading",
            title="Урок первый",
        )
    )
    db.add(Enrollment(id="c-prog-heads-e", user_id=STUDENT_ID, course_id="c-prog-heads", progress=0))
    db.flush()
    for entity_type, entity_id, ru, en in (
        ("module", "c-prog-heads-m", "Модуль", "Module"),
        ("chapter", "c-prog-heads-ch", "Урок первый", "Lesson one"),
    ):
        record_human_version(db, entity_type=entity_type, entity_id=entity_id, field="title", locale="ru", text=ru)
        record_mt_version(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            field="title",
            locale="en",
            text=en,
            source_locale="ru",
            source_hash=compute_source_hash(ru, locale="ru"),
        )
    db.commit()

    body = client.get("/api/v1/progress/course/c-prog-heads/gradebook", headers={"Accept-Language": "en"}).json()
    assert [m["title"] for m in body["modules"]] == ["Module"]
    assert [c["title"] for c in body["students"][0]["chapters"]] == ["Lesson one"]
    # The source column is untouched: the translation was not written back.
    db.expire_all()
    assert db.get(Chapter, "c-prog-heads-ch").title == "Урок первый"
    # And German, with no translation, gets the author's words, not blanks.
    de = client.get("/api/v1/progress/course/c-prog-heads/gradebook", headers={"Accept-Language": "de"}).json()
    assert [m["title"] for m in de["modules"]] == ["Модуль"]
