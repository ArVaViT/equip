"""What a student hands in is checked before it counts (2026-10-03).

* An open question answered with nothing was kept «waiting for review»: the
  student's grade said so forever, while neither teacher queue showed it (both
  need text) — and an exam's one attempt was spent on it. It is a skipped
  question, recorded like one.
* An option id that is not one of the question's own was a 409 from the
  foreign key, or — an option of another question — stored as the student's
  choice and shown to the teacher.
* A course taken back to draft is a 404 to read and was still taking
  attempts that counted.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.course import Chapter, Course
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizAnswer, QuizOption, QuizQuestion

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID


def _quiz(db: Session, teacher, course_id: str) -> tuple[Course, Quiz, QuizQuestion, QuizQuestion, QuizOption]:
    course = Course(id=course_id, status="published", created_by=teacher.id, source_locale="en")
    db.add(course)
    db.flush()
    chapter = Chapter(id=f"{course_id}-ch", course_id=course_id, order_index=0, chapter_type="quiz", title="Q")
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id, passing_score=50)
    db.add(quiz)
    db.flush()
    essay = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_type="essay", points=5, order_index=0)
    choice = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_type="multiple_choice", points=1, order_index=1)
    db.add_all([essay, choice])
    db.flush()
    right = QuizOption(id=uuid.uuid4(), question_id=choice.id, is_correct=True, order_index=0)
    db.add_all([right, QuizOption(id=uuid.uuid4(), question_id=choice.id, is_correct=False, order_index=1)])
    db.add(Enrollment(id=f"enr-{course_id}", user_id=STUDENT_ID, course_id=course_id, progress=0))
    db.commit()
    return course, quiz, essay, choice, right


def test_a_blank_essay_is_a_skipped_question_not_a_pending_one(
    student_client: TestClient, db: Session, teacher, student
) -> None:
    _, quiz, essay, choice, right = _quiz(db, teacher, "c-blank-essay")

    resp = student_client.post(
        f"/api/v1/quizzes/{quiz.id}/submit",
        json={
            "answers": [
                {"question_id": str(essay.id), "text_answer": "   "},
                {"question_id": str(choice.id), "selected_option_id": str(right.id)},
            ]
        },
    )

    assert resp.status_code == 200, resp.text
    answer = db.query(QuizAnswer).filter(QuizAnswer.question_id == essay.id).one()
    assert answer.text_answer is None
    assert answer.graded_at is not None


def test_an_option_of_another_question_is_refused(student_client: TestClient, db: Session, teacher, student) -> None:
    _, quiz, essay, _choice, right = _quiz(db, teacher, "c-foreign-option")

    resp = student_client.post(
        f"/api/v1/quizzes/{quiz.id}/submit",
        json={"answers": [{"question_id": str(essay.id), "selected_option_id": str(right.id)}]},
    )

    assert resp.status_code == 400
    assert db.query(QuizAnswer).count() == 0


def test_a_course_back_in_draft_takes_no_attempt(student_client: TestClient, db: Session, teacher, student) -> None:
    course, quiz, _essay, choice, right = _quiz(db, teacher, "c-back-to-draft")
    course.status = "draft"
    db.commit()

    resp = student_client.post(
        f"/api/v1/quizzes/{quiz.id}/submit",
        json={"answers": [{"question_id": str(choice.id), "selected_option_id": str(right.id)}]},
    )

    assert resp.status_code == 404
