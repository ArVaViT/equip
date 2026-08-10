"""An essay nobody has read yet is not a zero.

An essay or short-answer quiz is submitted long before it is marked: its open
answers carry ``graded_at IS NULL`` until a teacher reads them, and until then
the attempt's score is 0 out of the full total. Every screen that treats that
like an ordinary result shows a red 0% for work nobody has looked at — on the
board a teacher uses to decide who gets a certificate.

The calculator already knew this (``category_is_live`` excludes attempts with
unread answers). The per-chapter payload did not, so the gradebook matrix
painted the cell red.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizAnswer, QuizAttempt, QuizQuestion
from app.services.student_progress_service import build_course_gradebook_matrix

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID


def _essay_quiz_course(db: Session, teacher, course_id: str, *, graded: bool):
    course = Course(id=course_id, status="published", created_by=teacher.id)
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(id=f"{course_id}-ch", module_id=module.id, order_index=0, chapter_type="quiz", title="Essay")
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id)
    db.add(quiz)
    db.flush()
    question = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_type="essay", points=10, order_index=0)
    db.add(question)
    attempt = QuizAttempt(
        id=uuid.uuid4(),
        quiz_id=quiz.id,
        user_id=STUDENT_ID,
        score=0,
        max_score=10,
        passed=False,
        completed_at=datetime.now(UTC),
    )
    db.add(attempt)
    db.flush()
    db.add(
        QuizAnswer(
            id=uuid.uuid4(),
            attempt_id=attempt.id,
            question_id=question.id,
            text_answer="Мой ответ",
            points_earned=0,
            graded_at=datetime.now(UTC) if graded else None,
        )
    )
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=0))
    db.commit()
    return course, chapter


def _cell(db: Session, course, chapter_id: str) -> dict:
    matrix = build_course_gradebook_matrix(db, course, course.id)
    student = next(s for s in matrix["students"] if s["id"] == str(STUDENT_ID))
    return next(c for c in student["chapters"] if c["id"] == chapter_id)


def test_an_unread_essay_is_flagged_as_waiting_not_scored(db: Session, teacher, student) -> None:
    course, chapter = _essay_quiz_course(db, teacher, "c-essay-unread", graded=False)

    cell = _cell(db, course, chapter.id)

    assert cell["quiz_result"] is not None
    assert cell["quiz_result"]["awaiting_grading"] is True, (
        "0 out of 10 with `passed=False` renders as a red failure — for work nobody has read"
    )


def test_a_marked_essay_is_an_ordinary_result(db: Session, teacher, student) -> None:
    """The flag must clear the moment a teacher marks it, or every essay quiz
    on the platform sits in a permanent "waiting" state."""
    course, chapter = _essay_quiz_course(db, teacher, "c-essay-read", graded=True)

    cell = _cell(db, course, chapter.id)

    assert cell["quiz_result"]["awaiting_grading"] is False


def test_a_multiple_choice_quiz_is_never_left_waiting(db: Session, teacher, student) -> None:
    """Auto-marked answers are graded at submission, so nothing is pending."""
    course = Course(id="c-essay-mcq", status="published", created_by=teacher.id)
    db.add(course)
    module = Module(id="c-essay-mcq-m", course_id=course.id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(id="c-essay-mcq-ch", module_id=module.id, order_index=0, chapter_type="quiz", title="Q")
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id)
    db.add(quiz)
    db.flush()
    question = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_type="multiple_choice", points=10, order_index=0)
    db.add(question)
    attempt = QuizAttempt(
        id=uuid.uuid4(),
        quiz_id=quiz.id,
        user_id=STUDENT_ID,
        score=10,
        max_score=10,
        passed=True,
        completed_at=datetime.now(UTC),
    )
    db.add(attempt)
    db.flush()
    db.add(
        QuizAnswer(
            id=uuid.uuid4(),
            attempt_id=attempt.id,
            question_id=question.id,
            is_correct=True,
            points_earned=10,
            graded_at=datetime.now(UTC),
        )
    )
    db.add(Enrollment(id="enr-c-essay-mcq", user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.commit()

    cell = _cell(db, course, chapter.id)

    assert cell["quiz_result"]["awaiting_grading"] is False
    assert cell["quiz_result"]["passed"] is True


def test_one_unread_answer_is_enough_to_hold_the_whole_attempt(db: Session, teacher, student) -> None:
    """A mixed quiz — some auto-marked questions, one essay — is not a result
    until the essay is read. Its score is a running total until then."""
    course = Course(id="c-essay-mixed", status="published", created_by=teacher.id)
    db.add(course)
    module = Module(id="c-essay-mixed-m", course_id=course.id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(id="c-essay-mixed-ch", module_id=module.id, order_index=0, chapter_type="quiz", title="Q")
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id)
    db.add(quiz)
    db.flush()
    attempt = QuizAttempt(
        id=uuid.uuid4(),
        quiz_id=quiz.id,
        user_id=STUDENT_ID,
        score=5,
        max_score=20,
        passed=False,
        completed_at=datetime.now(UTC),
    )
    db.add(attempt)
    db.flush()
    for question_type, graded_at in (("multiple_choice", datetime.now(UTC)), ("essay", None)):
        question = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_type=question_type, points=10, order_index=0)
        db.add(question)
        db.flush()
        db.add(
            QuizAnswer(
                id=uuid.uuid4(),
                attempt_id=attempt.id,
                question_id=question.id,
                points_earned=5,
                graded_at=graded_at,
            )
        )
    db.add(Enrollment(id="enr-c-essay-mixed", user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.commit()

    cell = _cell(db, course, chapter.id)

    assert cell["quiz_result"]["awaiting_grading"] is True
