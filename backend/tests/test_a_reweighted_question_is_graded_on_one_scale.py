"""A question re-weighted after submission cannot push an attempt past 100% (2026-10-03).

A finished attempt keeps its submit-time maximum (an edit re-scores nothing
already graded), but a manual grade is capped by the question's current
points: an essay re-weighted 10 → 50 and marked 50 read 51/11 — 463% in the
course grade.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizAnswer, QuizAttempt, QuizQuestion
from app.services.grade_calculator import calculate_student_grade_for_course
from app.services.quiz_service import recompute_attempt_grade

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID


def _quiz(db: Session, teacher, course_id: str):
    course = Course(id=course_id, status="published", created_by=teacher.id, quiz_weight=100, assignment_weight=0)
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(id=f"{course_id}-ch", module_id=module.id, order_index=0, chapter_type="quiz", title="Q")
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id, passing_score=70)
    db.add(quiz)
    db.flush()
    mcq = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_type="multiple_choice", points=1, order_index=0)
    essay = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_type="essay", points=10, order_index=1)
    db.add_all([mcq, essay])
    attempt = QuizAttempt(
        id=uuid.uuid4(),
        quiz_id=quiz.id,
        user_id=STUDENT_ID,
        score=1,
        max_score=11,
        passed=False,
        completed_at=datetime.now(UTC),
    )
    db.add(attempt)
    db.flush()
    db.add(
        QuizAnswer(
            id=uuid.uuid4(), attempt_id=attempt.id, question_id=mcq.id, points_earned=1, graded_at=datetime.now(UTC)
        )
    )
    essay_answer = QuizAnswer(
        id=uuid.uuid4(), attempt_id=attempt.id, question_id=essay.id, text_answer="…", points_earned=0
    )
    db.add(essay_answer)
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=0))
    db.commit()
    return course, quiz, essay, essay_answer, attempt


def test_raising_the_weight_then_marking_full_is_full_marks_not_463_percent(db: Session, teacher, student) -> None:
    course, quiz, essay, answer, attempt = _quiz(db, teacher, "c-reweight-up")
    essay.points = 50
    answer.points_earned = 50
    answer.graded_at = datetime.now(UTC)
    db.flush()

    recompute_attempt_grade(db, attempt, quiz)
    db.commit()

    # Still out of its own 11: full marks, not 51/11.
    assert (attempt.score, attempt.max_score, attempt.passed) == (11, 11, True)
    assert calculate_student_grade_for_course(db, course, STUDENT_ID).final_score == 100.0


def test_an_auto_graded_answer_is_not_penalised_by_a_reweight(db: Session, teacher, student) -> None:
    """The inverse a review caught: the multiple-choice question re-weighted
    1 → 10 after submission must not turn a correct answer into a fail."""
    _course, quiz, essay, answer, attempt = _quiz(db, teacher, "c-reweight-mcq")
    mcq = db.query(QuizQuestion).filter(QuizQuestion.quiz_id == quiz.id, QuizQuestion.id != essay.id).one()
    mcq.points = 10
    answer.points_earned = 10
    answer.graded_at = datetime.now(UTC)
    db.flush()

    recompute_attempt_grade(db, attempt, quiz)

    assert (attempt.score, attempt.max_score, attempt.passed) == (11, 11, True)


def test_a_quiz_percentage_never_reads_above_100(db: Session, teacher, student) -> None:
    course, _, _essay, answer, attempt = _quiz(db, teacher, "c-reweight-cap")
    # A row left on two scales by the old code.
    answer.graded_at = datetime.now(UTC)
    attempt.score, attempt.max_score = 51, 11
    db.commit()

    assert calculate_student_grade_for_course(db, course, STUDENT_ID).final_score == 100.0
