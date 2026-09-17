import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StudentGrade(Base):
    __tablename__ = "student_grades"
    __table_args__ = (
        # One grade row per student, course and cohort -- a retake in a later
        # cohort is a new row (ADR-010). Production enforces it with the
        # NULLS NOT DISTINCT unique index from
        # ``20260521172911_student_grades_unique_constraint``, and it is the
        # only uniqueness on the table: a two-column (student_id, course_id)
        # constraint sat beside it until ``20260917030000`` and would have
        # refused the second cohort's grade. SQLite has no NULLS NOT DISTINCT,
        # so on the test backend two course-wide (cohort NULL) rows are not
        # refused; ``upsert_student_grade`` reads before it writes either way.
        UniqueConstraint(
            "student_id",
            "course_id",
            "cohort_id",
            name="uq_student_grades_student_course_cohort",
            postgresql_nulls_not_distinct=True,
        ),
        # At most one override. A row may hold a symbol, a number, or neither —
        # the last being a teacher who wrote a comment and left the grade
        # alone, which is an ordinary thing to do. Demanding exactly one made
        # comment-only rows illegal and forced clearing a grade to destroy the
        # comment with it.
        CheckConstraint(
            "(CASE WHEN override_code IS NULL THEN 0 ELSE 1 END + CASE WHEN override_score IS NULL THEN 0 ELSE 1 END) <= 1",
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
    graded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<StudentGrade id={self.id} student_id={self.student_id} course_id='{self.course_id}'>"
