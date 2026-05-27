from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

# Mirrors the Postgres ``certificates_status_check`` CHECK constraint
# and the SQLAlchemy ``CertificateStatus`` enum. Without the Literal
# here, ``CertificateResponse.status`` was ``str`` — any value would
# deserialise, including ones the DB CHECK would later reject.
CertificateStatus = Literal["pending", "teacher_approved", "approved", "rejected"]


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
    status: CertificateStatus = "pending"
    requested_at: datetime | None = None
    teacher_approved_at: datetime | None = None
    teacher_approved_by: UUID | None = None
    admin_approved_at: datetime | None = None
    admin_approved_by: UUID | None = None
    # Optional enrichment fields populated by the pending-cert listing
    # endpoints (teacher + admin panels). Pydantic skips them when the
    # source ORM row doesn't carry them, so the broader fan-out of
    # ``CertificateResponse`` consumers (student "my certs", course
    # detail, etc.) keeps its slim payload.
    student_name: str | None = None
    student_email: str | None = None
    course_title: str | None = None
    teacher_approver_name: str | None = None


class CertificateVerifyResponse(BaseModel):
    valid: bool
    certificate_number: str
    user_name: str | None = None
    course_title: str | None = None
    issued_at: datetime | None = None
