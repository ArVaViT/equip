import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
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
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column()
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cohorts.id", ondelete="SET NULL"))
    grade: Mapped[str | None] = mapped_column(String(10))
    comment: Mapped[str | None] = mapped_column(Text)
    graded_by: Mapped[uuid.UUID | None] = mapped_column()
    graded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<StudentGrade id={self.id} student_id={self.student_id} course_id='{self.course_id}'>"
