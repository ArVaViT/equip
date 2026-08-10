"""One number, one meaning, every teacher surface (D14).

The gradebook and the progress board used to compute a student's grade in two
different places, by two different formulas, and they disagreed in four
independent ways at once: the board divided by the work *attempted* rather than
the work *set*, took an unweighted mean of the two categories, and never
consulted overrides, exemptions or the institution's bands.

The tests below are written as invariants between the two surfaces rather than
as expected constants, because a constant only catches the case someone thought
of. If a fifth grade-affecting feature lands and reaches only one screen, these
fail.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizAttempt
from app.models.student_grade import StudentGrade
from app.services.grade_calculator import calculate_student_grade_for_course
from app.services.grade_exemption_service import apply_exemption
from app.services.student_progress_service import build_course_student_progress

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID


def _course(db: Session, teacher, course_id: str, *, quizzes: int, assignments: int, qw: int, aw: int):
    """A course with N quizzes and M assignments, one per chapter."""
    course = Course(id=course_id, status="published", created_by=teacher.id, quiz_weight=qw, assignment_weight=aw)
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.flush()

    made_quizzes, made_assignments = [], []
    for i in range(quizzes):
        ch = Chapter(id=f"{course_id}-q{i}", module_id=module.id, order_index=i, chapter_type="quiz", title=f"Q{i}")
        db.add(ch)
        db.flush()
        quiz = Quiz(id=uuid.uuid4(), chapter_id=ch.id)
        db.add(quiz)
        made_quizzes.append(quiz)
    for i in range(assignments):
        ch = Chapter(
            id=f"{course_id}-a{i}",
            module_id=module.id,
            order_index=quizzes + i,
            chapter_type="assignment",
            title=f"A{i}",
        )
        db.add(ch)
        db.flush()
        assignment = Assignment(id=uuid.uuid4(), chapter_id=ch.id, max_score=100)
        db.add(assignment)
        made_assignments.append(assignment)

    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=0))
    db.commit()
    return course, made_quizzes, made_assignments


def _attempt(db: Session, quiz, score: int) -> None:
    db.add(
        QuizAttempt(
            id=uuid.uuid4(),
            quiz_id=quiz.id,
            user_id=STUDENT_ID,
            score=score,
            max_score=100,
            passed=score >= 70,
            completed_at=datetime.now(UTC),
        )
    )


def _board_row(db: Session, course) -> dict:
    payload = build_course_student_progress(db, course, course.id)
    return next(s for s in payload["students"] if s["id"] == str(STUDENT_ID))


def test_the_board_counts_the_work_set_not_the_work_attempted(db: Session, teacher, student) -> None:
    """One quiz of four, answered perfectly, is 25% — not 100%.

    This was the loudest disagreement: the board divided by the results it
    happened to have, so a student who had done a quarter of the course read as
    top of the class right up until they ran out of time.
    """
    course, quizzes, _ = _course(db, teacher, "c-agree-denom", quizzes=4, assignments=0, qw=100, aw=0)
    _attempt(db, quizzes[0], 100)
    db.commit()

    row = _board_row(db, course)
    official = calculate_student_grade_for_course(db, course, STUDENT_ID)

    assert row["overall_grade"] == round(official.final_score)
    assert row["overall_grade"] == 25


def test_the_board_applies_the_weights_the_teacher_configured(db: Session, teacher, student) -> None:
    """An unweighted mean of the two categories is not the course's grade.

    70/30 with 100% on quizzes and 0% on assignments is 70, not 50.
    """
    course, quizzes, assignments = _course(db, teacher, "c-agree-weights", quizzes=1, assignments=1, qw=70, aw=30)
    _attempt(db, quizzes[0], 100)
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=assignments[0].id,
            student_id=STUDENT_ID,
            status="graded",
            grade=0,
            graded_by=teacher.id,
        )
    )
    db.commit()

    row = _board_row(db, course)
    official = calculate_student_grade_for_course(db, course, STUDENT_ID)

    assert row["overall_grade"] == round(official.final_score)
    assert row["overall_grade"] == 70


def test_an_exemption_moves_both_surfaces(db: Session, teacher, student) -> None:
    course, quizzes, _ = _course(db, teacher, "c-agree-excused", quizzes=2, assignments=0, qw=100, aw=0)
    _attempt(db, quizzes[0], 100)
    _attempt(db, quizzes[1], 20)
    db.commit()

    before = _board_row(db, course)["overall_grade"]
    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="quiz",
        item_id=quizzes[1].id,
        teacher_id=teacher.id,
    )
    db.commit()

    row = _board_row(db, course)
    official = calculate_student_grade_for_course(db, course, STUDENT_ID)

    assert before == 60
    assert row["overall_grade"] == round(official.final_score) == 100


def test_a_hand_set_grade_reaches_the_board(db: Session, teacher, student) -> None:
    """The override IS the official grade (D7), so it cannot stop at one screen.

    A teacher who marks a student up in the gradebook and then sees the old
    number on the progress board has no way to tell which one the certificate
    will use.
    """
    course, quizzes, _ = _course(db, teacher, "c-agree-override", quizzes=1, assignments=0, qw=100, aw=0)
    _attempt(db, quizzes[0], 30)
    db.add(StudentGrade(course_id=course.id, student_id=STUDENT_ID, override_code="A"))
    db.commit()

    row = _board_row(db, course)

    assert row["manual_grade"] == "A"
    assert row["overall_grade"] == 30, "the computed number stays visible beside it, not replaced"


def test_the_board_says_nothing_rather_than_zero_when_nothing_is_marked(db: Session, teacher, student) -> None:
    """0% and "nobody has read it yet" are arithmetically identical and mean
    opposite things. Only one of them belongs on a screen as a number."""
    course, _quizzes, _assignments = _course(db, teacher, "c-agree-unmarked", quizzes=1, assignments=1, qw=50, aw=50)

    row = _board_row(db, course)

    assert row["overall_grade"] is None
    assert row["quiz_avg"] is None
    assert row["assignment_avg"] is None
    assert row["result_state"] == "not_graded_yet"


def test_a_category_with_nothing_marked_shows_no_average(db: Session, teacher, student) -> None:
    course, quizzes, _assignments = _course(db, teacher, "c-agree-half", quizzes=1, assignments=1, qw=50, aw=50)
    _attempt(db, quizzes[0], 90)
    db.commit()

    row = _board_row(db, course)

    assert row["quiz_avg"] == 90
    assert row["assignment_avg"] is None, "nobody has marked an assignment — that is not a zero"


def test_the_board_carries_the_courses_own_symbol(db: Session, teacher, student) -> None:
    """A school that moves its bands moves them everywhere, or nowhere."""
    course, quizzes, _ = _course(db, teacher, "c-agree-symbol", quizzes=1, assignments=0, qw=100, aw=0)
    _attempt(db, quizzes[0], 95)
    db.commit()

    row = _board_row(db, course)
    official = calculate_student_grade_for_course(db, course, STUDENT_ID)

    assert row["letter_grade"] == official.letter_grade == "A"


def test_an_unmarked_student_shows_no_average_even_when_a_classmate_is_marked(db: Session, teacher, student) -> None:
    """ "Nobody has read theirs" is per student, not per course.

    Whether the category counts at all is a fact about the course — it has to
    be, or two students in one class would be graded on different weights. But
    whether there is a number to show is a fact about the student, and reading
    the first as the second puts a 0 on the row of every unmarked person in a
    class where anyone has been marked.
    """
    from app.models.user import User

    other_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    db.add(User(id=other_id, email="other@example.com", full_name="Other", role="student"))
    course, quizzes, _ = _course(db, teacher, "c-agree-unmarked-peer", quizzes=1, assignments=0, qw=100, aw=0)
    db.add(Enrollment(id="enr-peer", user_id=other_id, course_id=course.id, progress=0))
    _attempt(db, quizzes[0], 100)
    db.commit()

    rows = {s["id"]: s for s in build_course_student_progress(db, course, course.id)["students"]}

    assert rows[str(STUDENT_ID)]["quiz_avg"] == 100
    assert rows[str(other_id)]["quiz_avg"] is None, "nobody has marked theirs — that is not a zero"
    assert rows[str(other_id)]["overall_grade"] == 0, (
        "their course grade is still 0: the work was set and they have not done it"
    )


def test_the_score_reaches_the_client_unrounded(db: Session, teacher, student) -> None:
    """Rounding twice gave the same student two different numbers.

    Python rounds .5 to even and JavaScript rounds it up, so 86.5 became 86 on
    one screen and 87 on another. Worse, a rounded 89.5 printed as "90%" beside
    the letter B — which the school's own band table calls A.
    """
    course, quizzes, _ = _course(db, teacher, "c-agree-rounding", quizzes=4, assignments=0, qw=100, aw=0)
    for quiz, score in zip(quizzes, (100, 100, 89, 69), strict=True):
        _attempt(db, quiz, score)
    db.commit()

    row = _board_row(db, course)
    official = calculate_student_grade_for_course(db, course, STUDENT_ID)

    assert row["overall_grade"] == official.final_score == 89.5
    assert row["letter_grade"] == "B", "and the letter is read from the same unrounded score"
