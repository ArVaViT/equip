# Russian course text on purpose: a Russian course read by a Russian
# student is exactly the case the rule is about.
"""The bell shows a teacher's text only once every language has it.

The rule (2026-10-03, and again for the calendar in b38d7556): a text
reaches readers when all four languages are ready — in the author's own
language too, with no early copy for the class that shares it. A staged
edit is read by its editor and nobody else.

The bell broke it: the fan-out froze the author's held title into the
row for every reader of the author's language, the moment the post was
written, while the other languages were still being made. A renamed
event went out under its new name the same way.

Now the title is a reference the bell resolves when it is opened, from
released rows only; a notice about an announcement readers cannot see
yet is left out of the bell until the announcement is out.

Translation is switched on for every test here: on a deploy that does
not translate, ``auto`` falls back to whatever text exists and hides the
difference.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest

from app.api.consent_gate import consent_subject
from app.api.dependencies import get_current_user, get_optional_user
from app.main import app
from app.models.enrollment import Enrollment
from app.models.notification import Notification
from app.models.staged_content_version import StagedContentVersion
from app.services.content_versions.write import record_human_version, record_mt_version

from ._cv_helpers import make_course_with_text
from .conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User

API = "/api/v1"
OTHER_LOCALES = {"en": "EN", "de": "DE", "uk": "UK"}


@pytest.fixture(autouse=True)
def _translation_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.content_versions.read.is_translation_enabled", lambda: True)


def _live_course(db: Session, student: User, *, reader_locale: str = "ru") -> str:
    student.preferred_locale = reader_locale
    course = make_course_with_text(
        db,
        course_id=f"live-{uuid.uuid4().hex[:6]}",
        title="Карта в кармане",
        status="published",
        source_locale="ru",
        created_by=TEACHER_ID,
    )
    for locale in OTHER_LOCALES:
        record_human_version(
            db, entity_type="course", entity_id=course.id, field="title", locale=locale, text=f"Map [{locale}]"
        )
    db.add(Enrollment(id=f"e-{uuid.uuid4().hex[:6]}", user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.commit()
    return course.id


def _release(db: Session, entity_type: str, entity_id: str, texts: dict[str, str]) -> None:
    """What promotion does once every language is ready, for one entity:
    the author's held text goes out together with its translations."""
    held = (
        db.query(StagedContentVersion)
        .filter(StagedContentVersion.entity_type == entity_type, StagedContentVersion.entity_id == entity_id)
        .all()
    )
    for row in held:
        record_human_version(
            db, entity_type=entity_type, entity_id=entity_id, field=row.field, locale=row.locale, text=row.text
        )
        db.delete(row)
    for field, text in texts.items():
        for locale, tag in OTHER_LOCALES.items():
            record_mt_version(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                field=field,
                locale=locale,
                text=f"{text} [{tag}]",
                source_locale="ru",
                source_hash=f"h-{text}",
            )
    db.commit()


def _as_student(student: User) -> None:
    for dep in (get_current_user, get_optional_user, consent_subject):
        app.dependency_overrides[dep] = lambda: student


def _as_teacher(teacher: User) -> None:
    for dep in (get_current_user, get_optional_user, consent_subject):
        app.dependency_overrides[dep] = lambda: teacher


def _bell(client: TestClient, student: User, teacher: User, locale: str) -> dict[str, Any]:
    _as_student(student)
    try:
        r = client.get(f"{API}/notifications", headers={"Accept-Language": locale})
        assert r.status_code == 200, r.text
        count = client.get(f"{API}/notifications/unread-count").json()["count"]
    finally:
        _as_teacher(teacher)
    body = r.json()
    return {"messages": [n["message"] for n in body["items"]], "total": body["total"], "unread": count}


def _post_announcement(client: TestClient, course_id: str, title: str) -> str:
    r = client.post(f"{API}/announcements", json={"title": title, "content": "Переносим", "course_id": course_id})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _post_event(client: TestClient, course_id: str, title: str) -> str:
    r = client.post(
        f"{API}/courses/{course_id}/events",
        json={"title": title, "event_type": "exam", "event_date": "2099-10-01T18:00:00Z"},
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


class TestANewAnnouncement:
    def test_the_authors_own_language_waits_too(
        self, client: TestClient, db: Session, student: User, teacher: User
    ) -> None:
        course_id = _live_course(db, student, reader_locale="ru")
        _post_announcement(client, course_id, "Завтра занятия не будет")

        bell = _bell(client, student, teacher, "ru")
        assert bell == {"messages": [], "total": 0, "unread": 0}
        # Nor is the held title anywhere in the row, to be shown later by
        # some other reader of it.
        (row,) = db.query(Notification).filter(Notification.type == "new_announcement").all()
        assert "Завтра" not in row.message
        assert "Завтра" not in str(row.meta)

    def test_it_turns_up_with_its_title_once_every_language_has_it(
        self, client: TestClient, db: Session, student: User, teacher: User
    ) -> None:
        course_id = _live_course(db, student, reader_locale="ru")
        ann_id = _post_announcement(client, course_id, "Завтра занятия не будет")
        _release(db, "announcement", ann_id, {"title": "Завтра занятия не будет", "content": "Переносим"})

        assert _bell(client, student, teacher, "ru") == {
            "messages": ["Завтра занятия не будет — в «Карта в кармане»"],
            "total": 1,
            "unread": 1,
        }
        assert _bell(client, student, teacher, "de")["messages"] == ["Завтра занятия не будет [DE] — in „Map [de]“"]

    def test_marking_everything_read_leaves_a_held_notice_new(
        self, client: TestClient, db: Session, student: User, teacher: User
    ) -> None:
        course_id = _live_course(db, student)
        ann_id = _post_announcement(client, course_id, "Завтра занятия не будет")
        _as_student(student)
        try:
            assert client.post(f"{API}/notifications/read-all").status_code == 200
        finally:
            _as_teacher(teacher)
        _release(db, "announcement", ann_id, {"title": "Завтра занятия не будет", "content": "Переносим"})
        assert _bell(client, student, teacher, "ru")["unread"] == 1

    def test_it_keeps_its_place_by_date(self, client: TestClient, db: Session, student: User, teacher: User) -> None:
        course_id = _live_course(db, student)
        first = _post_announcement(client, course_id, "Первое")
        second = _post_announcement(client, course_id, "Второе")
        for notice in db.query(Notification).filter(Notification.type == "new_announcement"):
            written_first = notice.meta["announcement_id"] == first
            notice.created_at = datetime.now(UTC) - timedelta(minutes=2 if written_first else 1)
        db.commit()
        # The second is out first; the first follows. The bell is ordered
        # by when each was written, not by when it was released.
        _release(db, "announcement", second, {"title": "Второе", "content": "Переносим"})
        assert _bell(client, student, teacher, "ru")["messages"] == ["Второе — в «Карта в кармане»"]
        _release(db, "announcement", first, {"title": "Первое", "content": "Переносим"})
        assert _bell(client, student, teacher, "ru")["messages"] == [
            "Второе — в «Карта в кармане»",
            "Первое — в «Карта в кармане»",
        ]


class TestAnEditToAReleasedTitle:
    def test_the_bell_keeps_the_released_wording_until_the_edit_is_out(
        self, client: TestClient, db: Session, student: User, teacher: User
    ) -> None:
        course_id = _live_course(db, student, reader_locale="ru")
        ann_id = _post_announcement(client, course_id, "Было")
        _release(db, "announcement", ann_id, {"title": "Было", "content": "Переносим"})

        r = client.put(f"{API}/announcements/{ann_id}", json={"title": "Стало"})
        assert r.status_code == 200
        assert r.json()["title"] == "Стало", "the author sees their own edit"

        assert _bell(client, student, teacher, "ru")["messages"] == ["Было — в «Карта в кармане»"]
        assert _bell(client, student, teacher, "de")["messages"] == ["Было [DE] — in „Map [de]“"]

        _release(db, "announcement", ann_id, {"title": "Стало"})
        assert _bell(client, student, teacher, "ru")["messages"] == ["Стало — в «Карта в кармане»"]


class TestAnEvent:
    def test_a_held_event_is_named_by_its_kind_in_the_authors_language_too(
        self, client: TestClient, db: Session, student: User, teacher: User
    ) -> None:
        # Not hidden: the calendar lists a held event under its kind, and a
        # reminder that it starts within the hour must not wait.
        course_id = _live_course(db, student, reader_locale="ru")
        event_id = _post_event(client, course_id, "Итоговый зачёт")

        assert _bell(client, student, teacher, "ru")["messages"] == [
            "Экзамен: событие — в «Карта в кармане». Дата и время — в вашем календаре."
        ]

        _release(db, "course_event", event_id, {"title": "Итоговый зачёт"})
        assert _bell(client, student, teacher, "ru")["messages"] == [
            "Экзамен: Итоговый зачёт — в «Карта в кармане». Дата и время — в вашем календаре."
        ]

    def test_a_renamed_event_keeps_its_released_name_when_it_moves(
        self, client: TestClient, db: Session, student: User, teacher: User
    ) -> None:
        course_id = _live_course(db, student, reader_locale="ru")
        event_id = _post_event(client, course_id, "Зачёт")
        _release(db, "course_event", event_id, {"title": "Зачёт"})

        client.put(f"{API}/courses/{course_id}/events/{event_id}", json={"title": "Зачёт по Деяниям"})
        client.put(f"{API}/courses/{course_id}/events/{event_id}", json={"event_date": "2099-10-08T18:00:00Z"})

        (moved,) = [m for m in _bell(client, student, teacher, "ru")["messages"] if "Новая дата" in m]
        assert moved.startswith("Экзамен: Зачёт — в «Карта в кармане». Новая дата")
        (row,) = db.query(Notification).filter(Notification.type == "event_rescheduled").all()
        assert "Деяниям" not in row.message
