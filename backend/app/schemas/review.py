from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas._request import RequestModel


class ReviewCreate(RequestModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = Field(None, max_length=5000)


class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    course_id: str
    rating: int
    comment: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
