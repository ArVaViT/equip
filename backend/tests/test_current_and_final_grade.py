"""«Текущая» and «итоговая» — the same pair, the same names, both roles (D10).

Two honest answers to two different questions:

* «текущая» — how am I doing on the work that has been marked;
* «итоговая» — what is this if I hand in nothing more.

In week two those are 100% and 25%, and both are true. The design's rule is
that nobody gets one of them and not the other: giving the student «текущая»
and the teacher «итоговая» produces an 85%-vs-40% conversation where each side
is certain their own number is the grade, and neither can explain the other's.

Note what this makes of the progress board's old private arithmetic: dividing
by the work attempted was «текущая» all along. It was not the wrong formula —
it was the right formula for the other question, presented as the official
grade.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizAttempt
from app.services.grade_calculator import (
    calculate_all_student_grades,
    calculate_student_grade_for_course,
)
from app.services.grade_exemption_service import apply_exemption

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID


def _course(db: Session, teacher, course_id: str, *, quizzes=0, assignments=0, qw=100, aw=0):
    course = Course(id=course_id, status="published", created_by=teacher.id, quiz_weight=qw, assignment_weight=aw)
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.flush()
    made_q, made_a = [], []
    for i in range(quizzes):
        ch = Chapter(id=f"{course_id}-q{i}", module_id=module.id, order_index=i, chapter_type="quiz", title="Q")
        db.add(ch)
        db.flush()
        quiz = Quiz(id=uuid.uuid4(), chapter_id=ch.id)
        db.add(quiz)
        made_q.append(quiz)
    for i in range(assignments):
        ch = Chapter(
            id=f"{course_id}-a{i}",
            module_id=module.id,
            order_index=quizzes + i,
            chapter_type="assignment",
            title="A",
        )
        db.add(ch)
        db.flush()
        assignment = Assignment(id=uuid.uuid4(), chapter_id=ch.id, max_score=100)
        db.add(assignment)
        made_a.append(assignment)
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=0))
    db.commit()
    return course, made_q, made_a


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


def test_both_numbers_are_reported_and_both_are_true(db: Session, teacher, student) -> None:
    """One quiz of four, answered perfectly: 100% current, 25% final."""
    course, quizzes, _ = _course(db, teacher, "c-pair", quizzes=4)
    _attempt(db, quizzes[0], 100)
    db.commit()

    grade = calculate_student_grade_for_course(db, course, STUDENT_ID)

    assert grade.current_score == 100.0
    assert grade.final_score == 25.0
    assert grade.scores_differ is True


def test_they_collapse_to_one_number_when_everything_is_in(db: Session, teacher, student) -> None:
    """Nothing to explain once there is nothing outstanding — and the surfaces
    read `scores_differ` to decide whether to say anything at all."""
    course, quizzes, _ = _course(db, teacher, "c-pair-done", quizzes=2)
    _attempt(db, quizzes[0], 90)
    _attempt(db, quizzes[1], 70)
    db.commit()

    grade = calculate_student_grade_for_course(db, course, STUDENT_ID)

    assert grade.current_score == grade.final_score == 80.0
    assert grade.scores_differ is False


def test_the_pair_carries_its_own_symbols(db: Session, teacher, student) -> None:
    """A school reading in letters needs both sides in letters, or the sentence
    "текущая B, итоговая F" cannot be said at all."""
    course, quizzes, _ = _course(db, teacher, "c-pair-symbols", quizzes=4)
    _attempt(db, quizzes[0], 85)
    db.commit()

    grade = calculate_student_grade_for_course(db, course, STUDENT_ID)

    assert (grade.current_score, grade.current_letter_grade) == (85.0, "B")
    assert (grade.final_score, grade.letter_grade) == (21.25, "F")


def test_excused_work_leaves_both_numbers(db: Session, teacher, student) -> None:
    """An exemption is not "not handed in" — it is not owed at all, so it drops
    out of the harsher number too."""
    course, quizzes, _ = _course(db, teacher, "c-pair-excused", quizzes=2)
    _attempt(db, quizzes[0], 100)
    db.commit()
    apply_exemption(
        db,
        student_id=STUDENT_ID,
        course_id=course.id,
        item_type="quiz",
        item_id=quizzes[1].id,
        teacher_id=teacher.id,
    )
    db.commit()

    grade = calculate_student_grade_for_course(db, course, STUDENT_ID)

    assert grade.current_score == grade.final_score == 100.0
    assert grade.scores_differ is False


def test_both_categories_use_the_configured_weights(db: Session, teacher, student) -> None:
    """«Текущая» differs only in the denominator inside each category, never in
    how the categories combine — otherwise the gap cannot be explained in one
    sentence, which is the whole point of showing the pair."""
    course, quizzes, assignments = _course(db, teacher, "c-pair-weights", quizzes=2, assignments=2, qw=70, aw=30)
    _attempt(db, quizzes[0], 80)
    db.add(
        AssignmentSubmission(
            id=uuid.uuid4(),
            assignment_id=assignments[0].id,
            student_id=STUDENT_ID,
            status="graded",
            grade=60,
            graded_by=teacher.id,
        )
    )
    db.commit()

    grade = calculate_student_grade_for_course(db, course, STUDENT_ID)

    # current: 80 * 0.7 + 60 * 0.3 = 74
    assert grade.current_score == 74.0
    # final: (80/2) * 0.7 + (60/2) * 0.3 = 28 + 9 = 37
    assert grade.final_score == 37.0


def test_the_class_list_reports_the_same_pair(db: Session, teacher, student) -> None:
    course, quizzes, _ = _course(db, teacher, "c-pair-batch", quizzes=4)
    _attempt(db, quizzes[0], 100)
    db.commit()

    (row,) = calculate_all_student_grades(db, course)
    solo = calculate_student_grade_for_course(db, course, STUDENT_ID)

    assert row["breakdown"].current_score == solo.current_score == 100.0
    assert row["breakdown"].final_score == solo.final_score == 25.0


def test_a_student_with_nothing_marked_has_no_current_score_either(db: Session, teacher, student) -> None:
    """Zero marked work makes «текущая» an average over nothing. It reports 0
    with `student_has_*_marks` false, so the surfaces print a dash — the same
    rule that already governs the category columns."""
    course, _quizzes, _ = _course(db, teacher, "c-pair-nothing", quizzes=2)

    grade = calculate_student_grade_for_course(db, course, STUDENT_ID)

    assert grade.current_score == 0.0
    assert grade.student_has_quiz_marks is False
    assert grade.result_state == "not_graded_yet"
