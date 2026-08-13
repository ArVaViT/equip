from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

#: The kinds this product actually emits. Mirrors the TS ``NotificationType``
#: union in ``frontend/src/types/index.ts``.
#:
#: This used to be a ``Literal`` on the **response** model, described in a
#: comment as "the only thing keeping a typo from sneaking past the API layer".
#: It was doing the opposite. It was missing ``retake_requested`` — a kind
#: ``grades.py`` has been writing for weeks — so ``GET /api/v1/notifications``
#: answered **500** for every user who had one, and the bell was dead for them.
#: Production logged it seven times in six hours before anybody looked.
#:
#: It was also too wide: ``course_update`` and ``enrollment_confirmed`` appear
#: in nobody's write path.
#:
#: The guard belongs where typos happen, which is the **write**, not the read.
#: A list response must never fail because one row is unfamiliar, and it does
#: not need to: ``title`` and ``message`` are server-rendered human strings,
#: and the client already falls back to a bell icon for a kind it does not
#: recognise. ``test_notification_kinds.py`` walks every call site instead.
NOTIFICATION_TYPES: frozenset[str] = frozenset(
    {
        "certificate_approved",
        "certificate_rejected",
        "assignment_graded",
        "new_announcement",
        "retake_requested",
    }
)


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    #: Deliberately `str`, not a Literal — see the note on `NOTIFICATION_TYPES`.
    type: str
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
