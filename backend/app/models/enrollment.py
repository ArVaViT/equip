import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.user import User


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        # Uniqueness is on (user, course, cohort) — ADR-010 §3. Retake in a
        # later cohort writes a NEW row, preserving the historical attempt.
        # The COALESCE is the point: without it two enrolments in the same
        # course with no cohort would both be accepted, because a UNIQUE treats
        # NULLs as distinct. Same expression as production, so SQLite refuses
        # the same second row Postgres does.
        Index(
            "uq_enrollment_user_course_cohort",
            "user_id",
            "course_id",
            text("COALESCE(cohort_id, '00000000-0000-0000-0000-000000000000')"),
            unique=True,
        ),
        Index("ix_enrollments_course_id", "course_id"),
        Index("ix_enrollments_cohort_id", "cohort_id"),
        # Mirror prod: progress is a 0..100 percentage.
        CheckConstraint("progress >= 0 AND progress <= 100", name="enrollments_progress_range"),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id"))
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"))
    cohort_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("cohorts.id", ondelete="SET NULL"))
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    progress: Mapped[int] = mapped_column(default=0)

    user: Mapped["User"] = relationship(back_populates="enrollments")
    course: Mapped["Course"] = relationship(back_populates="enrollments")

    def __repr__(self) -> str:
        return f"<Enrollment id={self.id!r} user_id={self.user_id} course_id={self.course_id!r}>"
