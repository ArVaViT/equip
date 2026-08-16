"""A calendar entry is read at a glance, in whatever language you read.

Three of the four calendar surfaces were serving the author's language.
The module-deadline loop hydrated titles at each course's source locale
and welded the English word "Due" onto every one of them; the
assignment and course-event loops each wrote out their own
display → source → any-locale chain by hand — the spare language the
platform had removed everywhere the shared resolver reaches.

And the iCal feed asked ``Accept-Language``, which a calendar client
never sends: Apple Calendar polls a URL. That collapsed to the platform
default, so a German subscriber got a permanently Russian feed in an
app they had subscribed to once and would never think to re-check.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.course import Chapter, Course, Module
from app.models.course_event import CourseEvent
from app.models.enrollment import Enrollment
from app.services.calendar_service import build_calendar_events
from app.services.content_versions.write import record_human_version
from app.services.translation.service import reset_translation_provider_cache

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User


@pytest.fixture(autouse=True)
def _translation_is_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()
    yield
    reset_translation_provider_cache()


def _russian_course_with_dates(db: Session, student: User, teacher: User) -> Course:
    course = Course(
        id=f"cal-{uuid.uuid4().hex[:8]}",
        created_by=teacher.id,
        status="published",
        source_locale="ru",
    )
    db.add(course)
    db.flush()
    module = Module(
        id=str(uuid.uuid4()),
        course_id=course.id,
        order_index=0,
        due_date=datetime.now(UTC) + timedelta(days=3),
    )
    db.add(module)
    db.flush()
    record_human_version(
        db,
        entity_type="module",
        entity_id=str(module.id),
        field="title",
        locale="ru",
        text="Модуль 3. Толкование Писания",
        authored_by=teacher.id,
    )
    db.add(Chapter(id=str(uuid.uuid4()), module_id=module.id, title="Урок 1", order_index=0))
    event = CourseEvent(
        id=uuid.uuid4(),
        course_id=course.id,
        event_type="lecture",
        event_date=datetime.now(UTC) + timedelta(days=4),
        created_by=teacher.id,
    )
    db.add(event)
    db.flush()
    record_human_version(
        db,
        entity_type="course_event",
        entity_id=str(event.id),
        field="title",
        locale="ru",
        text="Разбор Послания к Римлянам",
        authored_by=teacher.id,
    )
    db.add(Enrollment(id=f"enr-{course.id}", user_id=student.id, course_id=course.id, progress=0))
    db.commit()
    return course


class TestTheAggregatedFeed:
    def test_a_german_reader_is_not_given_the_russian_module(self, db: Session, student: User, teacher: User):
        _russian_course_with_dates(db, student, teacher)

        events = build_calendar_events(db=db, user=student, course_id=None, limit=100, display_locale="de")

        deadlines = [e for e in events if e.source == "module_deadline"]
        assert deadlines
        assert all(e.title == "" for e in deadlines), [e.title for e in deadlines]

    def test_nor_the_russian_course_event(self, db: Session, student: User, teacher: User):
        _russian_course_with_dates(db, student, teacher)

        events = build_calendar_events(db=db, user=student, course_id=None, limit=100, display_locale="de")

        lectures = [e for e in events if e.event_type == "lecture"]
        assert lectures
        assert all(e.title == "" for e in lectures)

    def test_the_reader_whose_language_it_is_gets_it(self, db: Session, student: User, teacher: User):
        _russian_course_with_dates(db, student, teacher)

        events = build_calendar_events(db=db, user=student, course_id=None, limit=100, display_locale="ru")

        titles = [e.title for e in events]
        assert "Модуль 3. Толкование Писания" in titles
        assert "Разбор Послания к Римлянам" in titles

    def test_a_deadline_carries_no_english_word_in_its_title(self, db: Session, student: User, teacher: User):
        # The title used to be built as f"{module.title} — Due", which put
        # an English word in every locale's calendar. What kind of entry
        # this is travels in ``event_type``, and the client says it in
        # its own language.
        _russian_course_with_dates(db, student, teacher)

        events = build_calendar_events(db=db, user=student, course_id=None, limit=100, display_locale="ru")

        deadlines = [e for e in events if e.source == "module_deadline"]
        assert deadlines
        assert all("Due" not in e.title for e in deadlines)
        assert all(e.event_type == "deadline" for e in deadlines)
