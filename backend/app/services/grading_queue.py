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

The counted set must match, row for row, what the teacher finds when they open
the grading page (``GET /quizzes/{id}/pending-answers`` and the assignment
submission list). A badge that says three when the page shows two is worse than
no badge: it never reaches zero, and a queue that cannot be emptied is a queue
that gets ignored. Every filter below exists because that page has it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import func as sqlfunc

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.course import Chapter, Course, Module
from app.models.quiz import Quiz, QuizAnswer, QuizAttempt, QuizQuestion
from app.models.user import User
from app.services import quiz_service

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session


def unread_answer_filters() -> tuple:
    """What makes a quiz answer "waiting on a teacher", as one definition.

    Three surfaces ask this question — the grading page, the dashboard count,
    and the certificate explainer that tells a student their essay has not been
    read yet. Written out three times they drift, and the drift is invisible:
    the student is told one thing and the teacher's queue shows another, with
    neither number obviously wrong.
    """
    return (
        QuizAttempt.completed_at.isnot(None),
        QuizAnswer.graded_at.is_(None),
        QuizAnswer.text_answer.isnot(None),
        QuizQuestion.question_type.in_(quiz_service.MANUAL_GRADED_QUESTION_TYPES),
    )


def pending_by_course(db: Session, teacher_id: UUID) -> dict[str, int]:
    """``{course_id: count}`` of work awaiting this teacher, courses they own.

    Two queries for every course they teach, not two per course: a dashboard
    that costs a round trip per row is a dashboard that gets removed the first
    time somebody teaches twenty courses.
    """
    counts: dict[str, int] = {}

    # Open quiz answers: an essay or short answer submitted and unread. The
    # attempt must be finished — a quiz still being taken is not waiting on
    # anybody. The filters mirror the pending-answers page exactly.
    #
    # The question-type filter has no test that fails without it, and that is
    # deliberate: a CHECK constraint limits the column to the four known types,
    # so the row it would exclude cannot exist today. It is here as parity with
    # the page, for the day a fifth type is added — and
    # ``test_every_question_type_is_either_auto_marked_or_hand_marked`` is what
    # actually fires on that day.
    quiz_rows = (
        db.query(Module.course_id, sqlfunc.count(QuizAnswer.id))
        .select_from(QuizAnswer)
        .join(QuizQuestion, QuizQuestion.id == QuizAnswer.question_id)
        .join(QuizAttempt, QuizAttempt.id == QuizAnswer.attempt_id)
        .join(User, User.id == QuizAttempt.user_id)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .join(Chapter, Chapter.id == Quiz.chapter_id)
        .join(Module, Module.id == Chapter.module_id)
        .join(Course, Course.id == Module.course_id)
        .filter(
            Course.created_by == teacher_id,
            Course.deleted_at.is_(None),
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
            *unread_answer_filters(),
            # Deactivated students drop out of the grading queue (#786), so
            # they must drop out of the count of it too.
            User.deactivated_at.is_(None),
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
        .join(User, User.id == AssignmentSubmission.student_id)
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
            User.deactivated_at.is_(None),
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


# ---------------------------------------------------------------------------
# The queue itself, not the count of it
# ---------------------------------------------------------------------------
#
# Grouped by item rather than by student, because that is how the marking
# actually goes: thirty answers to the same prompt in a row, the standard
# loaded once. Read across a whole paper instead and the standard drifts
# between question one and question four, which is the thing a rubric exists to
# prevent and the thing a queue can prevent for free.
#
# The teacher's own phrase for this is «что мне сегодня проверить», and the
# answer has to fit on a phone screen.


def waiting_groups(db: Session, teacher_id: UUID) -> list[dict[str, Any]]:
    """Every piece of work waiting on this teacher, gathered by the item it answers.

    Two queries, one per kind. A group per course *and* item, because the same
    prompt reused in two courses is two conversations with two cohorts.
    """
    groups: list[dict[str, Any]] = []

    quiz_rows = (
        db.query(
            Module.course_id,
            QuizQuestion.id.label("item_id"),
            Chapter.id.label("chapter_id"),
            Chapter.title.label("chapter_title"),
            sqlfunc.count(QuizAnswer.id).label("waiting"),
            sqlfunc.min(QuizAttempt.completed_at).label("oldest"),
        )
        .select_from(QuizAnswer)
        .join(QuizQuestion, QuizQuestion.id == QuizAnswer.question_id)
        .join(QuizAttempt, QuizAttempt.id == QuizAnswer.attempt_id)
        .join(User, User.id == QuizAttempt.user_id)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .join(Chapter, Chapter.id == Quiz.chapter_id)
        .join(Module, Module.id == Chapter.module_id)
        .join(Course, Course.id == Module.course_id)
        .filter(
            Course.created_by == teacher_id,
            Course.deleted_at.is_(None),
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
            *unread_answer_filters(),
            User.deactivated_at.is_(None),
        )
        .group_by(Module.course_id, QuizQuestion.id, Chapter.id, Chapter.title)
        .all()
    )
    for row in quiz_rows:
        groups.append(
            {
                "kind": "quiz_answer",
                "item_id": str(row.item_id),
                "course_id": row.course_id,
                "chapter_id": row.chapter_id,
                "title": row.chapter_title,
                "waiting": int(row.waiting or 0),
                "oldest": row.oldest,
            }
        )

    assignment_rows = (
        db.query(
            Module.course_id,
            Assignment.id.label("item_id"),
            Chapter.id.label("chapter_id"),
            Chapter.title.label("chapter_title"),
            sqlfunc.count(AssignmentSubmission.id).label("waiting"),
            sqlfunc.min(AssignmentSubmission.submitted_at).label("oldest"),
        )
        .select_from(AssignmentSubmission)
        .join(Assignment, Assignment.id == AssignmentSubmission.assignment_id)
        .join(User, User.id == AssignmentSubmission.student_id)
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
            User.deactivated_at.is_(None),
        )
        .group_by(Module.course_id, Assignment.id, Chapter.id, Chapter.title)
        .all()
    )
    for row in assignment_rows:
        groups.append(
            {
                "kind": "assignment",
                "item_id": str(row.item_id),
                "course_id": row.course_id,
                "chapter_id": row.chapter_id,
                "title": row.chapter_title,
                "waiting": int(row.waiting or 0),
                "oldest": row.oldest,
            }
        )

    # Oldest first. A queue sorted by size buries the essay that has been
    # waiting three weeks under the assignment twelve people just handed in,
    # and the three-week-old one is the one somebody is upset about.
    return sorted(groups, key=lambda g: (g["oldest"] is None, g["oldest"]))


def assignment_work(db: Session, teacher_id: UUID, assignment_id: UUID) -> list[dict[str, Any]]:
    """The submissions waiting on one assignment, oldest first.

    Ownership is enforced by the caller; the teacher filter here is defence in
    depth rather than the only lock — a queue route that leaks is a route that
    leaks somebody's essay.
    """
    rows = (
        db.query(AssignmentSubmission, User.full_name, User.email)
        .join(Assignment, Assignment.id == AssignmentSubmission.assignment_id)
        .join(User, User.id == AssignmentSubmission.student_id)
        .join(Chapter, Chapter.id == Assignment.chapter_id)
        .join(Module, Module.id == Chapter.module_id)
        .join(Course, Course.id == Module.course_id)
        .filter(
            Assignment.id == assignment_id,
            Course.created_by == teacher_id,
            Course.deleted_at.is_(None),
            AssignmentSubmission.status == "submitted",
            AssignmentSubmission.grade.is_(None),
            User.deactivated_at.is_(None),
        )
        .order_by(AssignmentSubmission.submitted_at.asc(), AssignmentSubmission.id.asc())
        .all()
    )
    return [
        {
            "submission_id": str(submission.id),
            "student_id": str(submission.student_id),
            "student_name": full_name or email,
            "submitted_at": submission.submitted_at,
            "content": submission.content,
            "file_url": submission.file_url,
        }
        for submission, full_name, email in rows
    ]
