"""A graded quiz is the worst place to serve a blank.

Since the spare language was removed, a quiz with no rows in the
reader's language resolves to empty strings — and empty strings render.
The student is shown a blank question with blank options, answers
nothing, and the attempt counts against them.

The Daily Challenge already takes this position for the same reason.
This is the graded version of the same page, so it takes it harder: the
route refuses rather than returning something unusable.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.chapter_block import ChapterBlock
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizOption, QuizQuestion
from app.services.content_versions.write import record_human_version
from app.services.translation.service import reset_translation_provider_cache

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User


@pytest.fixture(autouse=True)
def _translation_is_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()
    yield
    reset_translation_provider_cache()


def _russian_quiz(db: Session, teacher: User, student: User) -> tuple[Course, Chapter, Quiz]:
    course = Course(
        id=f"course-{uuid.uuid4().hex[:8]}",
        created_by=teacher.id,
        status="published",
        source_locale="ru",
    )
    db.add(course)
    db.flush()
    module = Module(id=str(uuid.uuid4()), course_id=course.id, order_index=0)
    db.add(module)
    db.flush()
    chapter = Chapter(
        id=str(uuid.uuid4()),
        module_id=module.id,
        title="Урок 1",
        order_index=0,
        chapter_type="quiz",
    )
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id, max_attempts=1)
    db.add(quiz)
    db.flush()
    question = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, question_type="multiple_choice", order_index=0)
    db.add(question)
    db.flush()
    record_human_version(
        db,
        entity_type="quiz_question",
        entity_id=str(question.id),
        field="question_text",
        locale="ru",
        text="Кто написал послание к римлянам?",
        authored_by=teacher.id,
    )
    for index, text in enumerate(("Павел", "Пётр")):
        option = QuizOption(id=uuid.uuid4(), question_id=question.id, is_correct=index == 0, order_index=index)
        db.add(option)
        db.flush()
        record_human_version(
            db,
            entity_type="quiz_option",
            entity_id=str(option.id),
            field="option_text",
            locale="ru",
            text=text,
            authored_by=teacher.id,
        )
    db.add(ChapterBlock(id=uuid.uuid4(), chapter_id=chapter.id, block_type="quiz", order_index=0, quiz_id=quiz.id))
    db.add(Enrollment(id=f"enr-{course.id}", user_id=student.id, course_id=course.id, progress=0))
    db.commit()
    return course, chapter, quiz


class TestAQuizWithNothingInThisLanguage:
    def test_the_route_refuses_rather_than_serving_blanks(
        self, db: Session, teacher: User, student: User, student_client: TestClient
    ):
        _, chapter, _ = _russian_quiz(db, teacher, student)

        resp = student_client.get(
            f"/api/v1/quizzes/chapter/{chapter.id}",
            headers={"Accept-Language": "de"},
        )

        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "quiz.not_translated"

    def test_the_reader_whose_language_it_is_takes_the_quiz(
        self, db: Session, teacher: User, student: User, student_client: TestClient
    ):
        _, chapter, _ = _russian_quiz(db, teacher, student)

        resp = student_client.get(
            f"/api/v1/quizzes/chapter/{chapter.id}",
            headers={"Accept-Language": "ru"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["questions"][0]["question_text"] == "Кто написал послание к римлянам?"
        assert all(o["option_text"] for o in body["questions"][0]["options"])
