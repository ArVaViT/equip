from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas._request import RequestModel


class AnnouncementCreate(RequestModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=5000)
    course_id: str | None = Field(None, max_length=36)


class AnnouncementUpdate(RequestModel):
    title: str | None = Field(None, min_length=1, max_length=200)
    content: str | None = Field(None, min_length=1, max_length=5000)


class AnnouncementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    content: str
    course_id: str | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime | None = None
