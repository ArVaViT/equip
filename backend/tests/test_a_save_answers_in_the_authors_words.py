"""A save answers with the words the author just wrote, in any language.

Since an edit written in another language replaces the course's source
(``content_versions.write.record_human_version``), the author's own view
must read the newest human row. The course, module and lesson routes did;
the event's save answered with an empty title until the response asked for
the author's view too (review, 2026-10-17). The assignment and announcement
saves got the same fix in the same commit; their tests are here too, and
so is the other half of "the author's words": on a live course the edit
is held back from readers, and the save still answers with it.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.course import Chapter, Course, CourseStatus, Module
from app.services.translation.service import reset_translation_provider_cache

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

PREFIX = "/api/v1/courses"
RU = "Деяния святых апостолов и первая церковь в Иерусалиме"
EN = "The Acts of the Apostles and the first church in Jerusalem"


@pytest.fixture()
def translation_on(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr("app.services.translation.service.settings.GEMINI_API_KEY", SecretStr("k"), raising=False)
    reset_translation_provider_cache()
    yield
    reset_translation_provider_cache()


def _russian_course(client: TestClient, db: Session) -> str:
    cid = str(client.post(PREFIX, json={"title": "Деяния"}).json()["id"])
    course = db.get(Course, cid)
    assert course is not None
    course.source_locale = "ru"
    db.commit()
    return cid


@pytest.mark.usefixtures("translation_on")
def test_an_event_saved_in_another_language_answers_with_it(client: TestClient, db: Session) -> None:
    cid = _russian_course(client, db)
    created = client.post(
        f"{PREFIX}/{cid}/events",
        json={"title": RU, "event_type": "live_session", "event_date": "2026-11-20T18:00:00Z"},
    )
    assert created.status_code in (200, 201), created.text
    eid = created.json()["id"]

    saved = client.put(f"{PREFIX}/{cid}/events/{eid}", json={"title": EN})

    assert saved.status_code == 200, saved.text
    assert saved.json()["title"] == EN


def _chapter(db: Session, cid: str) -> str:
    module = Module(id=str(uuid.uuid4()), course_id=cid, title="Раздел", order_index=0)
    db.add(module)
    db.flush()
    chapter = Chapter(
        id=str(uuid.uuid4()),
        module_id=module.id,
        course_id=cid,
        title="Глава",
        order_index=0,
        chapter_type="assignment",
    )
    db.add(chapter)
    db.commit()
    return str(chapter.id)


def _publish(db: Session, cid: str) -> None:
    course = db.get(Course, cid)
    assert course is not None
    course.status = CourseStatus.PUBLISHED
    db.commit()


@pytest.mark.usefixtures("translation_on")
@pytest.mark.parametrize("live", [False, True], ids=["draft", "live"])
def test_an_assignment_saved_in_another_language_answers_with_it(client: TestClient, db: Session, live: bool) -> None:
    cid = _russian_course(client, db)
    created = client.post("/api/v1/assignments", json={"chapter_id": _chapter(db, cid), "title": RU, "description": RU})
    assert created.status_code == 201, created.text
    if live:
        _publish(db, cid)

    saved = client.put(f"/api/v1/assignments/{created.json()['id']}", json={"title": EN, "description": EN})

    assert saved.status_code == 200, saved.text
    assert (saved.json()["title"], saved.json()["description"]) == (EN, EN)


@pytest.mark.usefixtures("translation_on")
@pytest.mark.parametrize("live", [False, True], ids=["draft", "live"])
def test_an_announcement_saved_in_another_language_answers_with_it(client: TestClient, db: Session, live: bool) -> None:
    cid = _russian_course(client, db)
    created = client.post("/api/v1/announcements", json={"title": RU, "content": RU, "course_id": cid})
    assert created.status_code == 201, created.text
    if live:
        _publish(db, cid)

    saved = client.put(f"/api/v1/announcements/{created.json()['id']}", json={"title": EN, "content": EN})

    assert saved.status_code == 200, saved.text
    assert (saved.json()["title"], saved.json()["content"]) == (EN, EN)
