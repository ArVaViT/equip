# ruff: noqa: RUF001
# The fixtures are Russian course text; Cyrillic letters that look like
# Latin ones are the content, not a slip.
"""A teacher posts to the class; the class hears about it, and so does
the teacher.

Everything here was found on the live course, not imagined:

* On a published course a new post waits in the staging table for its
  translations. The teacher's own response read it from
  ``content_versions`` and came back empty — a blank card in the editor
  the moment after «Опубликовать».
* The notification written for a Russian reader of a Russian course
  said «объявление — в „Карта в кармане“»: the title was one table
  over, and the fan-out did not look there.
* An event put on the calendar told nobody. Announcements had a
  fan-out from the start; events had none.
* The teacher's own calendar was empty. They are not enrolled in the
  course they teach, and the aggregation only knew enrollments.
* A Zoom link with ``?pwd=a&b`` in an announcement body was stored as
  ``a&amp;b`` and shown that way — the body is a ``<textarea>`` rendered
  as text, and bleach escapes text.
* A bare ``2026-10-01T18:00:00`` was accepted as an event date and
  stored with no zone.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.sanitize import sanitize_multiline_text
from app.models.enrollment import Enrollment
from app.models.notification import Notification

from ._cv_helpers import make_course_with_text
from .conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User

ANNOUNCEMENTS = "/api/v1/announcements"
COURSES = "/api/v1/courses"
CALENDAR = "/api/v1/calendar/events"


def _published_course_with_student(db: Session, student: User, *, locale: str = "ru") -> str:
    student.preferred_locale = locale
    course = make_course_with_text(
        db,
        course_id=f"live-{uuid.uuid4().hex[:6]}",
        title="Карта в кармане" if locale == "ru" else "Map in a Pocket",
        status="published",
        source_locale=locale,
        created_by=TEACHER_ID,
    )
    db.add(Enrollment(id=f"e-{uuid.uuid4().hex[:6]}", user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.commit()
    return course.id


def _notifications(db: Session, kind: str) -> list[Notification]:
    return db.query(Notification).filter(Notification.type == kind, Notification.user_id == STUDENT_ID).all()


class TestTheTeacherSeesWhatTheyJustPosted:
    def test_a_new_announcement_on_a_live_course_answers_with_its_own_text(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _published_course_with_student(db, student)
        r = client.post(
            ANNOUNCEMENTS,
            json={"title": "Завтра занятия не будет", "content": "Переносим на четверг", "course_id": course_id},
        )
        assert r.status_code == 201
        assert r.json()["title"] == "Завтра занятия не будет"
        assert r.json()["content"] == "Переносим на четверг"

    def test_an_edit_on_a_live_course_answers_with_the_new_text(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _published_course_with_student(db, student)
        created = client.post(ANNOUNCEMENTS, json={"title": "Было", "content": "Текст", "course_id": course_id})
        r = client.put(f"{ANNOUNCEMENTS}/{created.json()['id']}", json={"title": "Стало"})
        assert r.status_code == 200
        assert r.json()["title"] == "Стало"
        assert r.json()["content"] == "Текст"


class TestTheBellCarriesTheTitle:
    def test_a_reader_of_the_authors_language_gets_the_title_even_while_it_is_staged(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _published_course_with_student(db, student, locale="ru")
        client.post(
            ANNOUNCEMENTS,
            json={"title": "Завтра занятия не будет", "content": "Переносим", "course_id": course_id},
        )
        rows = _notifications(db, "new_announcement")
        assert len(rows) == 1
        assert rows[0].message == "Завтра занятия не будет — в «Карта в кармане»"
        assert rows[0].meta["i18n"]["params"]["title"] == "Завтра занятия не будет"

    def test_a_reader_of_another_language_is_not_handed_the_authors_language(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        """The frozen text in a German bell must not be Russian. With no
        German version yet, the row says «eine Ankündigung» and leaves
        the title to the page, where it arrives translated."""
        course_id = _published_course_with_student(db, student, locale="ru")
        student.preferred_locale = "de"
        db.commit()
        client.post(
            ANNOUNCEMENTS, json={"title": "Завтра занятия не будет", "content": "Текст", "course_id": course_id}
        )
        rows = _notifications(db, "new_announcement")
        assert len(rows) == 1
        assert "Завтра" not in rows[0].message
        assert rows[0].message.startswith("eine Ankündigung — in „")


class TestAnEventTellsTheClass:
    def test_a_new_event_notifies_every_enrolled_student_but_not_the_author(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _published_course_with_student(db, student, locale="ru")
        r = client.post(
            f"{COURSES}/{course_id}/events",
            json={"title": "Итоговый зачёт", "event_type": "exam", "event_date": "2026-10-01T18:00:00Z"},
        )
        assert r.status_code == 201
        everyone = db.query(Notification).filter(Notification.type == "new_event").all()
        assert [str(n.user_id) for n in everyone] == [str(STUDENT_ID)]
        row = everyone[0]
        assert row.title == "Новое событие в курсе"
        assert row.message == "Экзамен: Итоговый зачёт — в «Карта в кармане». Дата и время — в вашем календаре."
        # The link opens the calendar on this course, where the date is
        # shown in the reader's own zone — the text itself names no time.
        assert row.link == f"/calendar?course={course_id}"
        assert row.meta["event_id"] == r.json()["id"]

    def test_moving_an_event_notifies_again_and_renaming_it_does_not(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _published_course_with_student(db, student, locale="ru")
        created = client.post(
            f"{COURSES}/{course_id}/events",
            json={"title": "Зачёт", "event_type": "exam", "event_date": "2026-10-01T18:00:00Z"},
        )
        event_id = created.json()["id"]

        client.put(f"{COURSES}/{course_id}/events/{event_id}", json={"title": "Зачёт по Деяниям"})
        assert _notifications(db, "event_rescheduled") == []

        client.put(f"{COURSES}/{course_id}/events/{event_id}", json={"event_date": "2026-10-01T18:00:00Z"})
        assert _notifications(db, "event_rescheduled") == [], "the same instant is not a move"

        client.put(f"{COURSES}/{course_id}/events/{event_id}", json={"event_date": "2026-10-08T18:00:00Z"})
        moved = _notifications(db, "event_rescheduled")
        assert len(moved) == 1
        assert moved[0].title == "Событие перенесено"
        assert moved[0].message.startswith("Экзамен: Зачёт по Деяниям — в «Карта в кармане». Новая дата")

    def test_deleting_an_event_takes_its_notifications_with_it(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _published_course_with_student(db, student, locale="ru")
        created = client.post(
            f"{COURSES}/{course_id}/events",
            json={"title": "Зачёт", "event_type": "exam", "event_date": "2026-10-01T18:00:00Z"},
        )
        event_id = created.json()["id"]
        client.put(f"{COURSES}/{course_id}/events/{event_id}", json={"event_date": "2026-10-08T18:00:00Z"})
        assert len(_notifications(db, "new_event")) == 1
        assert len(_notifications(db, "event_rescheduled")) == 1

        r = client.delete(f"{COURSES}/{course_id}/events/{event_id}")
        assert r.status_code == 204
        assert _notifications(db, "new_event") == []
        assert _notifications(db, "event_rescheduled") == []

    def test_a_deactivated_student_hears_nothing(self, client: TestClient, db: Session, student: User) -> None:
        course_id = _published_course_with_student(db, student, locale="ru")
        student.deactivated_at = datetime.now(UTC)
        db.commit()
        client.post(
            f"{COURSES}/{course_id}/events",
            json={"title": "Зачёт", "event_type": "exam", "event_date": "2026-10-01T18:00:00Z"},
        )
        assert _notifications(db, "new_event") == []


class TestTheTeachersOwnCalendar:
    def test_shows_the_events_of_the_courses_they_teach(self, client: TestClient, db: Session, student: User) -> None:
        course_id = _published_course_with_student(db, student, locale="ru")
        client.post(
            f"{COURSES}/{course_id}/events",
            json={"title": "Зачёт", "event_type": "exam", "event_date": "2026-10-01T18:00:00Z"},
        )
        r = client.get(CALENDAR)
        assert r.status_code == 200
        assert [(e["source"], e["course_id"]) for e in r.json()] == [("course_event", course_id)]

    def test_the_course_filter_applies_to_owned_courses_too(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        first = _published_course_with_student(db, student, locale="ru")
        second = _published_course_with_student(db, student, locale="ru")
        for cid in (first, second):
            client.post(
                f"{COURSES}/{cid}/events",
                json={"title": "Зачёт", "event_type": "exam", "event_date": "2026-10-01T18:00:00Z"},
            )
        r = client.get(CALENDAR, params={"course_id": second})
        assert [e["course_id"] for e in r.json()] == [second]


class TestPlainTextStaysPlain:
    def test_an_ampersand_in_an_announcement_body_survives_the_round_trip(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _published_course_with_student(db, student)
        body = "Встреча: https://zoom.us/j/123?pwd=a&b\nТема: 5 < 10"
        r = client.post(ANNOUNCEMENTS, json={"title": "Ссылка", "content": body, "course_id": course_id})
        assert r.json()["content"] == body

    def test_an_ampersand_in_an_event_description_survives_too(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _published_course_with_student(db, student)
        r = client.post(
            f"{COURSES}/{course_id}/events",
            json={
                "title": "Встреча",
                "description": "https://zoom.us/j/1?pwd=a&b\nПароль: 5 < 10",
                "event_type": "live_session",
                "event_date": "2026-10-01T18:00:00Z",
            },
        )
        assert r.json()["description"] == "https://zoom.us/j/1?pwd=a&b\nПароль: 5 < 10"

    def test_markup_is_dropped_and_line_breaks_are_kept(self) -> None:
        # Tags go; the text between them stays, as text — it is rendered
        # by React as a string, so ``alert(1)`` is just eight characters.
        text = "Первая  строка<script>alert(1)</script>\r\n\r\n\r\n\r\nВторая &amp; третья<br>\n<b>жирная</b>"
        assert sanitize_multiline_text(text) == "Первая строка alert(1)\n\nВторая & третья\nжирная"

    def test_plain_text_is_a_fixed_point(self) -> None:
        text = "Q&A: 5 < 10\n\nВторой абзац"
        assert sanitize_multiline_text(sanitize_multiline_text(text)) == text


class TestAnEventHappensAtOneInstant:
    def test_a_naive_date_is_read_as_utc_and_stored_with_its_zone(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        from app.schemas.calendar import CourseEventCreate

        parsed = CourseEventCreate(title="Зачёт", event_date=datetime(2026, 10, 1, 18, 0))  # type: ignore[arg-type]
        assert parsed.event_date.tzinfo is not None
        assert parsed.event_date == datetime(2026, 10, 1, 18, 0, tzinfo=UTC)

    def test_an_aware_date_is_left_alone(self) -> None:
        from zoneinfo import ZoneInfo

        from app.schemas.calendar import CourseEventUpdate

        indiana = datetime(2026, 10, 1, 14, 0, tzinfo=ZoneInfo("America/Indiana/Indianapolis"))
        parsed = CourseEventUpdate(event_date=indiana)
        assert parsed.event_date == indiana
        assert parsed.event_date is not None
        assert parsed.event_date.astimezone(UTC) == datetime(2026, 10, 1, 18, 0, tzinfo=UTC)
