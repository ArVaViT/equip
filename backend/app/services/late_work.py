"""Was this handed in after the deadline? (2026-10-03)

Assignments carried a ``due_date`` that was set by the teacher, shown to the
student, used by the calendar and the at-risk report — and never consulted
when the work actually arrived. A submission a week after the deadline
reached the teacher looking exactly like one a week before it.

Late work is accepted, not refused: a Bible school's deadlines are pastoral,
and what a late essay costs is the teacher's decision. The platform's part is
to make sure the teacher, and the student, can see that it was late.

Derived, never stored. ``submitted_at`` against the deadline, both as UTC
instants, at read time: a teacher who extends the deadline forgives the
work by doing so, and one who pulls it earlier does not rewrite a column
nobody re-computes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func

from app.models.assignment import AssignmentSubmission
from app.models.course import Chapter, Module

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session


def _aware(moment: datetime) -> datetime:
    """SQLite (the tests) hands back naive datetimes; every stored instant is UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def is_late(handed_in_at: datetime | None, due_date: datetime | None) -> bool:
    """Strictly after the deadline. No deadline, or nothing handed in yet, is not late."""
    if handed_in_at is None or due_date is None:
        return False
    return _aware(handed_in_at) > _aware(due_date)


def module_due_date_for_chapter(db: Session, chapter_id: str) -> datetime | None:
    """The deadline a quiz in this chapter is read against: its module's.

    A quiz has no due date of its own; the module is the unit a teacher
    schedules, and ``modules.due_date`` is what the calendar and the course
    outline already show the student as «due». A chapter outside any module
    has no deadline and nothing in it is ever late.
    """
    row = (
        db.query(Module.due_date)
        .join(Chapter, Chapter.module_id == Module.id)
        .filter(Chapter.id == chapter_id, Module.deleted_at.is_(None))
        .first()
    )
    return row[0] if row else None


def first_handed_in(db: Session, assignment_id: uuid.UUID, student_ids: list[uuid.UUID]) -> dict[str, datetime]:
    """When each student first handed this assignment in, in one query.

    Late is a fact about the first hand-in. A resubmission after the teacher
    returned the work for revision is the teacher's request answered, not a
    deadline missed — counted per row, an essay handed in on time, returned,
    and revised the next week was badged late (2026-10-03).
    """
    if not student_ids:
        return {}
    rows = (
        db.query(AssignmentSubmission.student_id, func.min(AssignmentSubmission.submitted_at))
        .filter(AssignmentSubmission.assignment_id == assignment_id, AssignmentSubmission.student_id.in_(student_ids))
        .group_by(AssignmentSubmission.student_id)
        .all()
    )
    return {str(student_id): first for student_id, first in rows if first is not None}
