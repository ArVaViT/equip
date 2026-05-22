import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, func
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
        # The PROD partial UNIQUE INDEX (with COALESCE for the NULL cohort_id
        # sentinel) lives in the migration; SQLAlchemy can't express that
        # directly so we declare a plain three-column UniqueConstraint here
        # which is enough for the SQLite test path (NULL is treated as a
        # distinct value by SQLite UNIQUE, matching the COALESCE semantics).
        UniqueConstraint("user_id", "course_id", "cohort_id", name="uq_enrollment_user_course_cohort"),
        Index("ix_enrollments_course_id", "course_id"),
        Index("ix_enrollments_cohort_id", "cohort_id"),
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
