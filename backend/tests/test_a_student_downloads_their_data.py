"""A reader can download everything Equip keeps about them — and nothing about anyone else.

GDPR gives a German reader the right to a copy of their data; every reader is
owed a plain answer to "what do you have on me?". These pin that the file
holds the caller's own rows across the tables that are about them, that a
classmate's rows in the same course never appear, and that it is a download
nobody caches.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizAnswer, QuizAttempt, QuizQuestion
from app.models.user import User
from tests._cv_helpers import make_course_with_text
from tests.conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _class(db: Session) -> uuid.UUID:
    course = make_course_with_text(db, title="Acts", status="published", created_by=TEACHER_ID)
    module = Module(id=f"m-{course.id}", course_id=course.id, title="M", order_index=0)
    reading = Chapter(id=f"r-{course.id}", course_id=course.id, module_id=module.id, title="R", order_index=0)
    test = Chapter(
        id=f"q-{course.id}", course_id=course.id, module_id=module.id, title="Q", order_index=1, chapter_type="quiz"
    )
    essay = Chapter(
        id=f"a-{course.id}",
        course_id=course.id,
        module_id=module.id,
        title="A",
        order_index=2,
        chapter_type="assignment",
    )
    db.add_all([module, reading, test, essay])
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=test.id)
    db.add(quiz)
    db.flush()
    question = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, order_index=0)
    assignment = Assignment(id=uuid.uuid4(), chapter_id=essay.id, max_score=10)
    db.add_all([question, assignment])
    db.flush()

    classmate = User(id=uuid.uuid4(), email="classmate@example.com", full_name="Classmate", role="student")
    db.add(classmate)
    db.flush()
    for who, words in ((STUDENT_ID, "mine"), (classmate.id, "theirs")):
        db.add(Enrollment(id=str(uuid.uuid4()), user_id=who, course_id=course.id, progress=50))
        db.add(ChapterProgress(user_id=who, chapter_id=reading.id, completed=True))
        attempt = QuizAttempt(id=uuid.uuid4(), quiz_id=quiz.id, user_id=who, score=1, max_score=1)
        db.add(attempt)
        db.flush()
        db.add(QuizAnswer(attempt_id=attempt.id, question_id=question.id, text_answer=f"{words} answer"))
        db.add(AssignmentSubmission(assignment_id=assignment.id, student_id=who, content=f"{words} essay"))
    db.commit()
    return classmate.id


def test_the_file_holds_my_rows_and_none_of_my_classmates(
    student_client: TestClient, db: Session, student: User
) -> None:
    classmate = _class(db)
    r = student_client.get("/api/v1/users/me/export")
    assert r.status_code == 200, r.text
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["content-disposition"].startswith('attachment; filename="equip-my-data-')

    data = r.json()
    assert data["format"] == "equip-my-data"
    assert data["profile"]["id"] == str(STUDENT_ID)
    assert len(data["enrollments"]) == 1
    assert len(data["lessons_completed"]) == 1
    assert [a["text_answer"] for a in data["quiz_answers"]] == ["mine answer"]
    assert [s["content"] for s in data["assignment_submissions"]] == ["mine essay"]
    assert str(classmate) not in r.text
    assert "theirs" not in r.text


def test_a_stranger_gets_nothing(anon_client: TestClient) -> None:
    assert anon_client.get("/api/v1/users/me/export").status_code == 401
