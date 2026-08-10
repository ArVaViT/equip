"""An essay score is a person's judgement, so the row says whose.

That score decides a student's grade: the attempt is re-aggregated from these
answers, the attempt feeds the course grade, and the course grade goes on a
certificate. Every other link in the chain records its author. This one threw
the information away — the route already tagged its throughput metric with the
teacher's id, so a dashboard could answer "who marked this" while the database
could not, which is precisely backwards for a disputed grade.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizAnswer, QuizAttempt, QuizQuestion

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID, TEACHER_ID


def _pending_essay(db: Session, teacher, course_id: str):
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
    answer = QuizAnswer(
        id=uuid.uuid4(),
        attempt_id=attempt.id,
        question_id=question.id,
        text_answer="Мой ответ",
        points_earned=0,
    )
    db.add(answer)
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=0))
    db.commit()
    return answer


def test_marking_an_answer_records_who_marked_it(client, db: Session, teacher, student) -> None:
    answer = _pending_essay(db, teacher, "c-graded-by")

    resp = client.patch(
        f"/api/v1/quizzes/answers/{answer.id}",
        json={"points_earned": 8, "grader_comment": "Хорошо"},
    )

    assert resp.status_code == 200, resp.text
    db.refresh(answer)
    assert answer.graded_by == TEACHER_ID
    assert answer.graded_at is not None


def test_a_regrade_records_the_teacher_who_did_it(client, db: Session, teacher, student) -> None:
    """The author is the person who set the score that stands, not the first
    person who touched it — a re-grade is the disputed case."""
    answer = _pending_essay(db, teacher, "c-graded-by-again")
    client.patch(f"/api/v1/quizzes/answers/{answer.id}", json={"points_earned": 2})
    db.refresh(answer)
    first = answer.graded_at

    resp = client.patch(f"/api/v1/quizzes/answers/{answer.id}", json={"points_earned": 9})

    assert resp.status_code == 200, resp.text
    db.refresh(answer)
    assert answer.graded_by == TEACHER_ID
    assert answer.graded_at >= first
    assert answer.points_earned == 9


def test_an_auto_marked_answer_has_no_grader(db: Session, teacher, student) -> None:
    """NULL here is not a gap — nobody marked it, and claiming otherwise would
    put a teacher's name on a machine's decision."""
    from app.services.quiz_service import AUTO_GRADED_QUESTION_TYPES

    assert "multiple_choice" in AUTO_GRADED_QUESTION_TYPES

    answer = QuizAnswer(
        id=uuid.uuid4(),
        attempt_id=uuid.uuid4(),
        question_id=uuid.uuid4(),
        is_correct=True,
        points_earned=10,
        graded_at=datetime.now(UTC),
    )

    assert answer.graded_by is None
