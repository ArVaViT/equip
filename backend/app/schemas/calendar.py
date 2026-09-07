from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas._request import RequestModel

EventType = Literal["deadline", "live_session", "exam", "other"]


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

    _event_date_utc = field_validator("event_date")(_as_utc_instant)


class CourseEventUpdate(RequestModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    event_type: EventType | None = None
    event_date: datetime | None = None

    _event_date_utc = field_validator("event_date")(_as_utc_instant)


class CourseEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    course_id: str
    title: str
    description: str | None = None
    event_type: str
    event_date: datetime
    created_by: UUID
    created_at: datetime


class CalendarEvent(BaseModel):
    id: str
    title: str
    description: str | None = None
    event_type: str
    event_date: datetime
    course_id: str
    course_title: str | None = None
    source: Literal["module_deadline", "assignment_deadline", "course_event"]
