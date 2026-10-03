# ruff: noqa: RUF001
"""A class has a length, repeats weekly, and keeps its hour across a clock change.

Before this, an event was a start and nothing else: the feed guessed an
hour, the app called a class over three hours in, and a term of
Saturday lessons was twelve events typed one by one. The first teacher
on the platform teaches at 20:00 in Indianapolis — whose clocks go back
on November 1 — so the series is stepped on his wall clock, not in
seconds.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.models.course_event import CourseEvent
from app.models.enrollment import Enrollment
from app.models.notification import Notification
from app.services.calendar_ical import render_calendar
from app.services.event_series import (
    MAX_OCCURRENCES,
    SeriesRejected,
    WeeklySeries,
    shift_on_wall_clock,
    zone_or_utc,
)

from ._cv_helpers import make_course_with_text
from .conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User

COURSES = "/api/v1/courses"
INDY = zone_or_utc("America/Indiana/Indianapolis")


def _course(db: Session, student: User) -> str:
    student.preferred_locale = "ru"
    course = make_course_with_text(
        db,
        course_id=f"series-{uuid.uuid4().hex[:6]}",
        title="Курс проповеди",
        status="published",
        source_locale="ru",
        created_by=TEACHER_ID,
    )
    db.add(Enrollment(id=f"e-{uuid.uuid4().hex[:6]}", user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.commit()
    return course.id


def _notices(db: Session, kind: str) -> list[Notification]:
    return db.query(Notification).filter(Notification.type == kind, Notification.user_id == STUDENT_ID).all()


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class TestTheWallClock:
    def test_a_saturday_class_stays_at_eight_when_the_clocks_go_back(self) -> None:
        # 20:00 EDT on Oct 24 is 00:00 UTC on the 25th; after Nov 1 the
        # same 20:00 EST is 01:00 UTC.
        first = datetime(2026, 10, 25, 0, 0, tzinfo=UTC)
        starts = WeeklySeries(first=first, every_weeks=1, until=date(2026, 11, 14), zone=INDY).occurrences()
        assert [s.isoformat() for s in starts] == [
            "2026-10-25T00:00:00+00:00",
            "2026-11-01T00:00:00+00:00",
            "2026-11-08T01:00:00+00:00",
            "2026-11-15T01:00:00+00:00",
        ]
        assert {s.astimezone(INDY).strftime("%a %H:%M") for s in starts} == {"Sat 20:00"}

    def test_the_last_day_is_included_and_every_other_week_skips(self) -> None:
        first = datetime(2026, 10, 10, 18, 0, tzinfo=UTC)
        starts = WeeklySeries(
            first=first, every_weeks=2, until=date(2026, 11, 7), zone=zone_or_utc("UTC")
        ).occurrences()
        assert [s.date().isoformat() for s in starts] == ["2026-10-10", "2026-10-24", "2026-11-07"]

    def test_an_end_before_the_start_and_a_runaway_year_are_refused(self) -> None:
        first = datetime(2026, 10, 10, 18, 0, tzinfo=UTC)
        utc = zone_or_utc("UTC")
        with pytest.raises(SeriesRejected) as before:
            WeeklySeries(first=first, every_weeks=1, until=date(2026, 10, 9), zone=utc).occurrences()
        assert before.value.reason == "until_before_start"
        with pytest.raises(SeriesRejected) as runaway:
            WeeklySeries(first=first, every_weeks=1, until=date(2027, 12, 31), zone=utc).occurrences()
        assert runaway.value.reason == "too_many"
        # Exactly a year of Saturdays is allowed.
        year = WeeklySeries(first=first, every_weeks=1, until=date(2027, 10, 2), zone=utc).occurrences()
        assert len(year) == MAX_OCCURRENCES

    def test_moving_the_lesson_an_hour_earlier_moves_every_lesson_to_seven(self) -> None:
        old_anchor = datetime(2026, 10, 25, 0, 0, tzinfo=UTC)  # Sat 20:00 EDT
        new_anchor = datetime(2026, 10, 24, 23, 0, tzinfo=UTC)  # Sat 19:00 EDT
        after_change = datetime(2026, 11, 8, 1, 0, tzinfo=UTC)  # Sat 20:00 EST
        moved = shift_on_wall_clock(after_change, old_anchor=old_anchor, new_anchor=new_anchor, zone=INDY)
        assert moved.astimezone(INDY).strftime("%a %H:%M") == "Sat 19:00"

    def test_an_unknown_zone_is_utc_rather_than_an_error(self) -> None:
        assert str(zone_or_utc("Mars/Olympus")) == "UTC"
        assert str(zone_or_utc(None)) == "UTC"


class TestASeriesThroughTheApi:
    def _create_series(self, client: TestClient, course_id: str, **extra: object) -> dict:
        body = {
            "title": "Урок",
            "event_type": "live_session",
            "event_date": "2099-10-24T00:00:00Z",
            "duration_minutes": 90,
            "meeting_url": "https://us02web.zoom.us/j/4959692097",
            "repeat": {"every_weeks": 1, "until": "2099-11-14", "time_zone": "America/Indiana/Indianapolis"},
        }
        body.update(extra)
        r = client.post(f"{COURSES}/{course_id}/events", json=body)
        assert r.status_code == 201, r.text
        return r.json()

    def test_creates_every_occurrence_and_tells_the_class_once(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _course(db, student)
        first = self._create_series(client, course_id)
        rows = db.query(CourseEvent).filter(CourseEvent.course_id == course_id).order_by(CourseEvent.event_date).all()
        assert len(rows) == 4
        assert {r.series_id for r in rows} == {uuid.UUID(first["series_id"])}
        assert {r.duration_minutes for r in rows} == {90}
        assert {r.meeting_url for r in rows} == {"https://us02web.zoom.us/j/4959692097"}
        assert len(_notices(db, "new_event")) == 1

    def test_a_series_of_one_is_just_an_event(self, client: TestClient, db: Session, student: User) -> None:
        course_id = _course(db, student)
        created = self._create_series(
            client, course_id, repeat={"every_weeks": 1, "until": "2099-10-24", "time_zone": "UTC"}
        )
        assert created["series_id"] is None

    def test_a_runaway_end_date_is_refused_with_nothing_written(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _course(db, student)
        r = client.post(
            f"{COURSES}/{course_id}/events",
            json={
                "title": "Урок",
                "event_type": "live_session",
                "event_date": "2099-10-24T00:00:00Z",
                "repeat": {"every_weeks": 1, "until": "2101-01-01"},
            },
        )
        assert r.status_code == 422
        assert db.query(CourseEvent).filter(CourseEvent.course_id == course_id).count() == 0

    def test_this_and_following_moves_the_later_lessons_and_leaves_the_earlier(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _course(db, student)
        self._create_series(client, course_id)
        rows = db.query(CourseEvent).filter(CourseEvent.course_id == course_id).order_by(CourseEvent.event_date).all()
        second = rows[1]
        # 20:00 EDT → 19:00 EDT on the second Saturday, and everything after it.
        days_before = [_aware(r.event_date).astimezone(INDY).date() for r in rows]
        r = client.put(
            f"{COURSES}/{course_id}/events/{second.id}?scope=following",
            json={
                "event_date": (_aware(second.event_date) - timedelta(hours=1)).isoformat(),
                "title": "Урок (раньше)",
                "time_zone": "America/Indiana/Indianapolis",
            },
        )
        assert r.status_code == 200, r.text
        db.expire_all()
        rows = db.query(CourseEvent).filter(CourseEvent.course_id == course_id).order_by(CourseEvent.event_date).all()
        assert [_aware(r.event_date).astimezone(INDY).date() for r in rows] == days_before
        assert [_aware(r.event_date).astimezone(INDY).strftime("%H:%M") for r in rows] == [
            "20:00",
            "19:00",
            "19:00",
            "19:00",
        ]
        # One notice for the move, not three.
        assert len(_notices(db, "event_rescheduled")) == 1

    def test_a_recording_stays_with_its_own_lesson(self, client: TestClient, db: Session, student: User) -> None:
        course_id = _course(db, student)
        self._create_series(client, course_id)
        rows = db.query(CourseEvent).filter(CourseEvent.course_id == course_id).order_by(CourseEvent.event_date).all()
        r = client.put(
            f"{COURSES}/{course_id}/events/{rows[0].id}?scope=all",
            json={"recording_url": "https://youtu.be/B7XfamOJBeI", "duration_minutes": 75},
        )
        assert r.status_code == 200
        db.expire_all()
        rows = db.query(CourseEvent).filter(CourseEvent.course_id == course_id).order_by(CourseEvent.event_date).all()
        assert [r.recording_url for r in rows] == ["https://youtu.be/B7XfamOJBeI", None, None, None]
        assert {r.duration_minutes for r in rows} == {75}

    def test_deleting_following_keeps_the_ones_before(self, client: TestClient, db: Session, student: User) -> None:
        course_id = _course(db, student)
        self._create_series(client, course_id)
        rows = db.query(CourseEvent).filter(CourseEvent.course_id == course_id).order_by(CourseEvent.event_date).all()
        r = client.delete(f"{COURSES}/{course_id}/events/{rows[2].id}?scope=following")
        assert r.status_code == 204
        left = db.query(CourseEvent).filter(CourseEvent.course_id == course_id).order_by(CourseEvent.event_date).all()
        assert [x.id for x in left] == [rows[0].id, rows[1].id]


class TestAClassAlreadyOver:
    def test_entering_a_past_class_tells_nobody_it_is_new(self, client: TestClient, db: Session, student: User) -> None:
        course_id = _course(db, student)
        r = client.post(
            f"{COURSES}/{course_id}/events",
            json={"title": "Урок", "event_type": "live_session", "event_date": "2026-09-13T00:00:00Z"},
        )
        assert r.status_code == 201
        assert _notices(db, "new_event") == []

    def test_a_past_class_entered_with_its_recording_announces_the_recording(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _course(db, student)
        client.post(
            f"{COURSES}/{course_id}/events",
            json={
                "title": "Урок",
                "event_type": "live_session",
                "event_date": "2026-09-13T01:20:00Z",
                "recording_url": "https://youtu.be/uRLR16a3SpI",
            },
        )
        assert _notices(db, "new_event") == []
        ready = _notices(db, "recording_ready")
        assert len(ready) == 1
        assert ready[0].meta["recording_url"] == "https://youtu.be/uRLR16a3SpI"

    def test_a_class_under_way_is_still_news(self, client: TestClient, db: Session, student: User) -> None:
        """Started ten minutes ago, lasts ninety: people can still join."""
        course_id = _course(db, student)
        started = datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=10)
        client.post(
            f"{COURSES}/{course_id}/events",
            json={
                "title": "Урок",
                "event_type": "live_session",
                "event_date": started.isoformat(),
                "duration_minutes": 90,
            },
        )
        assert len(_notices(db, "new_event")) == 1


class TestTheFeedKnowsTheLength:
    def test_duration_and_a_half_hour_alarm_for_a_class(self) -> None:
        from app.schemas.calendar import CalendarEvent

        ics = render_calendar(
            [
                CalendarEvent(
                    id="e1",
                    title="Урок",
                    event_type="live_session",
                    event_date=datetime(2099, 10, 25, 0, 0, tzinfo=UTC),
                    duration_minutes=90,
                    course_id="c",
                    source="course_event",
                ),
                CalendarEvent(
                    id="d1",
                    title="Эссе",
                    event_type="deadline",
                    event_date=datetime(2099, 10, 25, 3, 59, tzinfo=UTC),
                    course_id="c",
                    source="assignment_deadline",
                ),
            ],
            locale="ru",
        )
        events = ics.split("BEGIN:VEVENT")[1:]
        assert "DURATION:PT90M" in events[0]
        assert "TRIGGER:-PT30M" in events[0]
        assert "Через 30 минут" in events[0]
        assert "DURATION:PT0S" in events[1]
        assert "VALARM" not in events[1]


class TestTheHourBefore:
    def _event(self, db: Session, course_id: str, *, starts_in: timedelta, kind: str = "live_session") -> CourseEvent:
        event = CourseEvent(
            course_id=course_id,
            event_type=kind,
            event_date=datetime.now(UTC) + starts_in,
            meeting_url="https://us02web.zoom.us/j/4959692097",
            created_by=TEACHER_ID,
        )
        db.add(event)
        db.commit()
        return event

    def test_a_class_within_the_hour_is_announced_once_with_its_link(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        from app.services.event_reminders import send_due_reminders

        course_id = _course(db, student)
        event = self._event(db, course_id, starts_in=timedelta(minutes=40))
        assert send_due_reminders(db) == 1
        assert send_due_reminders(db) == 0, "a second sweep must not repeat it"
        rows = _notices(db, "event_reminder")
        assert len(rows) == 1
        assert rows[0].title == "Начнётся в течение часа"
        assert rows[0].meta["meeting_url"] == "https://us02web.zoom.us/j/4959692097"
        assert rows[0].meta["event_id"] == str(event.id)

    def test_later_classes_deadlines_and_classes_under_way_are_left_alone(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        from app.services.event_reminders import send_due_reminders

        course_id = _course(db, student)
        self._event(db, course_id, starts_in=timedelta(hours=3))
        self._event(db, course_id, starts_in=timedelta(minutes=30), kind="deadline")
        self._event(db, course_id, starts_in=-timedelta(minutes=5))
        assert send_due_reminders(db) == 0
        assert _notices(db, "event_reminder") == []

    def test_moving_a_reminded_class_reminds_again_at_the_new_time(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        from app.services.event_reminders import send_due_reminders

        course_id = _course(db, student)
        event = self._event(db, course_id, starts_in=timedelta(minutes=30))
        send_due_reminders(db)
        later = (datetime.now(UTC) + timedelta(hours=3)).replace(microsecond=0)
        r = client.put(f"{COURSES}/{course_id}/events/{event.id}", json={"event_date": later.isoformat()})
        assert r.status_code == 200
        db.expire_all()
        assert db.get(CourseEvent, event.id).reminded_at is None
        # An hour before the new time it rings again.
        assert send_due_reminders(db, now=datetime.now(UTC) + timedelta(hours=2, minutes=10)) == 1

    def test_a_class_posted_inside_the_hour_is_announced_once(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        """The "new event" notice carries the Join link already; a reminder
        five minutes later would be the same news twice."""
        from app.services.event_reminders import send_due_reminders

        course_id = _course(db, student)
        soon = (datetime.now(UTC) + timedelta(minutes=40)).replace(microsecond=0)
        client.post(
            f"{COURSES}/{course_id}/events",
            json={"title": "Урок", "event_type": "live_session", "event_date": soon.isoformat()},
        )
        assert len(_notices(db, "new_event")) == 1
        assert send_due_reminders(db) == 0

    def test_a_deadline_does_not_repeat_and_a_zone_must_exist(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _course(db, student)
        r = client.post(
            f"{COURSES}/{course_id}/events",
            json={
                "title": "Эссе",
                "event_type": "deadline",
                "event_date": "2099-10-24T00:00:00Z",
                "repeat": {"every_weeks": 1, "until": "2099-11-14"},
            },
        )
        assert r.status_code == 422
        r = client.post(
            f"{COURSES}/{course_id}/events",
            json={
                "title": "Урок",
                "event_type": "live_session",
                "event_date": "2099-10-24T00:00:00Z",
                "repeat": {"every_weeks": 1, "until": "2099-11-14", "time_zone": "America/Indianapolis_typo"},
            },
        )
        assert r.status_code == 422
        assert r.json()["detail"][0]["type"] == "time_zone_unknown" or "time_zone_unknown" in r.text
        assert db.query(CourseEvent).filter(CourseEvent.course_id == course_id).count() == 0

    def test_deleting_the_class_takes_its_reminder_off_the_bell(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        from app.services.event_reminders import send_due_reminders

        course_id = _course(db, student)
        event = self._event(db, course_id, starts_in=timedelta(minutes=30))
        send_due_reminders(db)
        client.delete(f"{COURSES}/{course_id}/events/{event.id}")
        assert _notices(db, "event_reminder") == []


class TestTheReminderCron:
    GOOD = "reminder-cron-secret-0123456789abcdef"

    def test_refuses_without_the_worker_secret_and_runs_with_it(
        self, client: TestClient, db: Session, student: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from pydantic import SecretStr

        monkeypatch.setattr("app.core.config.settings.TRANSLATION_WORKER_SECRET", SecretStr(self.GOOD), raising=False)
        course_id = _course(db, student)
        db.add(
            CourseEvent(
                course_id=course_id,
                event_type="live_session",
                event_date=datetime.now(UTC) + timedelta(minutes=20),
                created_by=TEACHER_ID,
            )
        )
        db.commit()
        assert client.get("/api/v1/internal/event-reminders").status_code == 401
        assert client.get("/api/v1/internal/event-reminders", headers={"X-Worker-Secret": "wrong"}).status_code == 401
        assert _notices(db, "event_reminder") == []
        r = client.get("/api/v1/internal/event-reminders", headers={"Authorization": f"Bearer {self.GOOD}"})
        assert r.status_code == 200
        assert r.json() == {"reminded": 1}
        assert len(_notices(db, "event_reminder")) == 1


class TestTheGroupsDays:
    def test_a_student_sees_their_group_start_and_end_as_days(
        self, client: TestClient, db: Session, student: User, student_client: TestClient
    ) -> None:
        from app.models.cohort import Cohort
        from app.models.course import Course
        from app.services.calendar_ical import render_calendar
        from app.services.calendar_service import build_calendar_events
        from app.services.content_versions.write import record_human_version

        course_id = _course(db, student)
        course = db.get(Course, course_id)
        assert course is not None
        cohort = Cohort(
            id=uuid.uuid4(),
            start_date=datetime(2099, 10, 5, 4, 0, tzinfo=UTC),  # midnight in Indianapolis
            end_date=datetime(2099, 12, 19, 5, 0, tzinfo=UTC),
            status="upcoming",
            organization_id=uuid.UUID(str(course.organization_id)),
        )
        db.add(cohort)
        db.flush()
        record_human_version(
            db,
            entity_type="cohort",
            entity_id=str(cohort.id),
            field="title",
            locale="ru",
            text="Осень 2099",
            authored_by=TEACHER_ID,
        )
        enrollment = db.query(Enrollment).filter(Enrollment.course_id == course_id).one()
        enrollment.cohort_id = cohort.id
        db.commit()

        student.time_zone = "America/Indiana/Indianapolis"
        db.commit()
        events = build_calendar_events(db, user=student, display_locale="ru")
        days = [e for e in events if e.source in ("cohort_start", "cohort_end")]
        assert [(e.source, e.title, e.all_day) for e in days] == [
            ("cohort_start", "Начало занятий группы: Осень 2099", True),
            ("cohort_end", "Последний день группы: Осень 2099", True),
        ]
        ics = render_calendar(days, locale="ru", time_zone=student.time_zone)
        assert "DTSTART;VALUE=DATE:20991005" in ics
        assert "DTSTART;VALUE=DATE:20991219" in ics
