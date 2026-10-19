"""Kyiv and Indiana change their clocks a week apart (2026).

Kyiv goes back an hour on Sunday October 25 (04:00 EEST → 03:00 EET, at
01:00 UTC); Indianapolis on Sunday November 1 (02:00 EDT → 01:00 EST, at
06:00 UTC). For that one week a class at 19:00 in Indiana is an hour earlier
in Kyiv than on every other week of the year — 01:00 instead of 02:00.

The rule the whole product keeps: a time is counted on the clock of the zone
the event was scheduled in and shown on the reader's. So these tests pin, on
both dates and in the week between:

- a weekly series keeps its hour in its own zone, from either side;
- a later "this and following" move is measured on the series' clock, not
  on the clock of whoever makes the edit (the defect fixed here);
- a lesson set inside the repeated autumn hour takes its first reading;
- the hour-before reminder goes out at the right instant;
- the calendar feed carries UTC instants, one per lesson, no RRULE to drift;
- the Daily Challenge day turns at the reader's midnight on a 25-hour day.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.models.course_event import CourseEvent
from app.services.calendar_ical import render_calendar
from app.services.daily_challenge import schedule as schedule_module
from app.services.daily_challenge.schedule import reader_today
from app.services.event_series import WeeklySeries, zone_or_utc

from .conftest import TEACHER_ID
from .test_event_series_and_lengths import _course

if TYPE_CHECKING:
    from zoneinfo import ZoneInfo

    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User

COURSES = "/api/v1/courses"
INDY = zone_or_utc("America/Indiana/Indianapolis")
KYIV = zone_or_utc("Europe/Kyiv")


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _read(instant: datetime, zone: ZoneInfo) -> str:
    return _aware(instant).astimezone(zone).strftime("%a %d %H:%M")


# Saturdays at 19:00 in Indianapolis, from before Kyiv's change to after Indiana's.
INDY_SATURDAYS = WeeklySeries(
    first=datetime(2026, 10, 17, 23, 0, tzinfo=UTC), every_weeks=1, until=date(2026, 11, 7), zone=INDY
)


class TestASeriesKeepsItsOwnClock:
    def test_an_indiana_class_stays_at_seven_there_and_is_an_hour_earlier_in_kyiv_for_one_week(self) -> None:
        starts = INDY_SATURDAYS.occurrences()
        assert [_read(s, INDY) for s in starts] == ["Sat 17 19:00", "Sat 24 19:00", "Sat 31 19:00", "Sat 07 19:00"]
        # Oct 24 is still summer in Kyiv (it turns at 01:00 UTC on the 25th,
        # two hours after this class starts); Oct 31 falls in the week
        # between; Nov 7 is winter on both sides.
        assert [_read(s, KYIV) for s in starts] == ["Sun 18 02:00", "Sun 25 02:00", "Sun 01 01:00", "Sun 08 02:00"]

    def test_a_kyiv_class_stays_at_seven_there_and_is_an_hour_later_in_indiana_for_one_week(self) -> None:
        starts = WeeklySeries(
            first=datetime(2026, 10, 21, 16, 0, tzinfo=UTC),  # Wed 19:00 EEST
            every_weeks=1,
            until=date(2026, 11, 4),
            zone=KYIV,
        ).occurrences()
        assert [_read(s, KYIV) for s in starts] == ["Wed 21 19:00", "Wed 28 19:00", "Wed 04 19:00"]
        assert [_read(s, INDY) for s in starts] == ["Wed 21 12:00", "Wed 28 13:00", "Wed 04 12:00"]

    @pytest.mark.parametrize(
        ("zone", "first", "repeated_utc"),
        [
            # 03:30 happens twice in Kyiv on Oct 25 (EEST, then EET).
            (KYIV, datetime(2026, 10, 18, 0, 30, tzinfo=UTC), datetime(2026, 10, 25, 0, 30, tzinfo=UTC)),
            # 01:30 happens twice in Indianapolis on Nov 1 (EDT, then EST).
            (INDY, datetime(2026, 10, 25, 5, 30, tzinfo=UTC), datetime(2026, 11, 1, 5, 30, tzinfo=UTC)),
        ],
    )
    def test_a_lesson_inside_the_repeated_hour_takes_its_first_reading(
        self, zone: ZoneInfo, first: datetime, repeated_utc: datetime
    ) -> None:
        starts = WeeklySeries(
            first=first, every_weeks=1, until=repeated_utc.date() + timedelta(days=7), zone=zone
        ).occurrences()
        assert starts[1] == repeated_utc
        # The same wall time on every lesson, the week of the change included.
        assert len({_aware(s).astimezone(zone).strftime("%H:%M") for s in starts}) == 1


class TestAMoveIsMeasuredOnTheSeriesClock:
    def _indiana_series(self, client: TestClient, course_id: str) -> None:
        r = client.post(
            f"{COURSES}/{course_id}/events",
            json={
                "title": "Урок",
                "event_type": "live_session",
                "event_date": "2026-10-24T23:00:00Z",  # Sat 19:00 EDT
                "duration_minutes": 90,
                "repeat": {"every_weeks": 1, "until": "2026-11-07", "time_zone": "America/Indiana/Indianapolis"},
            },
        )
        assert r.status_code == 201, r.text

    def _rows(self, db: Session, course_id: str) -> list[CourseEvent]:
        db.expire_all()
        return db.query(CourseEvent).filter(CourseEvent.course_id == course_id).order_by(CourseEvent.event_date).all()

    def test_the_series_remembers_its_zone_and_a_single_event_has_none(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _course(db, student)
        self._indiana_series(client, course_id)
        assert {r.time_zone for r in self._rows(db, course_id)} == {"America/Indiana/Indianapolis"}
        r = client.post(
            f"{COURSES}/{course_id}/events",
            json={"title": "Экзамен", "event_type": "exam", "event_date": "2026-11-14T23:00:00Z"},
        )
        assert r.status_code == 201, r.text
        single = db.get(CourseEvent, uuid.UUID(r.json()["id"]))
        assert single is not None
        assert single.time_zone is None

    def test_a_teacher_in_kyiv_moving_an_indiana_series_a_day_keeps_seven_in_indiana(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        # Saturday → Sunday, edited from Kyiv. Measured on Kyiv's clock the
        # first lesson's move is 23 hours (Kyiv's 25th has 25), and the
        # lessons after it would land at 18:00 and 17:00 in Indiana.
        course_id = _course(db, student)
        self._indiana_series(client, course_id)
        first = self._rows(db, course_id)[0]
        r = client.put(
            f"{COURSES}/{course_id}/events/{first.id}?scope=following",
            json={"event_date": "2026-10-25T23:00:00Z", "time_zone": "Europe/Kyiv"},
        )
        assert r.status_code == 200, r.text
        rows = self._rows(db, course_id)
        assert [_read(r.event_date, INDY) for r in rows] == ["Sun 25 19:00", "Sun 01 19:00", "Sun 08 19:00"]
        assert [_read(r.event_date, KYIV) for r in rows] == ["Mon 26 01:00", "Mon 02 02:00", "Mon 09 02:00"]
        # The zone is the series' own and an edit does not overwrite it.
        assert {r.time_zone for r in rows} == {"America/Indiana/Indianapolis"}

    def test_an_hour_earlier_from_kyiv_is_an_hour_earlier_on_the_indiana_clock(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _course(db, student)
        self._indiana_series(client, course_id)
        first = self._rows(db, course_id)[0]
        r = client.put(
            f"{COURSES}/{course_id}/events/{first.id}?scope=all",
            json={"event_date": "2026-10-24T22:00:00Z", "time_zone": "Europe/Kyiv"},
        )
        assert r.status_code == 200, r.text
        rows = self._rows(db, course_id)
        assert [_read(r.event_date, INDY) for r in rows] == ["Sat 24 18:00", "Sat 31 18:00", "Sat 07 18:00"]

    def test_a_series_saved_before_the_zone_was_stored_uses_the_editor_s(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _course(db, student)
        self._indiana_series(client, course_id)
        for row in self._rows(db, course_id):
            row.time_zone = None
        db.commit()
        first = self._rows(db, course_id)[0]
        r = client.put(
            f"{COURSES}/{course_id}/events/{first.id}?scope=following",
            json={"event_date": "2026-10-25T23:00:00Z", "time_zone": "America/Indiana/Indianapolis"},
        )
        assert r.status_code == 200, r.text
        assert [_read(r.event_date, INDY) for r in self._rows(db, course_id)] == [
            "Sun 25 19:00",
            "Sun 01 19:00",
            "Sun 08 19:00",
        ]


class TestASeriesWithNoZoneNamed:
    """Most profiles have no zone until a device reports one ('default')."""

    @pytest.mark.parametrize(
        ("school_zone", "expected"),
        [
            (None, "America/Indiana/Indianapolis"),
            ("Europe/Kyiv", "Europe/Kyiv"),
        ],
    )
    def test_is_stepped_on_the_school_s_clock_not_utc(
        self, client: TestClient, db: Session, student: User, school_zone: str | None, expected: str
    ) -> None:
        from app.models.course import Course
        from app.models.user import User as Profile
        from app.services.grading_scheme import get_org_settings

        course_id = _course(db, student)
        teacher = db.get(Profile, TEACHER_ID)
        assert teacher is not None
        teacher.time_zone = None
        course = db.get(Course, course_id)
        assert course is not None
        get_org_settings(db, course.organization_id).time_zone = school_zone
        db.commit()
        r = client.post(
            f"{COURSES}/{course_id}/events",
            json={
                "title": "Урок",
                "event_type": "live_session",
                "event_date": "2026-10-17T23:00:00Z",
                "repeat": {"every_weeks": 1, "until": "2026-11-07"},
            },
        )
        assert r.status_code == 201, r.text
        db.expire_all()
        rows = db.query(CourseEvent).filter(CourseEvent.course_id == course_id).order_by(CourseEvent.event_date).all()
        zone = zone_or_utc(expected)
        assert len({_aware(r.event_date).astimezone(zone).strftime("%H:%M") for r in rows}) == 1
        assert {r.time_zone for r in rows} == {expected}


class TestTheReminderGoesOutAtTheRightInstant:
    @pytest.mark.parametrize(
        "start",
        INDY_SATURDAYS.occurrences(),
        ids=["before-both", "kyiv-change-night", "week-between", "after-both"],
    )
    def test_an_hour_before_on_every_side_of_both_changes(
        self, client: TestClient, db: Session, student: User, start: datetime
    ) -> None:
        from app.services.event_reminders import send_due_reminders

        course_id = _course(db, student)
        db.add(CourseEvent(course_id=course_id, event_type="live_session", event_date=start, created_by=TEACHER_ID))
        db.commit()
        assert send_due_reminders(db, now=start - timedelta(minutes=61)) == 0
        assert send_due_reminders(db, now=start - timedelta(minutes=59)) == 1


class TestTheFeedCarriesInstants:
    def test_each_lesson_is_its_own_utc_start_with_no_rule_to_drift(self) -> None:
        from app.schemas.calendar import CalendarEvent

        ics = render_calendar(
            [
                CalendarEvent(
                    id=f"e{i}",
                    title="Урок",
                    event_type="live_session",
                    event_date=start,
                    duration_minutes=90,
                    course_id="c",
                    source="course_event",
                )
                for i, start in enumerate(INDY_SATURDAYS.occurrences())
            ],
            locale="uk",
            time_zone="Europe/Kyiv",
        )
        starts = [line for line in ics.split("\r\n") if line.startswith("DTSTART")]
        assert starts == [
            "DTSTART:20261017T230000Z",
            "DTSTART:20261024T230000Z",
            "DTSTART:20261031T230000Z",
            "DTSTART:20261108T000000Z",
        ]
        assert "RRULE" not in ics
        assert "TZID" not in ics


class _Clock(datetime):
    instant: datetime = datetime(2026, 1, 1, tzinfo=UTC)

    @classmethod
    def now(cls, tz=None):
        return cls.instant.astimezone(tz) if tz else cls.instant.replace(tzinfo=None)


class TestTheDayTurnsAtTheReadersMidnight:
    @pytest.mark.parametrize(
        ("instant", "zone", "day"),
        [
            # Kyiv's 25th is 25 hours long: it starts at 21:00 UTC on the
            # 24th (EEST) and ends at 22:00 UTC on the 25th (EET).
            (datetime(2026, 10, 24, 20, 59, tzinfo=UTC), "Europe/Kyiv", date(2026, 10, 24)),
            (datetime(2026, 10, 24, 21, 0, tzinfo=UTC), "Europe/Kyiv", date(2026, 10, 25)),
            (datetime(2026, 10, 25, 21, 59, tzinfo=UTC), "Europe/Kyiv", date(2026, 10, 25)),
            (datetime(2026, 10, 25, 22, 0, tzinfo=UTC), "Europe/Kyiv", date(2026, 10, 26)),
            # The week between: Kyiv at UTC+2, Indiana still at UTC-4.
            (datetime(2026, 10, 28, 21, 59, tzinfo=UTC), "Europe/Kyiv", date(2026, 10, 28)),
            (datetime(2026, 10, 28, 22, 0, tzinfo=UTC), "Europe/Kyiv", date(2026, 10, 29)),
            (datetime(2026, 10, 29, 3, 59, tzinfo=UTC), "America/Indiana/Indianapolis", date(2026, 10, 28)),
            (datetime(2026, 10, 29, 4, 0, tzinfo=UTC), "America/Indiana/Indianapolis", date(2026, 10, 29)),
            # Indiana's November 1 is 25 hours long: 04:00 UTC to 05:00 UTC next day.
            (datetime(2026, 11, 1, 3, 59, tzinfo=UTC), "America/Indiana/Indianapolis", date(2026, 10, 31)),
            (datetime(2026, 11, 1, 4, 0, tzinfo=UTC), "America/Indiana/Indianapolis", date(2026, 11, 1)),
            (datetime(2026, 11, 2, 4, 59, tzinfo=UTC), "America/Indiana/Indianapolis", date(2026, 11, 1)),
            (datetime(2026, 11, 2, 5, 0, tzinfo=UTC), "America/Indiana/Indianapolis", date(2026, 11, 2)),
            # A profile that never got a zone (time_zone_source 'default') counts in UTC.
            (datetime(2026, 10, 25, 23, 59, tzinfo=UTC), None, date(2026, 10, 25)),
        ],
    )
    def test_on_the_day_of_the_change(
        self, monkeypatch: pytest.MonkeyPatch, instant: datetime, zone: str | None, day: date
    ) -> None:
        clock = type("Clock", (_Clock,), {"instant": instant})
        monkeypatch.setattr(schedule_module, "datetime", clock)
        assert reader_today(zone) == day


# Wednesdays at 19:00 in Kyiv, from before its change to after Indiana's,
# as the app sends them (the first as an instant, the zone named).
KYIV_FIRST = "2026-10-21T16:00:00Z"  # Wed 19:00 EEST
KYIV_WEDNESDAYS_UTC = [
    datetime(2026, 10, 21, 16, 0, tzinfo=UTC),  # EEST
    datetime(2026, 10, 28, 17, 0, tzinfo=UTC),  # EET; Indiana still EDT
    datetime(2026, 11, 4, 17, 0, tzinfo=UTC),  # both on winter time
]


class TestAKyivSeriesThroughTheApi:
    """The mirror of the Indiana series above, from Kyiv's side of the week."""

    def _kyiv_series(self, client: TestClient, course_id: str) -> None:
        r = client.post(
            f"{COURSES}/{course_id}/events",
            json={
                "title": "Урок",
                "event_type": "live_session",
                "event_date": KYIV_FIRST,
                "duration_minutes": 90,
                "repeat": {"every_weeks": 1, "until": "2026-11-04", "time_zone": "Europe/Kyiv"},
            },
        )
        assert r.status_code == 201, r.text

    def _rows(self, db: Session, course_id: str) -> list[CourseEvent]:
        db.expire_all()
        return db.query(CourseEvent).filter(CourseEvent.course_id == course_id).order_by(CourseEvent.event_date).all()

    def test_wednesday_stays_at_seven_in_kyiv_and_the_calendar_serves_the_instants(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _course(db, student)
        self._kyiv_series(client, course_id)
        rows = self._rows(db, course_id)
        assert [_read(r.event_date, KYIV) for r in rows] == ["Wed 21 19:00", "Wed 28 19:00", "Wed 04 19:00"]
        # Noon in Indiana, then 13:00 for the one week Kyiv has changed and Indiana has not.
        assert [_read(r.event_date, INDY) for r in rows] == ["Wed 21 12:00", "Wed 28 13:00", "Wed 04 12:00"]
        assert {r.time_zone for r in rows} == {"Europe/Kyiv"}
        # What every reader's calendar is built from: the instants, which the
        # app then shows on the reader's own clock.
        r = client.get(f"/api/v1/calendar/events?course_id={course_id}")
        assert r.status_code == 200, r.text
        served = sorted(datetime.fromisoformat(e["event_date"]) for e in r.json() if e["source"] == "course_event")
        assert [_aware(s) for s in served] == KYIV_WEDNESDAYS_UTC

    def test_a_teacher_in_indiana_moving_a_kyiv_series_an_hour_later_keeps_eight_in_kyiv(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        # 19:00 → 20:00 on the first Wednesday, edited from Indiana. On
        # Kyiv's own clock the move is one hour on every lesson; measured on
        # Indiana's it would be one hour before its change and two after.
        course_id = _course(db, student)
        self._kyiv_series(client, course_id)
        first = self._rows(db, course_id)[0]
        r = client.put(
            f"{COURSES}/{course_id}/events/{first.id}?scope=following",
            json={"event_date": "2026-10-21T17:00:00Z", "time_zone": "America/Indiana/Indianapolis"},
        )
        assert r.status_code == 200, r.text
        rows = self._rows(db, course_id)
        assert [_read(r.event_date, KYIV) for r in rows] == ["Wed 21 20:00", "Wed 28 20:00", "Wed 04 20:00"]
        assert [_aware(r.event_date) for r in rows] == [s + timedelta(hours=1) for s in KYIV_WEDNESDAYS_UTC]
        assert {r.time_zone for r in rows} == {"Europe/Kyiv"}
        # Each moved lesson is announced again at its new hour.
        assert all(r.reminded_at is None for r in rows)


class TestADeadlineIsAMoment:
    """A deadline is set on one clock — «23:59 по Киеву» — and stored as the
    instant; a reader elsewhere sees the same instant on their own clock,
    which in the week between the changes is an hour from the usual."""

    @pytest.mark.parametrize(
        ("instant", "kyiv", "indiana"),
        [
            # Fri Oct 23: both on summer time (Kyiv UTC+3, Indiana UTC-4).
            (datetime(2026, 10, 23, 20, 59, tzinfo=UTC), "Fri 23 23:59", "Fri 23 16:59"),
            # Fri Oct 30: Kyiv back on UTC+2, Indiana still UTC-4.
            (datetime(2026, 10, 30, 21, 59, tzinfo=UTC), "Fri 30 23:59", "Fri 30 17:59"),
            # Fri Nov 6: both on winter time (UTC+2, UTC-5).
            (datetime(2026, 11, 6, 21, 59, tzinfo=UTC), "Fri 06 23:59", "Fri 06 16:59"),
        ],
        ids=["before-both", "week-between", "after-both"],
    )
    def test_23_59_in_kyiv_is_one_instant_everywhere(
        self, client: TestClient, db: Session, student: User, instant: datetime, kyiv: str, indiana: str
    ) -> None:
        from app.schemas.calendar import CalendarEvent as CalendarItem
        from app.services.event_reminders import send_due_reminders

        course_id = _course(db, student)
        r = client.post(
            f"{COURSES}/{course_id}/events",
            json={"title": "Эссе", "event_type": "deadline", "event_date": instant.isoformat()},
        )
        assert r.status_code == 201, r.text
        row = db.get(CourseEvent, uuid.UUID(r.json()["id"]))
        assert row is not None
        assert _read(row.event_date, KYIV) == kyiv
        assert _read(row.event_date, INDY) == indiana
        # The feed carries the instant and no length: a moment, not an hour.
        item = CalendarItem(
            id=str(row.id),
            title="Эссе",
            event_type="deadline",
            event_date=_aware(row.event_date),
            course_id=course_id,
            source="course_event",
        )
        for subscriber_zone in ("Europe/Kyiv", "America/Indiana/Indianapolis", None):
            ics = render_calendar([item], locale="ru", time_zone=subscriber_zone)
            assert f"DTSTART:{instant.strftime('%Y%m%dT%H%M%SZ')}" in ics
            assert "DURATION:PT0S" in ics
        # A deadline is not "starting": no hour-before reminder on any side of the change.
        assert send_due_reminders(db, now=instant - timedelta(minutes=30)) == 0


class TestTheInvitationNamesTheHour:
    """The invitation letter writes the first session on the school's clock,
    with that clock named — the one place the server itself prints a time."""

    @pytest.mark.parametrize(
        ("zone", "moment", "locale", "expected"),
        [
            (
                "Europe/Kyiv",
                datetime(2026, 10, 21, 16, 0, tzinfo=UTC),
                "ru",
                "21.10.2026, 19:00 по киевскому времени",
            ),
            (
                "Europe/Kyiv",
                datetime(2026, 10, 28, 17, 0, tzinfo=UTC),
                "ru",
                "28.10.2026, 19:00 по киевскому времени",
            ),
            (
                "Europe/Kyiv",
                datetime(2026, 11, 4, 17, 0, tzinfo=UTC),
                "uk",
                "04.11.2026, 19:00 за київським часом",
            ),
            # Indiana and the Pacific coast change together, so the pair holds all autumn.
            (
                "America/Indiana/Indianapolis",
                datetime(2026, 10, 31, 23, 0, tzinfo=UTC),
                "ru",
                "31.10.2026, 19:00 по времени Индианы (США) / 16:00 по тихоокеанскому времени США",
            ),
            (
                "America/Indiana/Indianapolis",
                datetime(2026, 11, 8, 0, 0, tzinfo=UTC),
                "en",
                "2026-11-07, 19:00 Eastern Time (Indiana, US) / 16:00 Pacific",
            ),
            # A school with no words for its zone is named by its offset, which the change moves.
            (
                "Europe/Berlin",
                datetime(2026, 10, 21, 17, 0, tzinfo=UTC),
                "de",
                "21.10.2026, 19:00 Zeit der Schule (UTC+2)",
            ),
            (
                "Europe/Berlin",
                datetime(2026, 10, 28, 18, 0, tzinfo=UTC),
                "de",
                "28.10.2026, 19:00 Zeit der Schule (UTC+1)",
            ),
        ],
    )
    def test_on_the_school_s_clock_on_every_side_of_the_change(
        self, zone: str, moment: datetime, locale: str, expected: str
    ) -> None:
        from app.services.email.invitation import _session_text

        text = _session_text(moment, locale, zone_or_utc(zone))  # type: ignore[arg-type]
        assert text == expected
