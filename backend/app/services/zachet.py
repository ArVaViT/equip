"""«Зачёт» — the completion-native pass rule (D2).

The заочная tradition means something specific by зачёт: **все обязательные
работы зачтены**. Not "average above a line". A minister taking a course by
correspondence can predict the outcome without arithmetic — did the work,
passed the tests, work accepted — and that predictability is the point of the
scheme, not a simplification of it.

So there is no percentage here, and deliberately no import of the calculator.
The draft this replaces defined pass as *weighted average ≥ threshold* while
the interface "de-emphasised percentages", which meant a student could complete
every chapter, pass every quiz, have every essay accepted, and still be handed
незачёт by a number the product had decided not to show them. The teacher would
then be holding two incompatible ideas of "passing" and no way to explain
either.

Три условия, все обязательны:

1. **progress == 100** — every gradable chapter done.
2. **Every quiz passed**, at its own ``passing_score``. The design assumes
   condition 1 carries this, and it does not: ``PUT /progress/chapter/…/complete``
   marks a chapter done without looking at the quiz inside it, so a student who
   failed every test could reach progress 100 on a teacher's tick and be handed
   зачёт by arithmetic nobody performed. A teacher who wants to pass such a
   student still can — by setting the grade themselves, which is recorded,
   visible and attributable (D7). Silence is the thing being removed, not the
   teacher's authority.
3. **Every assignment accepted** — it has a graded submission and is not
   sitting in ``returned``. Grading without returning *is* acceptance;
   «вернуть на доработку» is the teacher's "not yet", and a course cannot be
   зачтён while one is outstanding.
4. **Not «не аттестован»** — a student excused from everything was never
   assessed, and зачёт is an assessment.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.course import Chapter, Module
from app.models.grade_exemption import GradeExemption
from app.models.quiz import Quiz, QuizAttempt

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

#: The three outcomes. "Not attested" is not a failure — it says nobody
#: assessed this person, which is a different thing to say and needs a human.
ZACHET = "zachet"
NEZACHET = "nezachet"
NOT_ATTESTED = "not_attested"


def assignments_in_course(db: Session, course_id: str) -> list:
    return (
        db.query(Assignment.id)
        .join(Chapter, Chapter.id == Assignment.chapter_id)
        .join(Module, Module.id == Chapter.module_id)
        .filter(
            Module.course_id == course_id,
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
        )
        .all()
    )


def latest_submissions(db: Session, *, student_id: UUID, assignment_ids: list) -> dict:
    """The submission that decides each assignment's state, one per assignment.

    "Latest" needs a tie-break, not just ``MAX(submitted_at)``: the column
    defaults to ``NOW()``, which on Postgres is the *transaction* timestamp and
    is therefore identical for rows written together. Untied, a graded row and
    a returned row for the same assignment both came back, and whichever the
    reader happened to fold in decided the verdict — a returned essay could
    quietly count as accepted.

    Ordered so the newest wins, ties broken on ``graded_at`` and then ``id``,
    which is arbitrary but *stable*: the same answer every time it is asked.
    Shared by the зачёт rule and the student's item list so the two cannot
    disagree about the same essay.
    """
    if not assignment_ids:
        return {}
    rows = (
        db.query(AssignmentSubmission)
        .filter(
            AssignmentSubmission.assignment_id.in_(assignment_ids),
            AssignmentSubmission.student_id == student_id,
        )
        .order_by(
            AssignmentSubmission.submitted_at.asc().nullsfirst(),
            AssignmentSubmission.graded_at.asc().nullsfirst(),
            AssignmentSubmission.id.asc(),
        )
        .all()
    )
    # Ascending, so the last write per assignment is the winner.
    return {r.assignment_id: {"status": r.status, "grade": r.grade, "feedback": r.feedback} for r in rows}


def unaccepted_assignments(
    db: Session, *, student_id: UUID, course_id: str, course_assignment_ids: list | None = None
) -> list[str]:
    """Assignment ids this student still owes work on.

    "Owes" covers three shapes, and they are one list on purpose — a student
    asking "what is left" does not care which of the three it is:

    * never submitted;
    * submitted and not yet marked;
    * marked and **returned** for revision.

    Excused assignments are not owed at all (D6) and drop out entirely.
    """
    # The course's assignments are the same for everybody, so a caller looping
    # over a cohort passes them in once instead of asking per student.
    all_ids = (
        course_assignment_ids
        if course_assignment_ids is not None
        else [r.id for r in assignments_in_course(db, course_id)]
    )
    if not all_ids:
        return []

    excused = {
        r.item_id
        for r in db.query(GradeExemption.item_id)
        .filter(
            GradeExemption.student_id == student_id,
            GradeExemption.course_id == course_id,
            GradeExemption.item_type == "assignment",
        )
        .all()
    }

    latest = latest_submissions(db, student_id=student_id, assignment_ids=all_ids)
    accepted = {aid for aid, sub in latest.items() if sub["status"] == "graded" and sub["grade"] is not None}

    return [str(a) for a in all_ids if a not in excused and a not in accepted]


def course_quiz_rows(db: Session, course_id: str) -> list:
    """Every live quiz in the course, with its pass line. Course-invariant, so a
    caller looping over a cohort fetches it once."""
    return (
        db.query(Quiz.id, Quiz.passing_score)
        .join(Chapter, Chapter.id == Quiz.chapter_id)
        .join(Module, Module.id == Chapter.module_id)
        .filter(
            Module.course_id == course_id,
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
        )
        .all()
    )


def unpassed_quizzes(db: Session, *, student_id: UUID, course_id: str, course_quizzes: list | None = None) -> list[str]:
    """Quizzes this student has not passed at their own ``passing_score``.

    Excused quizzes are not owed (D6). A quiz counts as passed on any completed
    attempt that cleared its line — the platform keeps the best attempt, and a
    later worse one does not take a pass away.
    """
    quizzes = course_quizzes if course_quizzes is not None else course_quiz_rows(db, course_id)
    if not quizzes:
        return []

    excused = {
        r.item_id
        for r in db.query(GradeExemption.item_id)
        .filter(
            GradeExemption.student_id == student_id,
            GradeExemption.course_id == course_id,
            GradeExemption.item_type == "quiz",
        )
        .all()
    }
    passed = {
        r.quiz_id
        for r in db.query(QuizAttempt.quiz_id)
        .filter(
            QuizAttempt.quiz_id.in_([q.id for q in quizzes]),
            QuizAttempt.user_id == student_id,
            QuizAttempt.completed_at.isnot(None),
            QuizAttempt.passed.is_(True),
        )
        .distinct()
        .all()
    }
    return [str(q.id) for q in quizzes if q.id not in excused and q.id not in passed]


def zachet_result(
    db: Session,
    *,
    student_id: UUID,
    course_id: str,
    progress: int,
    all_items_excused: bool,
    course_assignment_ids: list | None = None,
    course_quizzes: list | None = None,
) -> tuple[str, list[str]]:
    """``(result, unaccepted_assignment_ids)`` for a pass/fail course.

    ``progress`` comes from the enrolment rather than being recomputed here:
    it is the same number the certificate gate and every progress bar already
    use, and зачёт disagreeing with the progress bar on the same screen is
    exactly the confusion this rule exists to remove.
    """
    if all_items_excused:
        return NOT_ATTESTED, []

    outstanding = unaccepted_assignments(
        db, student_id=student_id, course_id=course_id, course_assignment_ids=course_assignment_ids
    )
    failed_quizzes = unpassed_quizzes(db, student_id=student_id, course_id=course_id, course_quizzes=course_quizzes)
    if progress >= 100 and not outstanding and not failed_quizzes:
        return ZACHET, []
    return NEZACHET, outstanding
