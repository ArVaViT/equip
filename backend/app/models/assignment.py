import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
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
    # Phase 5e3: title + description columns dropped — cv is the only
    # store. Reads go through fetch_cv_entity_texts_with_fallback;
    # writes through dual_write_entity_content(texts={...}).
    max_score: Mapped[int] = mapped_column(default=100)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AssignmentSubmission(Base):
    __tablename__ = "assignment_submissions"
    __table_args__ = (
        Index("ix_assignment_subs_student_assignment", "student_id", "assignment_id"),
        Index("ix_assignment_subs_assignment_id", "assignment_id"),
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
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(20), default="submitted")
    grade: Mapped[int | None] = mapped_column()
    feedback: Mapped[str | None] = mapped_column(Text)
    graded_by: Mapped[uuid.UUID | None] = mapped_column()
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
