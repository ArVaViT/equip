"""What is waiting for a teacher to mark it.

An essay is submitted and then nothing happens until somebody opens the right
course, the right chapter and the right attempt. Until now the platform had no
place that said "seven pieces of work are waiting on you" — the teacher had to
already suspect it. For a school taking its first cohort, that is the gap where
student work quietly sits for a fortnight.

Two shapes of waiting, and they are counted together because the teacher's
question is "what do I owe", not "which table is it in":

* an open quiz answer nobody has read (``quiz_answers.graded_at IS NULL``);
* a submitted assignment with no mark on it.

Work the student owes — never handed in, or handed back for revision — is
deliberately **not** here. That is the student's move, and putting it in a
teacher's queue would make the number unactionable, which is how a queue stops
being read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import func as sqlfunc

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.course import Chapter, Course, Module
from app.models.quiz import Quiz, QuizAnswer, QuizAttempt

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session


def pending_by_course(db: Session, teacher_id: UUID) -> dict[str, int]:
    """``{course_id: count}`` of work awaiting this teacher, courses they own.

    Two queries for every course they teach, not two per course: a dashboard
    that costs a round trip per row is a dashboard that gets removed the first
    time somebody teaches twenty courses.
    """
    counts: dict[str, int] = {}

    # Open quiz answers: an essay or short answer submitted and unread. The
    # attempt must be finished — a quiz still being taken is not waiting on
    # anybody.
    quiz_rows = (
        db.query(Module.course_id, sqlfunc.count(QuizAnswer.id))
        .select_from(QuizAnswer)
        .join(QuizAttempt, QuizAttempt.id == QuizAnswer.attempt_id)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .join(Chapter, Chapter.id == Quiz.chapter_id)
        .join(Module, Module.id == Chapter.module_id)
        .join(Course, Course.id == Module.course_id)
        .filter(
            Course.created_by == teacher_id,
            Course.deleted_at.is_(None),
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
            QuizAttempt.completed_at.isnot(None),
            QuizAnswer.graded_at.is_(None),
        )
        .group_by(Module.course_id)
        .all()
    )
    for course_id, count in quiz_rows:
        counts[course_id] = counts.get(course_id, 0) + int(count or 0)

    # Submitted assignments with no mark. `returned` is excluded: it has been
    # read, and the ball is with the student.
    assignment_rows = (
        db.query(Module.course_id, sqlfunc.count(AssignmentSubmission.id))
        .select_from(AssignmentSubmission)
        .join(Assignment, Assignment.id == AssignmentSubmission.assignment_id)
        .join(Chapter, Chapter.id == Assignment.chapter_id)
        .join(Module, Module.id == Chapter.module_id)
        .join(Course, Course.id == Module.course_id)
        .filter(
            Course.created_by == teacher_id,
            Course.deleted_at.is_(None),
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
            AssignmentSubmission.status == "submitted",
            AssignmentSubmission.grade.is_(None),
        )
        .group_by(Module.course_id)
        .all()
    )
    for course_id, count in assignment_rows:
        counts[course_id] = counts.get(course_id, 0) + int(count or 0)

    return counts


def pending_summary(db: Session, teacher_id: UUID) -> dict[str, Any]:
    """The rollup a teacher's dashboard shows: a total and a per-course map."""
    by_course = pending_by_course(db, teacher_id)
    return {"total": sum(by_course.values()), "by_course": by_course}
