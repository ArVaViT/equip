"""Correcting a question must not throw away the work done on it.

Before ``PATCH /quizzes/questions/{id}`` existed, a teacher who noticed a
typo had one route: delete the quiz and build it again. ``quiz_attempts``
hangs off ``quizzes`` with ``ON DELETE CASCADE``, so the fix cost every
student their graded attempt — in a school that prints a transcript,
that is not a fix.

These tests hold the line that makes the edit safe: an attempt already
graded keeps its score, its answer, and its verdict, while the next
student sees the corrected wording. And the two edits that would quietly
rewrite history — changing a question's type after somebody answered it,
deleting an option out from under a stored answer — stay impossible.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.content_version import ContentVersion
from app.models.course import Chapter, Course, Module
from app.models.quiz import QuizAnswer, QuizAttempt
from tests.conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _seed_chapter(db: Session) -> str:
    course = Course(
        id="course-quiz-edit",
        title="Учебник",
        created_by=TEACHER_ID,
        status="draft",
        source_locale="ru",
    )
    module = Module(id="mod-quiz-edit", course_id=course.id, title="Раздел", order_index=0)
    chapter = Chapter(
        id="ch-quiz-edit",
        module_id=module.id,
        title="Глава",
        order_index=0,
        chapter_type="quiz",
    )
    db.add_all([course, module, chapter])
    db.commit()
    return chapter.id


def _make_quiz(client: TestClient, chapter_id: str, *, question_type: str = "multiple_choice") -> dict:
    payload = {
        "chapter_id": chapter_id,
        "title": "Тест по Бытию",
        "quiz_type": "quiz",
        "passing_score": 70,
        "questions": [
            {
                "question_text": "Кто создал небро и землю?",  # typo on purpose
                "question_type": question_type,
                "order_index": 0,
                "points": 2,
                "options": [
                    {"option_text": "Бог", "is_correct": True, "order_index": 0},
                    {"option_text": "Никто", "is_correct": False, "order_index": 1},
                ],
            },
        ],
    }
    resp = client.post("/api/v1/quizzes", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _grade_an_attempt(db: Session, quiz_id: str, question_id: str, option_id: str) -> uuid.UUID:
    """A finished, scored attempt — the thing the old workaround destroyed."""
    attempt = QuizAttempt(
        id=uuid.uuid4(),
        quiz_id=uuid.UUID(quiz_id),
        user_id=STUDENT_ID,
        score=2,
        max_score=2,
        passed=True,
    )
    db.add(attempt)
    db.flush()
    db.add(
        QuizAnswer(
            attempt_id=attempt.id,
            question_id=uuid.UUID(question_id),
            selected_option_id=uuid.UUID(option_id),
            is_correct=True,
            points_earned=2,
        )
    )
    db.commit()
    return attempt.id


def _active_text(db: Session, entity_type: str, entity_id: str, field: str) -> str | None:
    row = (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == entity_id,
            ContentVersion.field == field,
            ContentVersion.superseded_by.is_(None),
        )
        .first()
    )
    return row.text if row else None


class TestTheGradedWorkSurvives:
    def test_fixing_the_wording_keeps_the_attempt_and_its_score(self, client: TestClient, db: Session, student):
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id)
        question = quiz["questions"][0]
        attempt_id = _grade_an_attempt(db, quiz["id"], question["id"], question["options"][0]["id"])

        resp = client.patch(
            f"/api/v1/quizzes/questions/{question['id']}",
            json={"question_text": "Кто создал небо и землю?"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["questions"][0]["question_text"] == "Кто создал небо и землю?"

        # The correction reached the source of truth for text.
        assert _active_text(db, "quiz_question", question["id"], "question_text") == "Кто создал небо и землю?"

        # And the graded attempt is untouched: same score, same answer.
        survived = db.query(QuizAttempt).filter(QuizAttempt.id == attempt_id).first()
        assert survived is not None
        assert (survived.score, survived.max_score, survived.passed) == (2, 2, True)
        answer = db.query(QuizAnswer).filter(QuizAnswer.attempt_id == attempt_id).first()
        assert answer is not None
        assert answer.is_correct is True
        assert answer.points_earned == 2
        assert answer.selected_option_id is not None

    def test_points_change_does_not_rescore_a_finished_attempt(self, client: TestClient, db: Session, student):
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id)
        question = quiz["questions"][0]
        attempt_id = _grade_an_attempt(db, quiz["id"], question["id"], question["options"][0]["id"])

        resp = client.patch(f"/api/v1/quizzes/questions/{question['id']}", json={"points": 5})
        assert resp.status_code == 200, resp.text
        assert resp.json()["questions"][0]["points"] == 5

        # ``max_score`` was a snapshot taken when the attempt was graded.
        # A later change to the question's worth does not reach back.
        survived = db.query(QuizAttempt).filter(QuizAttempt.id == attempt_id).first()
        assert (survived.score, survived.max_score) == (2, 2)

    def test_fixing_the_answer_key_keeps_the_old_verdict(self, client: TestClient, db: Session, student):
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id)
        question = quiz["questions"][0]
        wrong_option = question["options"][1]
        attempt_id = _grade_an_attempt(db, quiz["id"], question["id"], question["options"][0]["id"])

        resp = client.patch(f"/api/v1/quizzes/options/{wrong_option['id']}", json={"is_correct": True})
        assert resp.status_code == 200, resp.text
        options = {o["id"]: o for o in resp.json()["questions"][0]["options"]}
        assert options[wrong_option["id"]]["is_correct"] is True

        answer = db.query(QuizAnswer).filter(QuizAnswer.attempt_id == attempt_id).first()
        assert answer.is_correct is True
        assert answer.points_earned == 2


class TestWhatAnEditMayNotDo:
    def test_changing_the_type_after_an_answer_is_refused(self, client: TestClient, db: Session, student):
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id)
        question = quiz["questions"][0]
        _grade_an_attempt(db, quiz["id"], question["id"], question["options"][0]["id"])

        resp = client.patch(
            f"/api/v1/quizzes/questions/{question['id']}",
            json={"question_type": "essay"},
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["code"] == "quiz.question_already_answered"

        db.expire_all()
        again = client.get(f"/api/v1/quizzes/{quiz['id']}?source=1")
        assert again.json()["questions"][0]["question_type"] == "multiple_choice"

    def test_changing_the_type_before_anyone_answers_is_allowed(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id)
        question = quiz["questions"][0]

        resp = client.patch(
            f"/api/v1/quizzes/questions/{question['id']}",
            json={"question_type": "essay", "min_words": 120},
        )
        assert resp.status_code == 200, resp.text
        edited = resp.json()["questions"][0]
        assert edited["question_type"] == "essay"
        assert edited["min_words"] == 120

    def test_the_option_list_is_not_editable_as_a_list(self, client: TestClient, db: Session):
        """No route deletes an option, because a deleted option nulls the
        answer that pointed at it."""
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id)
        question = quiz["questions"][0]

        resp = client.patch(
            f"/api/v1/quizzes/questions/{question['id']}",
            json={"options": []},
        )
        # Unknown field is ignored, not obeyed: the options stay.
        assert resp.status_code in (200, 422), resp.text
        if resp.status_code == 200:
            assert len(resp.json()["questions"][0]["options"]) == 2


class TestOnlyTheOwnerEdits:
    def test_a_stranger_cannot_correct_someone_elses_quiz(self, client: TestClient, db: Session, student):
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id)
        question = quiz["questions"][0]

        course = db.query(Course).filter(Course.id == "course-quiz-edit").first()
        course.created_by = STUDENT_ID  # somebody else's course now
        db.commit()

        resp = client.patch(
            f"/api/v1/quizzes/questions/{question['id']}",
            json={"question_text": "Чужой курс"},
        )
        assert resp.status_code in (403, 404), resp.text

    def test_a_missing_question_is_a_404(self, client: TestClient):
        resp = client.patch(
            f"/api/v1/quizzes/questions/{uuid.uuid4()}",
            json={"question_text": "нет такого"},
        )
        assert resp.status_code == 404, resp.text
