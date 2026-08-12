"""A student's own standing in one course (D10).

Everything here already existed — the weighted pair, the per-item results, the
excused list — and all of it was behind ``require_teacher``. A student could
see a progress bar, individual quiz scores, and, if a teacher had hand-set one,
a bare letter on their dashboard. They could not see their course grade.

That is the wrong way round for the thing this phase is building toward: the
certificate pass-gate goes live at the end of Phase 2, and the design's first
rule is that enforcement never ships before the visibility that explains it. A
student refused a certificate must already know why, and have known for weeks.

The list is built from the course's **items**, not its chapters. The first
version of this file walked the result arrays and filled the gaps by chapter,
which quietly dropped every untouched sibling: a chapter holding two quizzes,
one of them answered perfectly, showed a student 50% overall and a single piece
of work at 100%, with nothing on screen accounting for the difference. Nothing
enforces one gradable item per chapter, and the grade has never assumed it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import case
from sqlalchemy import func as sqlfunc

from app.models.quiz import QuizAnswer, QuizAttempt
from app.services.certificate_readiness import certificate_blockers
from app.services.gradable_items import course_items
from app.services.grade_calculator import calculate_student_grade_for_course
from app.services.grade_exemption_service import excused_item_ids
from app.services.grade_override import resolve_official_row
from app.services.zachet import latest_submissions, zachet_result

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from app.models.course import Course
    from app.models.enrollment import Enrollment

#: States where no honest number exists, so the student is told the reason
#: instead of being shown a zero. Same vocabulary as every teacher surface.
_NO_NUMBER_STATES = {"completion_pass", "not_graded_yet", "zero_weighted", "not_assessed"}

#: Its rule is completion-native (D2) and not implemented yet, so the weighted
#: percentage is not this course's result and must not be presented as one.
_COMPLETION_NATIVE_SCHEMES = {"pass_fail"}


def _quiz_marks(db: Session, student_id: UUID, quiz_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    """Best completed attempt per quiz, and whether it is still unread."""
    if not quiz_ids:
        return {}
    # An essay's open answers carry `graded_at IS NULL` until a teacher reads
    # them, and until then the attempt's score is a running total rather than a
    # result. Showing that to the person waiting on it is how a student
    # concludes they failed work nobody has opened.
    pending = db.query(QuizAnswer.attempt_id).filter(QuizAnswer.graded_at.is_(None)).distinct().subquery()
    rows = (
        db.query(
            QuizAttempt.quiz_id,
            sqlfunc.max(QuizAttempt.score * 100.0 / sqlfunc.nullif(QuizAttempt.max_score, 0)).label("best"),
            sqlfunc.max(case((pending.c.attempt_id.isnot(None), 1), else_=0)).label("awaiting"),
        )
        .outerjoin(pending, pending.c.attempt_id == QuizAttempt.id)
        .filter(
            QuizAttempt.quiz_id.in_(quiz_ids),
            QuizAttempt.user_id == student_id,
            QuizAttempt.completed_at.isnot(None),
        )
        .group_by(QuizAttempt.quiz_id)
        .all()
    )
    return {r.quiz_id: {"score": r.best, "awaiting": bool(r.awaiting)} for r in rows}


def _assignment_marks(db: Session, student_id: UUID, assignment_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    """The submission that decides each assignment, from the same helper the
    зачёт rule uses — so the card and the verdict cannot disagree about the
    same essay, which they did when each picked its own "latest"."""
    return latest_submissions(db, student_id=student_id, assignment_ids=assignment_ids)


def _status_and_score(
    *, excused: bool, has_work: bool, awaiting: bool, score: float | None, returned: bool = False
) -> tuple[str, float | None]:
    if excused:
        # Checked first: an exemption means the work is not owed at all, so a
        # returned-then-excused essay must not keep showing as owed. It did,
        # putting a red «возвращено на доработку» row under a «Зачёт».
        # «Освобождено», never «не сдано» — the work was not missed, it was set
        # aside by a teacher who wrote down why.
        return "excused", None
    if returned:
        # Marked, and handed back. The grade on it is real but the work is not
        # finished — returning work is the teacher's "not yet", and the ball is
        # with the student.
        return "returned", None
    if not has_work:
        return "not_submitted", None
    if awaiting or score is None:
        return "pending_review", None
    return "graded", round(score, 1)


def build_my_course_grade(db: Session, course: Course, enrollment: Enrollment, student_id: UUID) -> dict[str, Any]:
    """The student's own view of one course. Never anyone else's."""
    breakdown = calculate_student_grade_for_course(db, course, student_id)
    excused_quizzes, excused_assignments = excused_item_ids(db, student_id=student_id, course_id=course.id)

    quizzes, assignments = course_items(db, course.id)
    quiz_marks = _quiz_marks(db, student_id, [q.id for q in quizzes])
    assignment_marks = _assignment_marks(db, student_id, [a.id for a in assignments])

    items: list[dict[str, Any]] = []
    for quiz in quizzes:
        mark = quiz_marks.get(quiz.id)
        status, score = _status_and_score(
            excused=quiz.id in excused_quizzes,
            has_work=mark is not None,
            awaiting=bool(mark and mark["awaiting"]),
            score=float(mark["score"]) if mark and mark["score"] is not None else None,
        )
        items.append(
            {
                "item_id": str(quiz.id),
                "chapter_id": quiz.chapter_id,
                "title": quiz.chapter_title,
                "kind": "quiz",
                "status": status,
                "score": score,
                # A quiz has no single note: its comments hang off individual
                # answers. Surfacing "the" comment for one would mean picking
                # one and dropping the rest, so the attempt page stays the
                # place for those.
                "feedback": None,
            }
        )
    for assignment in assignments:
        mark = assignment_marks.get(assignment.id)
        raw_grade = mark["grade"] if mark is not None else None
        pct = None
        if raw_grade is not None and assignment.max_score:
            # Clamped for the same reason the calculator clamps: a pre-cap
            # historical row above `max_score` would print over 100%.
            pct = min(100.0, float(raw_grade) / assignment.max_score * 100.0)
        status, score = _status_and_score(
            excused=assignment.id in excused_assignments,
            has_work=mark is not None,
            awaiting=mark is not None and raw_grade is None,
            score=pct,
            returned=mark is not None and mark.get("status") == "returned",
        )
        items.append(
            {
                "item_id": str(assignment.id),
                "chapter_id": assignment.chapter_id,
                "title": assignment.chapter_title,
                "kind": "assignment",
                "status": status,
                "score": score,
                # Not shown for work the student is not owed and has not done:
                # a note on an excused item is about a decision they did not
                # make, and there is nothing written on work never handed in.
                "feedback": (mark or {}).get("feedback") if status in {"graded", "returned"} else None,
            }
        )

    scheme = course.grading_scheme
    withheld = scheme in _COMPLETION_NATIVE_SCHEMES
    no_number = breakdown.result_state in _NO_NUMBER_STATES or withheld

    # A pass/fail course has a real verdict, and the student is the person who
    # most needs it — «зачёт» is predictable without arithmetic, which is the
    # whole point of the scheme (D2). Withholding the percentage while saying
    # nothing in its place would leave them worse informed than before.
    zachet = None
    if withheld:
        zachet, _owed = zachet_result(
            db,
            student_id=student_id,
            course_id=course.id,
            progress=enrollment.progress,
            all_items_excused=breakdown.result_state == "not_assessed",
        )

    official_row = resolve_official_row(db, student_id=student_id, course_id=course.id)
    official_grade = None
    if official_row is not None:
        if official_row.override_code is not None:
            official_grade = official_row.override_code
        elif official_row.override_score is not None:
            official_grade = f"{official_row.override_score:.2f}"

    return {
        "course_id": course.id,
        "grading_scheme": scheme,
        "pass_threshold": course.pass_threshold,
        "progress": enrollment.progress,
        "current_score": None if no_number else breakdown.current_score,
        "current_symbol": (breakdown.current_letter_grade or None) if not no_number else None,
        "final_score": None if no_number else breakdown.final_score,
        "final_symbol": (breakdown.letter_grade or None) if not no_number else None,
        "scores_differ": False if no_number else breakdown.scores_differ,
        "result_state": breakdown.result_state,
        "scores_withheld": withheld,
        "zachet": zachet,
        "official_grade": official_grade,
        # The note written TO the student. `reason` — the note about them,
        # written for the institution — is never read here (D7).
        "comment": official_row.comment if official_row is not None else None,
        "certificate_blockers": [
            b.as_dict()
            for b in certificate_blockers(db, course, enrollment, student_id, breakdown=breakdown, zachet=zachet)
        ],
        "items": sorted(items, key=lambda i: (i["kind"], i["title"], i["item_id"])),
    }


def latest_enrollment(db: Session, student_id: UUID, course_id: str) -> Enrollment | None:
    """The enrolment this student's grade is resolved against.

    A retaking student has two: last term's and this one's. ``resolve_official_row``
    deliberately picks the most recent, so the progress shown beside that grade
    has to come from the same row — otherwise the card pairs this term's mark
    with last term's progress bar, and which one wins is row order.
    """
    from app.models.enrollment import Enrollment as _Enrollment

    return (
        db.query(_Enrollment)
        .filter(_Enrollment.user_id == student_id, _Enrollment.course_id == course_id)
        .order_by(_Enrollment.enrolled_at.desc().nullslast(), _Enrollment.id.desc())
        .first()
    )
