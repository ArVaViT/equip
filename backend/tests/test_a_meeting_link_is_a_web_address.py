# ruff: noqa: RUF001
# The fixtures are Russian course text; Cyrillic letters that look like
# Latin ones are the content, not a slip.
"""A live session says where to join, and only ever with a web address.

The first teacher on the platform runs a preachers' course entirely in
Zoom. ``live_session`` was already in the event vocabulary, so the class
could be announced and the room could not — the address went into the
description, which is the one translated field on the row, and which no
machine-readable surface can mine a link out of.

The link is now its own column, and the thing worth testing hardest is
the gate in front of it. It is written by a teacher and rendered to
every student as something clickable, so it is the one place in the
product where somebody else's string becomes an ``href``. A
``javascript:`` value there runs in the reader's session on click.

So: the allowlist holds (only ``http`` / ``https`` with a host), the
disguised host is refused on its own terms, the value reaches every
surface a student looks at, and an event with no link shows no button
anywhere.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from app.core.meeting_url import (
    MEETING_URL_MAX_LENGTH,
    MeetingUrlRejected,
    MeetingUrlRejection,
    normalize_meeting_url,
)
from app.models.enrollment import Enrollment
from app.models.notification import Notification
from app.schemas.calendar import CalendarEvent
from app.services.calendar_ical import render_calendar

from ._cv_helpers import make_course_with_text
from .conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User

COURSES = "/api/v1/courses"
CALENDAR = "/api/v1/calendar/events"

ZOOM = "https://zoom.us/j/1234567890?pwd=aB3dEf"


# ── The rule itself ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        ZOOM,
        "https://meet.google.com/abc-defg-hij",
        "http://meet.example.org/room",  # plain http is a real, working link
        "https://zoom.us:8443/j/1",  # an explicit port
        "https://zoom.us/j/1?to=pastor@example.com",  # @ outside the authority
        "HTTPS://ZOOM.US/j/1",  # a scheme is case-insensitive
        "https://xn--80aswg.xn--p1ai/room",  # a punycoded host
    ],
)
def test_a_web_address_is_kept_exactly_as_it_was_typed(value: str) -> None:
    # Byte-for-byte: a Zoom password lives in the query, and any
    # normalisation that re-encodes it yields a link that joins nothing.
    assert normalize_meeting_url(value) == value


@pytest.mark.parametrize("value", [None, "", "   ", "\n\t "])
def test_nothing_typed_is_not_a_link_and_not_an_error(value: str | None) -> None:
    # Most events have no meeting. A form that submits "" for a field
    # nobody touched must not be treated as an attempt at a link.
    assert normalize_meeting_url(value) is None


def test_surrounding_whitespace_is_trimmed_rather_than_refused() -> None:
    assert normalize_meeting_url(f"  {ZOOM}\n") == ZOOM


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(document.cookie)",
        "JaVaScRiPt:alert(1)",
        "  javascript:alert(1)",  # leading space does not launder the scheme
        "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
        "vbscript:msgbox(1)",
        "file:///etc/passwd",
        "mailto:pastor@example.com",
        "tel:+13175551234",
        "/calendar?course=acts",  # a path on Equip is not a meeting
        "//evil.example.com/j/1",  # protocol-relative
        "zoom.us/j/1234567890",  # no scheme: will not open
        "www.zoom.us",
        "https://",
        "https:",
        "https:///room",  # a scheme and no site
        "просто текст",
        "поговорим в зуме",
    ],
)
def test_anything_that_is_not_a_web_address_is_refused(value: str) -> None:
    with pytest.raises(MeetingUrlRejected) as raised:
        normalize_meeting_url(value)
    assert raised.value.reason is MeetingUrlRejection.NOT_A_WEB_ADDRESS


@pytest.mark.parametrize(
    "value",
    [
        "https://zoom.us\nSUMMARY:injected",  # would write its own ICS property
        "https://zoom.us\r\nLOCATION:elsewhere",
        "https://zoom.us/j/1\twith-a-tab",
        "https://zoom.us/j/1\x00",
        "https://zoom.us/j/ 1",  # NO-BREAK SPACE, from a word processor
        "https://zoom.us/j/ 1",  # a line terminator to a JS parser
        "﻿https://zoom.us/j/1",  # a BOM the outer strip() does not take
    ],
)
def test_a_link_cannot_carry_a_line_ending_or_an_invisible_space(value: str) -> None:
    # The iCalendar feed writes this value into a property line, and a
    # newline in it would end that line and start one of the attacker's.
    with pytest.raises(MeetingUrlRejected) as raised:
        normalize_meeting_url(value)
    assert raised.value.reason is MeetingUrlRejection.NOT_A_WEB_ADDRESS


def test_an_invisible_space_around_the_edges_is_trimmed_rather_than_refused() -> None:
    """``str.strip()`` counts U+2028 and U+00A0 as whitespace, so one
    hanging off either end is gone before the value is inspected — which
    is the right outcome and worth pinning, because it is the reason the
    check above has to look *inside* the string rather than trusting the
    strip. A teacher who pastes out of a word processor picks these up
    without ever seeing them."""
    assert normalize_meeting_url("\u00a0https://zoom.us/j/1\u2028") == "https://zoom.us/j/1"


@pytest.mark.parametrize(
    "value",
    [
        "https://zoom.us@evil.example.com/j/1",
        "https://user:password@evil.example.com/",
        "https://@evil.example.com/",
    ],
)
def test_a_host_wearing_another_host_as_a_costume_is_refused_on_its_own_terms(value: str) -> None:
    # These start with https:// and are links to evil.example.com. Told
    # only "must start with https://", a teacher looking at a link that
    # starts with https:// concludes the product is broken — so this
    # refusal carries its own explanation.
    with pytest.raises(MeetingUrlRejected) as raised:
        normalize_meeting_url(value)
    assert raised.value.reason is MeetingUrlRejection.CREDENTIALS_IN_URL


def test_a_paste_that_is_not_a_link_is_refused_as_a_length() -> None:
    with pytest.raises(MeetingUrlRejected) as raised:
        normalize_meeting_url("https://zoom.us/j/" + "1" * MEETING_URL_MAX_LENGTH)
    assert raised.value.reason is MeetingUrlRejection.TOO_LONG


def test_a_link_of_exactly_the_maximum_length_is_still_a_link() -> None:
    value = "https://zoom.us/j/" + "1" * (MEETING_URL_MAX_LENGTH - len("https://zoom.us/j/"))
    assert len(value) == MEETING_URL_MAX_LENGTH
    assert normalize_meeting_url(value) == value


# ── The route ────────────────────────────────────────────────────────


def _published_course_with_student(db: Session, student: User) -> str:
    student.preferred_locale = "ru"
    course = make_course_with_text(
        db,
        course_id=f"live-{uuid.uuid4().hex[:6]}",
        title="Карта в кармане",
        status="published",
        source_locale="ru",
        created_by=TEACHER_ID,
    )
    db.add(Enrollment(id=f"e-{uuid.uuid4().hex[:6]}", user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.commit()
    return course.id


def _create_event(client: TestClient, course_id: str, **extra: object) -> dict:
    payload = {
        "title": "Занятие по проповеди",
        "event_type": "live_session",
        "event_date": "2026-10-03T18:00:00Z",
        **extra,
    }
    return client.post(f"{COURSES}/{course_id}/events", json=payload)  # type: ignore[return-value]


class TestTheTeacherSavesTheRoom:
    def test_a_zoom_link_comes_back_on_the_event_it_was_saved_on(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _published_course_with_student(db, student)
        r = _create_event(client, course_id, meeting_url=ZOOM)
        assert r.status_code == 201
        assert r.json()["meeting_url"] == ZOOM

    def test_an_event_with_no_meeting_says_so_rather_than_guessing(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _published_course_with_student(db, student)
        r = _create_event(client, course_id, event_type="deadline")
        assert r.status_code == 201
        assert r.json()["meeting_url"] is None

    def test_a_blank_field_is_no_meeting_rather_than_an_error(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _published_course_with_student(db, student)
        r = _create_event(client, course_id, meeting_url="   ")
        assert r.status_code == 201
        assert r.json()["meeting_url"] is None

    def test_the_link_can_be_added_later_and_taken_back_off(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _published_course_with_student(db, student)
        event_id = _create_event(client, course_id).json()["id"]

        added = client.put(f"{COURSES}/{course_id}/events/{event_id}", json={"meeting_url": ZOOM})
        assert added.json()["meeting_url"] == ZOOM

        # A patch that does not mention the field leaves it alone…
        untouched = client.put(f"{COURSES}/{course_id}/events/{event_id}", json={"title": "Занятие 2"})
        assert untouched.json()["meeting_url"] == ZOOM

        # …and an explicit null is how the teacher clears it.
        cleared = client.put(f"{COURSES}/{course_id}/events/{event_id}", json={"meeting_url": None})
        assert cleared.json()["meeting_url"] is None


class TestTheRefusalIsSomethingTheTeacherCanActOn:
    """The refusal has to name what is wrong specifically enough for the
    client to say it in the reader's language: the ``type`` is the
    identifier the frontend translates (``errors.validation.*``), the
    English ``msg`` beside it is for a log."""

    def _refusal_types(self, response) -> list[str]:  # type: ignore[no-untyped-def]
        return [entry["type"] for entry in response.json()["detail"]]

    @pytest.mark.parametrize(
        "value",
        ["javascript:alert(1)", "data:text/html,<script>alert(1)</script>", "zoom.us/j/1", "/calendar"],
    )
    def test_a_value_that_is_not_a_web_address_is_refused_by_the_route(
        self, client: TestClient, db: Session, student: User, value: str
    ) -> None:
        course_id = _published_course_with_student(db, student)
        r = _create_event(client, course_id, meeting_url=value)
        assert r.status_code == 422
        assert "meeting_url_not_a_web_address" in self._refusal_types(r)

    def test_a_disguised_host_is_refused_with_its_own_explanation(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _published_course_with_student(db, student)
        r = _create_event(client, course_id, meeting_url="https://zoom.us@evil.example.com/j/1")
        assert r.status_code == 422
        assert "meeting_url_credentials_in_url" in self._refusal_types(r)

    def test_an_over_long_value_is_refused_as_a_length(self, client: TestClient, db: Session, student: User) -> None:
        course_id = _published_course_with_student(db, student)
        r = _create_event(client, course_id, meeting_url="https://zoom.us/" + "x" * MEETING_URL_MAX_LENGTH)
        assert r.status_code == 422
        assert "meeting_url_too_long" in self._refusal_types(r)

    def test_the_refusal_names_the_field_so_the_client_can_point_at_it(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _published_course_with_student(db, student)
        r = _create_event(client, course_id, meeting_url="javascript:alert(1)")
        assert ["body", "meeting_url"] in [entry["loc"] for entry in r.json()["detail"]]

    def test_a_refused_link_saves_no_event_at_all(self, client: TestClient, db: Session, student: User) -> None:
        # The whole body is refused, so the teacher does not end up with
        # an event that quietly lost the half she cared about.
        course_id = _published_course_with_student(db, student)
        _create_event(client, course_id, meeting_url="javascript:alert(1)")
        assert client.get(f"{COURSES}/{course_id}/events").json() == []


# ── Every surface a student looks at ─────────────────────────────────


class TestTheLinkReachesTheStudent:
    def test_the_course_page_list_carries_it(self, client: TestClient, db: Session, student: User) -> None:
        course_id = _published_course_with_student(db, student)
        _create_event(client, course_id, meeting_url=ZOOM)
        rows = client.get(f"{COURSES}/{course_id}/events").json()
        assert [row["meeting_url"] for row in rows] == [ZOOM]

    def test_the_calendar_feed_carries_it(self, client: TestClient, db: Session, student: User) -> None:
        course_id = _published_course_with_student(db, student)
        _create_event(client, course_id, meeting_url=ZOOM)
        rows = client.get(CALENDAR).json()
        assert [(row["source"], row["meeting_url"]) for row in rows] == [("course_event", ZOOM)]

    def test_a_reader_of_another_language_gets_the_same_address(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        # The title is translated; the address is not. A German student
        # must be sent to the room the teacher actually opened.
        course_id = _published_course_with_student(db, student)
        _create_event(client, course_id, meeting_url=ZOOM)
        rows = client.get(f"{COURSES}/{course_id}/events", headers={"Accept-Language": "de"}).json()
        assert [row["meeting_url"] for row in rows] == [ZOOM]

    def test_the_bell_carries_it_so_a_student_can_join_from_the_notification(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        course_id = _published_course_with_student(db, student)
        _create_event(client, course_id, meeting_url=ZOOM)
        rows = db.query(Notification).filter(Notification.type == "new_event").all()
        assert len(rows) == 1
        assert rows[0].meta["meeting_url"] == ZOOM

    def test_the_reschedule_notice_carries_the_link_too(self, client: TestClient, db: Session, student: User) -> None:
        course_id = _published_course_with_student(db, student)
        event_id = _create_event(client, course_id, meeting_url=ZOOM).json()["id"]
        client.put(f"{COURSES}/{course_id}/events/{event_id}", json={"event_date": "2026-10-10T18:00:00Z"})
        moved = db.query(Notification).filter(Notification.type == "event_rescheduled").all()
        assert len(moved) == 1
        assert moved[0].meta["meeting_url"] == ZOOM

    def test_an_event_with_no_meeting_puts_no_empty_key_in_the_bell(
        self, client: TestClient, db: Session, student: User
    ) -> None:
        # The client draws the join button off this key's presence, so
        # an absent meeting must be an absent key — not an empty string.
        course_id = _published_course_with_student(db, student)
        _create_event(client, course_id, event_type="deadline")
        rows = db.query(Notification).filter(Notification.type == "new_event").all()
        assert "meeting_url" not in rows[0].meta

    def test_a_deadline_is_a_moment_and_never_a_room(self, client: TestClient, db: Session, student: User) -> None:
        course_id = _published_course_with_student(db, student)
        _create_event(client, course_id, event_type="deadline")
        assert [row["meeting_url"] for row in client.get(CALENDAR).json()] == [None]


# ── The subscribed calendar ──────────────────────────────────────────


def _ics_event(meeting_url: str | None) -> CalendarEvent:
    return CalendarEvent(
        id="e-1",
        title="Занятие по проповеди",
        description=None,
        event_type="live_session",
        event_date=datetime(2026, 10, 3, 18, 0, tzinfo=UTC),
        meeting_url=meeting_url,
        course_id="c-1",
        course_title="Карта в кармане",
        source="course_event",
    )


class TestTheSubscribedCalendarShowsAWayIn:
    def test_both_properties_are_emitted_because_neither_client_reads_both(self) -> None:
        # Apple Calendar shows URL and does not linkify LOCATION; Google
        # Calendar ignores URL on an imported event and linkifies a
        # LOCATION that parses as one. Zoom's own .ics emits both.
        ics = render_calendar([_ics_event(ZOOM)])
        assert f"LOCATION:{ZOOM}\r\n" in ics
        assert f"URL:{ZOOM}\r\n" in ics

    def test_location_is_escaped_as_text_and_the_url_is_left_as_a_uri(self) -> None:
        # LOCATION is TEXT (RFC 5545 §3.8.1.7) and its commas are
        # escaped; URL is URI (§3.8.4.6) and must not be, or the client
        # hands the student a link with backslashes in it.
        with_comma = "https://zoom.us/j/1?note=a,b"
        ics = render_calendar([_ics_event(with_comma)])
        assert "LOCATION:https://zoom.us/j/1?note=a\\,b\r\n" in ics
        assert f"URL:{with_comma}\r\n" in ics

    def test_an_event_with_no_meeting_writes_neither_property(self) -> None:
        ics = render_calendar([_ics_event(None)])
        assert "LOCATION:" not in ics
        assert "URL:" not in ics
