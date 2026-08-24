from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas._request import RequestModel

EventType = Literal["deadline", "live_session", "exam", "other"]


class CourseEventCreate(RequestModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    event_type: EventType = "other"
    event_date: datetime


class CourseEventUpdate(RequestModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    event_type: EventType | None = None
    event_date: datetime | None = None


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
