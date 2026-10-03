from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_core import PydanticCustomError

from app.core.meeting_url import MeetingUrlRejected, normalize_meeting_url
from app.schemas._request import RequestModel

EventType = Literal["deadline", "live_session", "exam", "other"]


def _validated_meeting_url(value: str | None) -> str | None:
    """Where the live session happens, or ``None``.

    The rule itself is ``app.core.meeting_url``; this is the pydantic
    end of it. The refusal is raised as a ``PydanticCustomError`` with a
    stable ``type`` rather than a plain ``ValueError`` for the reason
    ``schemas/quiz.py`` does it: the ``type`` is an identifier the
    client translates (``errors.validation.meeting_url_*``), and the
    English ``msg`` beside it is for a log. A teacher who pastes the
    wrong thing has to be told what to do about it in the language the
    rest of her screen is in.
    """
    try:
        return normalize_meeting_url(value)
    except MeetingUrlRejected as exc:
        raise PydanticCustomError(
            f"meeting_url_{exc.reason.value}",
            "Meeting link rejected: {reason}",
            {"reason": exc.reason.value},
        ) from exc


def _as_utc_instant(value: datetime | None) -> datetime | None:
    """An event happens at one instant; the column is ``timestamptz``.

    The app always sends ``…Z`` (``localInputToIso``), but a bare
    ``2026-10-01T18:00:00`` from a script or an older client used to be
    accepted as-is and then read by Postgres in the session's zone —
    UTC on Supabase, and nothing in the response said so. Say it:
    a naive value means UTC, and the stored row carries the zone.
    """
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


class EventRepeat(RequestModel):
    """Repeat the new event every ``every_weeks`` weeks through ``until``.

    ``until`` is a day on the calendar of ``time_zone`` — the zone the
    teacher is scheduling in, which the client knows and the server does
    not — and is inclusive. Without a zone the teacher's profile zone is
    used, then UTC.
    """

    every_weeks: int = Field(1, ge=1, le=4)
    until: date
    time_zone: str | None = Field(None, max_length=64)


class CourseEventCreate(RequestModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    event_type: EventType = "other"
    event_date: datetime
    #: Optional on purpose — a deadline and an exam in a room have
    #: nothing to join. No ``max_length`` here: the length rule lives in
    #: ``normalize_meeting_url`` so that an over-long paste is refused
    #: with the same translated sentence as every other bad link,
    #: instead of pydantic's generic ``string_too_long``.
    meeting_url: str | None = None
    #: The recording, once there is one. Same rule as the meeting link.
    recording_url: str | None = None
    #: Minutes. ``None`` for a moment rather than a span — a deadline.
    #: A day is the ceiling: past it, it is not one event.
    duration_minutes: int | None = Field(None, ge=1, le=1440)
    #: Present to create a weekly series instead of one event.
    repeat: EventRepeat | None = None

    _event_date_utc = field_validator("event_date")(_as_utc_instant)
    _meeting_url = field_validator("meeting_url", "recording_url")(_validated_meeting_url)


class CourseEventUpdate(RequestModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    event_type: EventType | None = None
    event_date: datetime | None = None
    #: ``None`` clears the link. ``exclude_unset`` in the route is what
    #: separates "clear it" from "leave it alone" — a patch that omits
    #: the key never touches the column.
    meeting_url: str | None = None
    #: The recording, once there is one. Same rule as the meeting link.
    recording_url: str | None = None
    #: ``None`` clears it, like the links.
    #: A day is the ceiling: past it, it is not one event.
    duration_minutes: int | None = Field(None, ge=1, le=1440)
    #: The zone a "this and following" move is measured in, so that
    #: 20:00 → 19:00 lands at 19:00 on every lesson's own day across a
    #: clock change. Ignored for a single event.
    time_zone: str | None = Field(None, max_length=64)

    _event_date_utc = field_validator("event_date")(_as_utc_instant)
    _meeting_url = field_validator("meeting_url", "recording_url")(_validated_meeting_url)


#: Which occurrences of a series an edit or a delete reaches.
SeriesScope = Literal["this", "following", "all"]


class CourseEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: str
    title: str
    description: str | None = None
    event_type: str
    event_date: datetime
    meeting_url: str | None = None
    recording_url: str | None = None
    duration_minutes: int | None = None
    series_id: UUID | None = None
    created_by: UUID
    created_at: datetime


class CalendarEvent(BaseModel):
    id: str
    title: str
    description: str | None = None
    event_type: str
    event_date: datetime
    #: Only a ``course_event`` can carry one. A module or assignment
    #: deadline is a date, not a meeting, so this stays ``None`` for
    #: both — and the clients render the join button on its presence,
    #: never on the event type.
    meeting_url: str | None = None
    #: Where to watch it afterwards. Like the meeting link, only a
    #: ``course_event`` can carry one.
    recording_url: str | None = None
    #: Minutes, for a ``course_event`` that has a length.
    duration_minutes: int | None = None
    #: Shared by the occurrences of one weekly series.
    series_id: str | None = None
    course_id: str
    course_title: str | None = None
    source: Literal["module_deadline", "assignment_deadline", "course_event"]
