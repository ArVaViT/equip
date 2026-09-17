import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        Index("ix_assignments_chapter_id", "chapter_id"),
        # Mirror prod: max_score must be positive.
        CheckConstraint("max_score > 0", name="assignments_max_score_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"))
    # Title + description columns dropped — cv is the only
    # store. Reads go through fetch_cv_entity_texts_with_fallback;
    # writes through dual_write_entity_content(texts={...}).
    max_score: Mapped[int] = mapped_column(default=100)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AssignmentSubmission(Base):
    __tablename__ = "assignment_submissions"
    __table_args__ = (
        # A student hands in as many times as the work allows, one row each;
        # the newest row is the one that counts. Nothing here is unique on
        # (assignment_id, student_id) -- production carried such a constraint
        # until 20260917030000 and it turned every second hand-in into a 409.
        # This index serves the per-assignment list, a student's own history
        # for one assignment, and ``latest_submissions``.
        Index(
            "ix_assignment_submissions_assignment_student_submitted",
            "assignment_id",
            "student_id",
            text("submitted_at DESC"),
        ),
        Index("idx_submissions_student_id", "student_id"),
        # Mirror prod CHECK constraints (status domain + non-negative grade).
        CheckConstraint(
            "status IN ('submitted', 'graded', 'returned')",
            name="assignment_submissions_status_check",
        ),
        CheckConstraint("grade IS NULL OR grade >= 0", name="assignment_submissions_grade_nonneg"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"))
    student_id: Mapped[uuid.UUID] = mapped_column()
    content: Mapped[str | None] = mapped_column(Text)
    file_url: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), default="submitted")
    grade: Mapped[int | None] = mapped_column()
    feedback: Mapped[str | None] = mapped_column(Text)
    graded_by: Mapped[uuid.UUID | None] = mapped_column()
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
