"""A question is never left without a right answer.

Creation checks that a question can be answered — two options at least,
exactly one of them right, none under a written-answer question. The edit
routes checked nothing. ``PATCH /quizzes/options/{id}`` took «this option
is no longer correct» for the only correct option; ``PATCH
/quizzes/questions/{id}`` turned a short answer into a multiple choice
with no options. The editor sent its corrections one option at a time, so
the check could not go on those routes without refusing the moment between
«old answer off» and «new answer on» (2026-10-03).

So a question is now saved whole: ``PUT /quizzes/questions/{id}`` carries
the question's fields and every option, is validated the way creation is,
and is applied in one transaction. The per-row routes stay for callers
that send one field, and refuse an edit that leaves the question
unanswerable. Either way the option rows are the same rows afterwards,
so every stored answer still points at the option the student chose.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.content_version import ContentVersion
from app.models.course import Chapter, Course, Module
from app.models.quiz import QuizAnswer, QuizAttempt, QuizOption, QuizQuestion
from tests.conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _seed_chapter(db: Session) -> str:
    course = Course(id="course-whole-q", title="Учебник", created_by=TEACHER_ID, status="draft", source_locale="ru")
    module = Module(id="mod-whole-q", course_id=course.id, title="Раздел", order_index=0)
    chapter = Chapter(id="ch-whole-q", module_id=module.id, title="Глава", order_index=0, chapter_type="quiz")
    db.add_all([course, module, chapter])
    db.commit()
    return chapter.id


def _make_quiz(client: TestClient, chapter_id: str, *, question_type: str = "multiple_choice") -> dict:
    options = (
        [
            {"option_text": "Бог", "is_correct": True, "order_index": 0},
            {"option_text": "Никто", "is_correct": False, "order_index": 1},
            {"option_text": "Случай", "is_correct": False, "order_index": 2},
        ]
        if question_type in ("multiple_choice", "true_false")
        else []
    )
    resp = client.post(
        "/api/v1/quizzes",
        json={
            "chapter_id": chapter_id,
            "title": "Тест по Бытию",
            "quiz_type": "quiz",
            "passing_score": 70,
            "questions": [
                {
                    "question_text": "Кто создал небо и землю?",
                    "question_type": question_type,
                    "order_index": 0,
                    "points": 2,
                    "options": options,
                }
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _whole(question: dict, **changes) -> dict:
    """The question as the editor would send it, with ``changes`` applied."""
    body = {
        "question_text": question["question_text"],
        "question_type": question["question_type"],
        "order_index": question["order_index"],
        "points": question["points"],
        "min_words": question.get("min_words"),
        "options": [
            {
                "id": o["id"],
                "option_text": o["option_text"],
                "is_correct": o["is_correct"],
                "order_index": o["order_index"],
            }
            for o in question["options"]
        ],
    }
    body.update(changes)
    return body


def _grade_an_attempt(db: Session, quiz_id: str, question_id: str, option_id: str) -> uuid.UUID:
    attempt = QuizAttempt(
        id=uuid.uuid4(), quiz_id=uuid.UUID(quiz_id), user_id=STUDENT_ID, score=2, max_score=2, passed=True
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


def _correct_ids(db: Session, question_id: str) -> set[str]:
    rows = db.query(QuizOption).filter(QuizOption.question_id == uuid.UUID(question_id), QuizOption.is_correct).all()
    return {str(o.id) for o in rows}


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


class TestSavingAQuestionWhole:
    def test_the_right_answer_moves_in_one_request_and_the_options_stay_the_same_rows(
        self, client: TestClient, db: Session, student
    ):
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id)
        question = quiz["questions"][0]
        first, second, third = question["options"]
        attempt_id = _grade_an_attempt(db, quiz["id"], question["id"], first["id"])
        body = _whole(question, question_text="Кто сотворил небо и землю?")
        body["options"][0]["is_correct"] = False
        body["options"][2]["is_correct"] = True
        body["options"][2]["option_text"] = "Случайность"

        resp = client.put(f"/api/v1/quizzes/questions/{question['id']}", json=body)

        assert resp.status_code == 200, resp.text
        saved = resp.json()["questions"][0]
        assert saved["question_text"] == "Кто сотворил небо и землю?"
        assert [o["id"] for o in saved["options"]] == [first["id"], second["id"], third["id"]]
        assert [o["is_correct"] for o in saved["options"]] == [False, False, True]
        assert saved["options"][2]["option_text"] == "Случайность"
        assert _correct_ids(db, question["id"]) == {third["id"]}
        assert _active_text(db, "quiz_option", third["id"], "option_text") == "Случайность"
        # The graded attempt keeps its verdict and still says what was chosen.
        answer = db.query(QuizAnswer).filter(QuizAnswer.attempt_id == attempt_id).one()
        assert (answer.is_correct, answer.points_earned, str(answer.selected_option_id)) == (True, 2, first["id"])

    def test_a_question_left_without_a_right_answer_is_refused_and_nothing_moves(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id)
        question = quiz["questions"][0]
        body = _whole(question, question_text="Изменённый текст")
        for option in body["options"]:
            option["is_correct"] = False

        resp = client.put(f"/api/v1/quizzes/questions/{question['id']}", json=body)

        assert resp.status_code == 422, resp.text
        assert {e["type"] for e in resp.json()["detail"]} == {"quiz_no_correct_option"}
        assert _correct_ids(db, question["id"]) == {question["options"][0]["id"]}
        assert _active_text(db, "quiz_question", question["id"], "question_text") == "Кто создал небо и землю?"

    def test_two_right_answers_are_refused(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id)
        question = quiz["questions"][0]
        body = _whole(question)
        body["options"][1]["is_correct"] = True

        resp = client.put(f"/api/v1/quizzes/questions/{question['id']}", json=body)

        assert resp.status_code == 422, resp.text
        assert {e["type"] for e in resp.json()["detail"]} == {"quiz_many_correct_options"}
        assert _correct_ids(db, question["id"]) == {question["options"][0]["id"]}

    def test_an_option_the_question_does_not_have_is_a_stale_editor(self, client: TestClient, db: Session):
        # Nothing is added or removed in place; a body with other ids was
        # written against a quiz that has since been rebuilt.
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id)
        question = quiz["questions"][0]
        body = _whole(question)
        body["options"][2]["id"] = str(uuid.uuid4())

        resp = client.put(f"/api/v1/quizzes/questions/{question['id']}", json=body)

        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "quiz.options_changed"
        assert detail["context"]["unknown_option_ids"] == [body["options"][2]["id"]]
        assert detail["context"]["missing_option_ids"] == [question["options"][2]["id"]]
        assert db.query(QuizOption).filter(QuizOption.question_id == uuid.UUID(question["id"])).count() == 3

    def test_an_option_left_out_is_not_deleted(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id)
        question = quiz["questions"][0]
        body = _whole(question)
        body["options"].pop()

        resp = client.put(f"/api/v1/quizzes/questions/{question['id']}", json=body)

        assert resp.status_code == 409, resp.text
        assert db.query(QuizOption).filter(QuizOption.question_id == uuid.UUID(question["id"])).count() == 3

    def test_the_type_of_an_answered_question_stays(self, client: TestClient, db: Session, student):
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id, question_type="short_answer")
        question = quiz["questions"][0]
        _grade_an_attempt_text = QuizAttempt(
            id=uuid.uuid4(), quiz_id=uuid.UUID(quiz["id"]), user_id=STUDENT_ID, score=0, max_score=2
        )
        db.add(_grade_an_attempt_text)
        db.flush()
        db.add(
            QuizAnswer(attempt_id=_grade_an_attempt_text.id, question_id=uuid.UUID(question["id"]), text_answer="Бог")
        )
        db.commit()

        resp = client.put(
            f"/api/v1/quizzes/questions/{question['id']}",
            json=_whole(question, question_type="essay", min_words=50),
        )

        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["code"] == "quiz.question_already_answered"
        assert db.query(QuizQuestion).filter(QuizQuestion.id == uuid.UUID(question["id"])).one().question_type == (
            "short_answer"
        )

    def test_a_written_question_moves_between_its_two_kinds(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id, question_type="short_answer")
        question = quiz["questions"][0]

        resp = client.put(
            f"/api/v1/quizzes/questions/{question['id']}",
            json=_whole(question, question_type="essay", min_words=50, points=5),
        )

        assert resp.status_code == 200, resp.text
        saved = resp.json()["questions"][0]
        assert (saved["question_type"], saved["min_words"], saved["points"]) == ("essay", 50, 5)

    def test_a_stranger_cannot_save_someone_elses_question(self, client: TestClient, db: Session, student):
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id)
        question = quiz["questions"][0]
        db.query(Course).filter(Course.id == "course-whole-q").update({"created_by": STUDENT_ID})
        db.commit()

        resp = client.put(f"/api/v1/quizzes/questions/{question['id']}", json=_whole(question, points=9))

        assert resp.status_code == 403, resp.text
        assert db.query(QuizQuestion).filter(QuizQuestion.id == uuid.UUID(question["id"])).one().points == 2

    def test_a_missing_question_is_a_404(self, client: TestClient, db: Session):
        _seed_chapter(db)
        resp = client.put(
            f"/api/v1/quizzes/questions/{uuid.uuid4()}",
            json={"question_text": "нет такого", "question_type": "essay", "options": []},
        )
        assert resp.status_code == 404, resp.text


class TestThePerRowRoutesRefuseAnUnanswerableResult:
    def test_the_only_right_answer_cannot_be_unmarked(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id)
        question = quiz["questions"][0]
        right = question["options"][0]

        resp = client.patch(f"/api/v1/quizzes/options/{right['id']}", json={"is_correct": False})

        assert resp.status_code == 422, resp.text
        assert {e["type"] for e in resp.json()["detail"]} == {"quiz_no_correct_option"}
        assert _correct_ids(db, question["id"]) == {right["id"]}

    def test_a_second_right_answer_cannot_be_marked(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id)
        question = quiz["questions"][0]
        wrong = question["options"][1]

        resp = client.patch(f"/api/v1/quizzes/options/{wrong['id']}", json={"is_correct": True})

        assert resp.status_code == 422, resp.text
        assert {e["type"] for e in resp.json()["detail"]} == {"quiz_many_correct_options"}
        assert _correct_ids(db, question["id"]) == {question["options"][0]["id"]}

    def test_a_written_question_cannot_become_a_choice_with_no_options(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id, question_type="short_answer")
        question = quiz["questions"][0]

        resp = client.patch(f"/api/v1/quizzes/questions/{question['id']}", json={"question_type": "multiple_choice"})

        assert resp.status_code == 422, resp.text
        assert {e["type"] for e in resp.json()["detail"]} == {"quiz_too_few_options"}
        assert db.query(QuizQuestion).filter(QuizQuestion.id == uuid.UUID(question["id"])).one().question_type == (
            "short_answer"
        )

    def test_a_choice_question_cannot_become_an_essay_over_its_options(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id)
        question = quiz["questions"][0]

        resp = client.patch(f"/api/v1/quizzes/questions/{question['id']}", json={"question_type": "essay"})

        assert resp.status_code == 422, resp.text
        assert {e["type"] for e in resp.json()["detail"]} == {"quiz_options_not_allowed"}

    def test_a_wording_fix_on_one_option_still_goes_through(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        quiz = _make_quiz(client, chapter_id)
        wrong = quiz["questions"][0]["options"][1]

        resp = client.patch(f"/api/v1/quizzes/options/{wrong['id']}", json={"option_text": "Никто другой"})

        assert resp.status_code == 200, resp.text
        assert _active_text(db, "quiz_option", wrong["id"], "option_text") == "Никто другой"
