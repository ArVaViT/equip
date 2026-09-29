"""A teacher who switched the interface to German read German everywhere
but their own course list, which stayed in the author's language
(2026-09-29). The list follows ``Accept-Language`` now, and falls back to
the author's words where there is no translation — a teacher always sees
the name of their own course."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.course import Course
from app.services.content_versions.write import record_human_version, record_mt_version
from app.services.translation.hash import compute_source_hash
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _course(db: Session, course_id: str, ru: str, de: str | None) -> None:
    db.add(Course(id=course_id, created_by=TEACHER_ID, status="draft", source_locale="ru"))
    db.flush()
    record_human_version(db, entity_type="course", entity_id=course_id, field="title", locale="ru", text=ru)
    if de:
        record_mt_version(
            db,
            entity_type="course",
            entity_id=course_id,
            field="title",
            locale="de",
            text=de,
            source_locale="ru",
            source_hash=compute_source_hash(ru, locale="ru"),
        )
    db.commit()


def test_the_list_is_in_the_teachers_language(client: TestClient, db: Session) -> None:
    _course(db, "c-list-de", "Книга Деяний", "Die Apostelgeschichte")
    _course(db, "c-list-ru-only", "Черновик курса", None)

    titles = {c["id"]: c["title"] for c in client.get("/api/v1/courses/my", headers={"Accept-Language": "de"}).json()}

    assert titles["c-list-de"] == "Die Apostelgeschichte"
    # Nothing in German yet: the author's own words, never an empty name.
    assert titles["c-list-ru-only"] == "Черновик курса"


def test_without_a_language_it_is_the_authors(client: TestClient, db: Session) -> None:
    _course(db, "c-list-src", "Книга Деяний", "Die Apostelgeschichte")
    titles = {c["id"]: c["title"] for c in client.get("/api/v1/courses/my").json()}
    assert titles["c-list-src"] == "Книга Деяний"


def test_with_translation_on_an_untranslated_course_keeps_its_name(
    client: TestClient, db: Session, monkeypatch
) -> None:
    # Review, 2026-09-29: tests run with no provider, where "auto" falls back
    # to the source. In production it does not, and the course came back
    # unnamed in the teacher's own list.
    monkeypatch.setattr("app.services.content_versions.read.is_translation_enabled", lambda: True)
    _course(db, "c-list-on", "Черновик курса", None)
    titles = {c["id"]: c["title"] for c in client.get("/api/v1/courses/my", headers={"Accept-Language": "de"}).json()}
    assert titles["c-list-on"] == "Черновик курса"
