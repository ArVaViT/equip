"""A chapter has one quiz, and a rebuild is one step.

Every reader assumes one quiz per chapter: a student is handed the
chapter's ``.first()`` quiz, the grade sheet counts every quiz in the
chapter. Nothing enforced it. The editor rebuilt a quiz whose shape
changed as two requests — create the new one, delete the old one — and
when the delete was refused (a student finished an attempt between the
two) the chapter was left with both: the student saw one, the grade
counted two (2026-10-03).

Two things hold the line now. ``POST /quizzes`` refuses a second quiz on
a chapter that has one. ``POST /quizzes/{id}/replace`` puts the new quiz
in the old one's place inside one transaction — refusing first, with the
number of attempts, when there is something to lose and ``force`` was not
said — so there is no moment at which the chapter has two.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.chapter_block import ChapterBlock
from app.models.content_version import ContentVersion
from app.models.course import Chapter, Course, Module
from app.models.quiz import Quiz, QuizAttempt
from tests.conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _seed_chapter(db: Session) -> str:
    course = Course(id="course-one-quiz", title="Учебник", created_by=TEACHER_ID, status="draft", source_locale="ru")
    module = Module(id="mod-one-quiz", course_id=course.id, title="Раздел", order_index=0)
    chapter = Chapter(id="ch-one-quiz", module_id=module.id, title="Глава", order_index=0, chapter_type="quiz")
    db.add_all([course, module, chapter])
    db.commit()
    return chapter.id


def _body(*, title: str = "Тест по Бытию", option_count: int = 2) -> dict:
    options = [{"option_text": f"Вариант {i + 1}", "is_correct": i == 0, "order_index": i} for i in range(option_count)]
    return {
        "title": title,
        "quiz_type": "quiz",
        "passing_score": 70,
        "questions": [
            {
                "question_text": "Кто создал небо и землю?",
                "question_type": "multiple_choice",
                "order_index": 0,
                "points": 2,
                "options": options,
            }
        ],
    }


def _create(client: TestClient, chapter_id: str) -> dict:
    resp = client.post("/api/v1/quizzes", json={"chapter_id": chapter_id, **_body()})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _cv_count(db: Session, quiz: dict) -> int:
    ids = (
        [quiz["id"]] + [q["id"] for q in quiz["questions"]] + [o["id"] for q in quiz["questions"] for o in q["options"]]
    )
    return db.query(ContentVersion).filter(ContentVersion.entity_id.in_(ids)).count()


class TestASecondQuizIsRefused:
    def test_a_chapter_that_has_a_quiz_does_not_take_another(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        first = _create(client, chapter_id)

        resp = client.post("/api/v1/quizzes", json={"chapter_id": chapter_id, **_body(title="Второй")})

        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "quiz.already_exists"
        assert detail["context"]["existing_quiz_id"] == first["id"]
        assert db.query(Quiz).filter(Quiz.chapter_id == chapter_id).count() == 1

    def test_a_chapter_without_a_quiz_still_takes_one(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        _create(client, chapter_id)
        assert db.query(Quiz).filter(Quiz.chapter_id == chapter_id).count() == 1


class TestARebuildIsOneStep:
    def test_the_new_quiz_takes_the_old_ones_place(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        old = _create(client, chapter_id)
        old_cv_rows = _cv_count(db, old)
        assert old_cv_rows > 0

        resp = client.post(
            f"/api/v1/quizzes/{old['id']}/replace", json=_body(title="Тест по двум главам", option_count=3)
        )

        assert resp.status_code == 201, resp.text
        new = resp.json()
        assert new["id"] != old["id"]
        assert new["chapter_id"] == chapter_id
        assert new["title"] == "Тест по двум главам"
        assert len(new["questions"][0]["options"]) == 3
        # Exactly one quiz on the chapter, and it is the new one.
        assert [str(q.id) for q in db.query(Quiz).filter(Quiz.chapter_id == chapter_id).all()] == [new["id"]]
        # The old quiz's text went with it; the new quiz's text is there.
        assert _cv_count(db, old) == 0
        assert _cv_count(db, new) > 0

    def test_a_block_that_pointed_at_the_old_quiz_points_at_the_new_one(self, client: TestClient, db: Session):
        # ``chapter_blocks.quiz_id`` is ``ON DELETE SET NULL``: without the
        # repoint the lesson's quiz block forgets its quiz the moment the
        # old one goes, and the lesson shows an empty quiz block.
        chapter_id = _seed_chapter(db)
        old = _create(client, chapter_id)
        block = ChapterBlock(chapter_id=chapter_id, block_type="quiz", order_index=0, quiz_id=uuid.UUID(old["id"]))
        db.add(block)
        db.commit()
        block_id = block.id

        resp = client.post(f"/api/v1/quizzes/{old['id']}/replace", json=_body(option_count=3))
        assert resp.status_code == 201, resp.text

        db.expire_all()
        repointed = db.query(ChapterBlock).filter(ChapterBlock.id == block_id).one()
        assert str(repointed.quiz_id) == resp.json()["id"]

    def test_with_attempts_and_no_force_nothing_changes(self, client: TestClient, db: Session, student):
        chapter_id = _seed_chapter(db)
        old = _create(client, chapter_id)
        for _ in range(2):
            db.add(QuizAttempt(quiz_id=uuid.UUID(old["id"]), user_id=STUDENT_ID, score=2, max_score=2, passed=True))
        db.commit()

        resp = client.post(f"/api/v1/quizzes/{old['id']}/replace", json=_body(option_count=3))

        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "quiz.has_attempts"
        assert detail["context"]["attempt_count"] == 2
        # The old quiz, its attempts and its text are exactly as they were,
        # and no second quiz appeared.
        assert [str(q.id) for q in db.query(Quiz).filter(Quiz.chapter_id == chapter_id).all()] == [old["id"]]
        assert db.query(QuizAttempt).filter(QuizAttempt.quiz_id == uuid.UUID(old["id"])).count() == 2
        assert _cv_count(db, old) > 0

    def test_with_force_the_attempts_go_with_the_old_quiz(self, client: TestClient, db: Session, student):
        chapter_id = _seed_chapter(db)
        old = _create(client, chapter_id)
        db.add(QuizAttempt(quiz_id=uuid.UUID(old["id"]), user_id=STUDENT_ID, score=2, max_score=2, passed=True))
        db.commit()

        resp = client.post(f"/api/v1/quizzes/{old['id']}/replace", params={"force": "true"}, json=_body(option_count=3))

        assert resp.status_code == 201, resp.text
        assert [str(q.id) for q in db.query(Quiz).filter(Quiz.chapter_id == chapter_id).all()] == [resp.json()["id"]]
        assert db.query(QuizAttempt).count() == 0

    def test_a_body_creation_would_refuse_leaves_the_old_quiz_alone(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        old = _create(client, chapter_id)
        body = _body(option_count=3)
        for option in body["questions"][0]["options"]:
            option["is_correct"] = False

        resp = client.post(f"/api/v1/quizzes/{old['id']}/replace", json=body)

        assert resp.status_code == 422, resp.text
        assert [str(q.id) for q in db.query(Quiz).filter(Quiz.chapter_id == chapter_id).all()] == [old["id"]]

    def test_a_stranger_cannot_replace_someone_elses_quiz(self, client: TestClient, db: Session, student):
        chapter_id = _seed_chapter(db)
        old = _create(client, chapter_id)
        db.query(Course).filter(Course.id == "course-one-quiz").update({"created_by": STUDENT_ID})
        db.commit()

        resp = client.post(f"/api/v1/quizzes/{old['id']}/replace", json=_body(option_count=3))

        assert resp.status_code == 403, resp.text
        assert [str(q.id) for q in db.query(Quiz).filter(Quiz.chapter_id == chapter_id).all()] == [old["id"]]

    def test_a_missing_quiz_is_a_404(self, client: TestClient, db: Session):
        _seed_chapter(db)
        resp = client.post(f"/api/v1/quizzes/{uuid.uuid4()}/replace", json=_body())
        assert resp.status_code == 404, resp.text
