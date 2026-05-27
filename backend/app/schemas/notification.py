from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# The full set of notification kinds the system emits. Mirrors the TS
# ``NotificationType`` union in ``frontend/src/types/index.ts``.
# Postgres has no CHECK on ``notifications.type`` (it's free-form
# ``VARCHAR(50)`` so future kinds don't need a migration), so this
# Literal is the only thing keeping a typo'd ``'certificat_approved'``
# from sneaking past the API layer.
NotificationType = Literal[
    "certificate_approved",
    "certificate_rejected",
    "assignment_graded",
    "new_announcement",
    "course_update",
    "enrollment_confirmed",
]


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    type: NotificationType
    title: str
    message: str
    link: str | None = None
    is_read: bool = False
    created_at: datetime
    metadata: dict[str, Any] | None = Field(None, validation_alias="meta")


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    page: int
    page_size: int


class UnreadCountResponse(BaseModel):
    count: int
