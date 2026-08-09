import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StudentGrade(Base):
    __tablename__ = "student_grades"
    __table_args__ = (
        Index("ix_student_grades_student_course", "student_id", "course_id"),
        Index("ix_student_grades_student_course_cohort", "student_id", "course_id", "cohort_id"),
        # The unique constraint is enforced in Postgres via the
        # NULLS-NOT-DISTINCT index added in migration
        # ``20260521172911_student_grades_unique_constraint``. SQLite (the
        # test backend) treats NULLs as distinct in unique constraints, so
        # the test-side check is "best effort" -- it still catches the
        # non-NULL-cohort race. Production safety comes from the migration.
        UniqueConstraint(
            "student_id",
            "course_id",
            "cohort_id",
            name="uq_student_grades_student_course_cohort",
        ),
        # A row exists only to express an override: a symbol or a number, never
        # both and never neither. "Neither" is what a cleared override would
        # look like — and a cleared override is a deleted row, not a row full
        # of NULLs.
        CheckConstraint(
            "(CASE WHEN override_code IS NULL THEN 0 ELSE 1 END + CASE WHEN override_score IS NULL THEN 0 ELSE 1 END) = 1",
            name="ck_student_grades_one_override",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column()
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cohorts.id", ondelete="SET NULL"))
    # Exactly one of these two holds the override (D7). Canonical codes, never
    # localized text: «зачёт» and «4 (хорошо)» are display, built from the code
    # and the reader's locale. Free text let "Aa+" through and could not fit
    # «удовлетворительно» in ten characters.
    override_code: Mapped[str | None] = mapped_column(String(8))
    override_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    # What the calculator said when the override was set. Kept so both numbers
    # can be shown side by side — a hand-set grade should be visible as one.
    computed_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    # Optional. Mandatory reasons tax the common, kind case; accountability
    # comes from the audit trail and the override glyph instead (D7).
    reason: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    graded_by: Mapped[uuid.UUID | None] = mapped_column()
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<StudentGrade id={self.id} student_id={self.student_id} course_id='{self.course_id}'>"
