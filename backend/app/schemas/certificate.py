from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CertificateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    # Nullable: the course this certificate was issued for may have been
    # deleted. ``archived_course_title`` preserves the title for verification.
    course_id: str | None = None
    archived_course_title: str | None = None
    issued_at: datetime | None = None
    certificate_number: str | None = None
    status: str = "pending"
    requested_at: datetime | None = None
    teacher_approved_at: datetime | None = None
    teacher_approved_by: UUID | None = None
    admin_approved_at: datetime | None = None
    admin_approved_by: UUID | None = None


class CertificateVerifyResponse(BaseModel):
    valid: bool
    certificate_number: str
    user_name: str | None = None
    course_title: str | None = None
    issued_at: datetime | None = None
