"""The week's review: questions from tests taken a while ago, wrong ones first.

Pins what is offered (completed, a week old, single right option, text in
the reader's language), what never is (an exam, a test not yet taken), that
the set holds for the week, and that checking an answer reveals nothing a
student's own results screen has not.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.models.course import Chapter, Module
from app.models.enrollment import Enrollment
from app.models.quiz import QuizAnswer, QuizAttempt
from app.services.review_questions import pick_review_questions
from tests._cv_helpers import (
    make_course_with_text,
    make_quiz_option_with_text,
    make_quiz_question_with_text,
    make_quiz_with_text,
)
from tests.conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _quiz(db: Session, course_id: str, module_id: str, name: str, *, quiz_type: str = "quiz", n: int = 3):
    chapter = Chapter(
        id=f"{name}-{course_id}",
        course_id=course_id,
        module_id=module_id,
        title=name,
        order_index=0,
        chapter_type="quiz",
    )
    db.add(chapter)
    db.flush()
    quiz = make_quiz_with_text(db, chapter_id=chapter.id, quiz_type=quiz_type)
    questions = []
    for i in range(n):
        q = make_quiz_question_with_text(db, quiz_id=quiz.id, question_text=f"{name} Q{i}?", order_index=i)
        right = make_quiz_option_with_text(db, question_id=q.id, option_text="right", is_correct=True, order_index=0)
        make_quiz_option_with_text(db, question_id=q.id, option_text="wrong", order_index=1)
        questions.append((q, right))
    return quiz, questions


def _took(db: Session, quiz, questions, *, days_ago: float, wrong: set[int] = frozenset()) -> None:  # type: ignore[assignment]
    attempt = QuizAttempt(
        id=uuid.uuid4(),
        quiz_id=quiz.id,
        user_id=STUDENT_ID,
        score=1,
        max_score=len(questions),
        started_at=NOW - timedelta(days=days_ago),
        completed_at=NOW - timedelta(days=days_ago),
    )
    db.add(attempt)
    db.flush()
    for i, (q, _right) in enumerate(questions):
        db.add(QuizAnswer(attempt_id=attempt.id, question_id=q.id, is_correct=i not in wrong))


def _setup(db: Session):
    course = make_course_with_text(db, title="Acts", status="published", created_by=TEACHER_ID)
    module = Module(id=f"m-{course.id}", course_id=course.id, title="M", order_index=0)
    db.add(module)
    db.add(Enrollment(id=str(uuid.uuid4()), user_id=STUDENT_ID, course_id=course.id, progress=50))
    db.flush()
    old, old_qs = _quiz(db, course.id, module.id, "old", n=8)
    recent, recent_qs = _quiz(db, course.id, module.id, "recent")
    exam, exam_qs = _quiz(db, course.id, module.id, "exam", quiz_type="exam")
    _untaken, untaken_qs = _quiz(db, course.id, module.id, "untaken")
    _took(db, old, old_qs, days_ago=20, wrong={6, 7})
    _took(db, recent, recent_qs, days_ago=2)
    _took(db, exam, exam_qs, days_ago=20)
    db.commit()
    return course, old_qs, untaken_qs, exam_qs


def test_old_tests_only_wrong_answers_first_and_the_same_all_week(db: Session, teacher: User, student: User) -> None:
    course, _old_qs, _untaken, _exam = _setup(db)
    picked = pick_review_questions(
        db, user_id=STUDENT_ID, course_id=course.id, display_locale="en", source_locale="en", now=NOW
    )
    assert len(picked) == 5
    assert all(q.question_text.startswith("old ") for q in picked)
    assert {q.question_text for q in picked[:2]} == {"old Q6?", "old Q7?"}
    later = pick_review_questions(
        db,
        user_id=STUDENT_ID,
        course_id=course.id,
        display_locale="en",
        source_locale="en",
        now=NOW + timedelta(hours=30),
    )
    assert [q.id for q in later] == [q.id for q in picked]
    # Nothing in the reader's language, nothing offered.
    assert (
        pick_review_questions(
            db, user_id=STUDENT_ID, course_id=course.id, display_locale="de", source_locale="en", now=NOW
        )
        == []
    )


def test_checking_reveals_only_what_the_results_screen_did(
    student_client: TestClient, db: Session, teacher: User, student: User
) -> None:
    _course, old_qs, untaken_qs, exam_qs = _setup(db)
    q, right = old_qs[0]
    r = student_client.post("/api/v1/review/check", json={"question_id": str(q.id), "option_id": str(right.id)})
    assert r.status_code == 200, r.text
    assert r.json() == {"correct": True, "correct_option_id": str(right.id)}

    for question, answer in (untaken_qs[0], exam_qs[0]):
        r = student_client.post(
            "/api/v1/review/check", json={"question_id": str(question.id), "option_id": str(answer.id)}
        )
        assert r.status_code == 404


def test_the_course_page_gets_the_set(student_client: TestClient, db: Session, teacher: User, student: User) -> None:
    course, *_ = _setup(db)
    r = student_client.get(f"/api/v1/review/course/{course.id}")
    assert r.status_code == 200, r.text
    # "now" is real here; the fixtures are dated around 2026-10-01, so at
    # least the old test qualifies whatever today is.
    rows = r.json()
    assert rows and all("is_correct" not in o for q in rows for o in q["options"])
