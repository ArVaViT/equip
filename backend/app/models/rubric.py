"""Rubrics — the same standard applied to the twentieth essay as to the first.

Design: `assessment-integrity-and-the-graders-day.md` §6.3.

The argument for rubrics here is not speed. It is that a grade which is one
person's impression cannot be discussed, and a grade which is four named
criteria with a level chosen on each can be — by the student who disagrees,
by the director who signs the ведомость, and by the teacher themselves on the
twentieth essay of an evening.

**The decision recorded is the level, never the number.** Points live on the
level and are read through it. That ordering is what lets a school decide
a level is worth eight points rather than seven, edit it once, and have every mark resting on it
follow — instead of a teacher reopening finished essays by hand. The corollary
is that levels are archived, never deleted: a deleted level turns every mark
that referenced it into a mark by nobody, for nothing.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Rubric(Base):
    """A named marking standard, belonging to a course.

    Course-scoped and reusable across the assignments in it — «наша стандартная
    рубрика эссе» is a real thing a school asks for. It travels with the course
    when the course is cloned, like the rest of the grading configuration (D13).
    """

    __tablename__ = "rubrics"
    __table_args__ = (Index("ix_rubrics_course", "course_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    #: Archived rather than deleted: a rubric referenced by a mark on a closed
    #: ведомость has to stay readable for as long as that document exists.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RubricCriterion(Base):
    """One thing being judged. «Аргумент опирается на текст», not «Качество»."""

    __tablename__ = "rubric_criteria"
    __table_args__ = (Index("ix_rubric_criteria_rubric", "rubric_id", "order_index"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    rubric_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubrics.id", ondelete="CASCADE"))
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RubricLevel(Base):
    """One rung on a criterion, with what it is worth.

    ``points`` is bounded on purpose: a typo that makes one criterion worth
    5000 silently swamps every other one, and the resulting mark looks
    arithmetically fine.
    """

    __tablename__ = "rubric_levels"
    __table_args__ = (
        Index("ix_rubric_levels_criterion", "criterion_id", "order_index"),
        CheckConstraint("points >= 0 AND points <= 1000", name="rubric_levels_points_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    criterion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubric_criteria.id", ondelete="CASCADE"))
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    label: Mapped[str] = mapped_column(Text)
    points: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssignmentRubric(Base):
    """Which rubric an assignment is marked by.

    One, not many: two rubrics on one assignment would mean two totals and no
    answer to which one the grade came from.
    """

    __tablename__ = "assignment_rubrics"
    __table_args__ = (Index("ix_assignment_rubrics_rubric", "rubric_id"),)

    assignment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), primary_key=True)
    rubric_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubrics.id", ondelete="CASCADE"))
    attached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    attached_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))


class RubricMark(Base):
    """The teacher's decision on one criterion for one piece of work.

    ``level_id`` is the decision; the points are read from the level. The
    unique constraint is the important part: one decision per criterion per
    submission, because a second row would mean the same criterion marked
    twice with no way to know which one counted.
    """

    __tablename__ = "rubric_marks"
    __table_args__ = (
        UniqueConstraint("submission_id", "criterion_id", name="uq_rubric_marks_submission_criterion"),
        Index("ix_rubric_marks_submission", "submission_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignment_submissions.id", ondelete="CASCADE"))
    criterion_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubric_criteria.id", ondelete="CASCADE"))
    #: RESTRICT rather than CASCADE: deleting a level a mark rests on would
    #: erase the mark, which is why levels are archived instead.
    level_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rubric_levels.id", ondelete="RESTRICT"))
    #: A note on this criterion specifically, separate from the feedback on the
    #: whole piece of work — «здесь не хватает текста» belongs to the criterion.
    comment: Mapped[str | None] = mapped_column(Text)
    marked_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
