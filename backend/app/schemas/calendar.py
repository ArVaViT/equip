from datetime import UTC, datetime
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

    _event_date_utc = field_validator("event_date")(_as_utc_instant)
    _meeting_url = field_validator("meeting_url")(_validated_meeting_url)


class CourseEventUpdate(RequestModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    event_type: EventType | None = None
    event_date: datetime | None = None
    #: ``None`` clears the link. ``exclude_unset`` in the route is what
    #: separates "clear it" from "leave it alone" — a patch that omits
    #: the key never touches the column.
    meeting_url: str | None = None

    _event_date_utc = field_validator("event_date")(_as_utc_instant)
    _meeting_url = field_validator("meeting_url")(_validated_meeting_url)


class CourseEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: str
    title: str
    description: str | None = None
    event_type: str
    event_date: datetime
    meeting_url: str | None = None
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
    course_id: str
    course_title: str | None = None
    source: Literal["module_deadline", "assignment_deadline", "course_event"]
