import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CertificateStatus(enum.StrEnum):
    """Certificate request → approve → issue state machine.

    ``pending`` — student requested. Teacher must approve first.
    ``teacher_approved`` — instructor signed off. Admin issues from here.
    ``approved`` — admin issued; ``certificate_number`` populated.
    ``rejected`` — either reviewer can reject before issuance.
    """

    PENDING = "pending"
    TEACHER_APPROVED = "teacher_approved"
    APPROVED = "approved"
    REJECTED = "rejected"


class Certificate(Base):
    __tablename__ = "certificates"
    __table_args__ = (
        # The unique constraint already backs a B-tree on
        # ``(user_id, course_id)``; a separate identical index was pure
        # duplication (same columns, same order).
        UniqueConstraint("user_id", "course_id", name="uq_certificate_user_course"),
        Index("ix_certificates_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column()
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    certificate_number: Mapped[str | None] = mapped_column(String(50), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    teacher_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    teacher_approved_by: Mapped[uuid.UUID | None] = mapped_column()
    admin_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    admin_approved_by: Mapped[uuid.UUID | None] = mapped_column()
    # ``cohort_id`` carries an FK to ``cohorts.id`` with ``ON DELETE SET NULL``
    # — cohorts are metadata, not a load-bearing identity for the cert, so
    # deleting a cohort must not destroy issued certs. The constraint already
    # lives in prod; the model just never declared it, leaving the CI
    # schema-smoke job blind to the relationship. See migration
    # ``20260516021349_certificates_cohort_fk_ensure.sql``.
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cohorts.id", ondelete="SET NULL"), nullable=True)
