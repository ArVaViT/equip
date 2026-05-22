"""Cohort + CohortCourse models.

Cohort is a **top-level admin entity** (ADR-010): a named batch of
students that takes some set of courses together over a date window.
The director creates an empty cohort, then independently adds courses
to it (via the ``cohort_courses`` junction) and students to it (via the
``enrollments`` rows whose ``cohort_id`` points at this cohort).

Teachers do not own or manage cohorts; they only see the cohort id as
a filter dropdown in their own course's gradebook.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CohortStatus(enum.StrEnum):
    """Forward-only cohort lifecycle: ``upcoming → active → completed``.

    Going back from ``completed`` is blocked at the route layer (see
    ``update_cohort``) — a completed cohort's grades and certificates
    are frozen.
    """

    UPCOMING = "upcoming"
    ACTIVE = "active"
    COMPLETED = "completed"


class Cohort(Base):
    __tablename__ = "cohorts"
    __table_args__ = (
        Index("ix_cohorts_status", "status"),
        Index("ix_cohorts_created_by", "created_by"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    enrollment_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enrollment_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 'upcoming' before start_date, 'active' inside the window, 'completed'
    # after end_date or when director marks it done early. Transitions are
    # currently manual via the cohorts API; auto-transition on dates is a
    # follow-up if it ever matters.
    status: Mapped[str] = mapped_column(String(20), default="upcoming")
    max_students: Mapped[int | None] = mapped_column()
    # Director / admin who set the cohort up. NULL means the creator was
    # deleted from the platform — cohort survives so historical
    # enrollments and grades stay intact.
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Cohort id={self.id} name='{self.name}'>"


class CohortCourse(Base):
    """Junction: which courses run in which cohorts.

    When a course is added to a cohort that already has students, the
    cohort service is responsible for backfilling enrollment rows for
    every existing cohort student (and vice versa: adding a student to
    a cohort enrolls them in all already-attached courses). Removing
    detaches but keeps historical enrollment rows with ``cohort_id``
    nulled — see ADR-010 §5.
    """

    __tablename__ = "cohort_courses"
    __table_args__ = (Index("ix_cohort_courses_course_id", "course_id"),)

    cohort_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("cohorts.id", ondelete="CASCADE"), primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True)
    added_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<CohortCourse cohort_id={self.cohort_id} course_id={self.course_id!r}>"
