"""Phase 1e integration tests: quiz / question / option dual-writes.

Quiz creation is one-shot — Quiz + Questions + Options all land in
a single endpoint call. The dual-write fans out: one row per
(quiz, field), one per (question, field), one per (option, field).
``update_quiz`` only mutates the Quiz row itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.models.content_version import ContentVersion
from app.models.course import Chapter, Course, Module
from app.models.quiz import Quiz, QuizOption, QuizQuestion
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _seed_chapter(db: Session) -> str:
    course = Course(
        id="course-quiz-dw",
        title="Учебник",
        created_by=TEACHER_ID,
        status="draft",
        source_locale="ru",
    )
    module = Module(id="mod-quiz-dw", course_id=course.id, title="Раздел", order_index=0)
    chapter = Chapter(
        id="ch-quiz-dw",
        module_id=module.id,
        title="Глава",
        order_index=0,
        chapter_type="quiz",
    )
    db.add_all([course, module, chapter])
    db.commit()
    return chapter.id


def _active(db: Session, entity_type: str, entity_id: str) -> list[ContentVersion]:
    return (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == entity_id,
            ContentVersion.superseded_by.is_(None),
        )
        .order_by(ContentVersion.field)
        .all()
    )


class TestCreateQuizDualWrite:
    def test_writes_quiz_question_option_rows(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        payload = {
            "chapter_id": chapter_id,
            "title": "Тест по Бытию",
            "description": "Краткий тест после первой главы.",
            "quiz_type": "quiz",
            "passing_score": 70,
            "questions": [
                {
                    "question_text": "Кто создал небо и землю?",
                    "question_type": "multiple_choice",
                    "order_index": 0,
                    "points": 1,
                    "options": [
                        {"option_text": "Бог", "is_correct": True, "order_index": 0},
                        {"option_text": "Никто", "is_correct": False, "order_index": 1},
                    ],
                },
            ],
        }
        resp = client.post("/api/v1/quizzes", json=payload)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        quiz_id = data["id"]
        # Quiz: title + description rows.
        quiz_rows = {r.field: r for r in _active(db, "quiz", quiz_id)}
        assert set(quiz_rows.keys()) == {"title", "description"}
        assert quiz_rows["title"].text == "Тест по Бытию"
        assert quiz_rows["title"].locale == "ru"
        assert quiz_rows["title"].authored_by == TEACHER_ID
        # Question row.
        question_id = data["questions"][0]["id"]
        question_rows = _active(db, "quiz_question", question_id)
        assert len(question_rows) == 1
        assert question_rows[0].field == "question_text"
        assert "Кто создал" in question_rows[0].text
        # Option rows (one per option).
        for opt in data["questions"][0]["options"]:
            opt_rows = _active(db, "quiz_option", opt["id"])
            assert len(opt_rows) == 1
            assert opt_rows[0].field == "option_text"

    def test_quiz_without_description_skips_description_row(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        resp = client.post(
            "/api/v1/quizzes",
            json={
                "chapter_id": chapter_id,
                "title": "Тест",
                "description": None,
                "quiz_type": "quiz",
                "passing_score": 70,
                "questions": [],
            },
        )
        assert resp.status_code == 201, resp.text
        quiz_id = resp.json()["id"]
        rows = _active(db, "quiz", quiz_id)
        assert [r.field for r in rows] == ["title"]


class TestUpdateQuizDualWrite:
    def test_title_change_supersedes_quiz_title_row(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        resp = client.post(
            "/api/v1/quizzes",
            json={
                "chapter_id": chapter_id,
                "title": "Старое",
                "description": "Описание.",
                "quiz_type": "quiz",
                "passing_score": 70,
                "questions": [],
            },
        )
        quiz_id = resp.json()["id"]
        original_title = next(r for r in _active(db, "quiz", quiz_id) if r.field == "title")
        resp = client.put(f"/api/v1/quizzes/{quiz_id}", json={"title": "Новое"})
        assert resp.status_code == 200, resp.text
        active_title = next(r for r in _active(db, "quiz", quiz_id) if r.field == "title")
        assert active_title.text == "Новое"
        db.refresh(original_title)
        assert original_title.superseded_by == active_title.id

    def test_non_text_patch_does_not_touch_content_versions(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        resp = client.post(
            "/api/v1/quizzes",
            json={
                "chapter_id": chapter_id,
                "title": "Стабильный",
                "description": "Описание.",
                "quiz_type": "quiz",
                "passing_score": 70,
                "questions": [],
            },
        )
        quiz_id = resp.json()["id"]
        ids_before = {r.id for r in _active(db, "quiz", quiz_id)}
        resp = client.put(f"/api/v1/quizzes/{quiz_id}", json={"passing_score": 80})
        assert resp.status_code == 200, resp.text
        ids_after = {r.id for r in _active(db, "quiz", quiz_id)}
        assert ids_before == ids_after


@pytest.fixture(autouse=True)
def _isolate(db: Session):
    yield
    db.query(ContentVersion).filter(ContentVersion.entity_type.in_(("quiz", "quiz_question", "quiz_option"))).delete()
    db.query(QuizOption).delete()
    db.query(QuizQuestion).delete()
    db.query(Quiz).delete()
    db.commit()
