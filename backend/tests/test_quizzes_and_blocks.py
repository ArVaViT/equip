"""Comprehensive tests for Quiz and Block endpoints."""

import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.chapter_block import ChapterBlock
from app.models.content_translation import ContentTranslation
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizAttempt, QuizOption, QuizQuestion
from app.models.user import User, UserRole
from tests.conftest import STUDENT_ID, TEACHER_ID

# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_course(db: Session):
    """Create a published course -> module -> chapter graph (no enrollment)."""
    course = Course(
        id="course-1",
        title="Test Course",
        created_by=TEACHER_ID,
        status="published",
    )
    module = Module(
        id="mod-1",
        course_id="course-1",
        title="Module 1",
        order_index=0,
    )
    chapter = Chapter(
        id="ch-1",
        module_id="mod-1",
        title="Chapter 1",
        order_index=0,
        chapter_type="quiz",
    )
    db.add_all([course, module, chapter])
    db.commit()
    return course, module, chapter


def _seed_course_with_enrollment(db: Session):
    """Create a published course -> module -> chapter with student enrollment."""
    course, module, chapter = _seed_course(db)
    existing = db.query(User).filter(User.id == STUDENT_ID).first()
    if not existing:
        db.add(User(id=STUDENT_ID, email="student@example.com", full_name="Test Student", role=UserRole.STUDENT.value))
        db.commit()
    enrollment = Enrollment(
        id="enroll-1",
        user_id=STUDENT_ID,
        course_id="course-1",
        progress=0,
    )
    db.add(enrollment)
    db.commit()
    return course, module, chapter


def _seed_quiz_with_questions(db: Session, chapter_id: str = "ch-1"):
    """Create a quiz with two MC questions, each with two options (one correct)."""
    quiz_id = uuid.uuid4()
    quiz = Quiz(
        id=quiz_id,
        chapter_id=chapter_id,
        title="Test Quiz",
        description="A quiz for testing",
        quiz_type="quiz",
        max_attempts=3,
        passing_score=50,
    )
    db.add(quiz)
    db.flush()

    q1_id, q2_id = uuid.uuid4(), uuid.uuid4()
    q1 = QuizQuestion(
        id=q1_id,
        quiz_id=quiz_id,
        question_text="What is 2+2?",
        question_type="multiple_choice",
        order_index=0,
        points=1,
    )
    q2 = QuizQuestion(
        id=q2_id,
        quiz_id=quiz_id,
        question_text="Capital of France?",
        question_type="multiple_choice",
        order_index=1,
        points=1,
    )
    db.add_all([q1, q2])
    db.flush()

    o1_wrong, o1_right = uuid.uuid4(), uuid.uuid4()
    o2_wrong, o2_right = uuid.uuid4(), uuid.uuid4()
    db.add_all(
        [
            QuizOption(id=o1_wrong, question_id=q1_id, option_text="3", is_correct=False, order_index=0),
            QuizOption(id=o1_right, question_id=q1_id, option_text="4", is_correct=True, order_index=1),
            QuizOption(id=o2_wrong, question_id=q2_id, option_text="London", is_correct=False, order_index=0),
            QuizOption(id=o2_right, question_id=q2_id, option_text="Paris", is_correct=True, order_index=1),
        ]
    )
    db.commit()

    opts = {
        "q1_correct": o1_right,
        "q1_wrong": o1_wrong,
        "q2_correct": o2_right,
        "q2_wrong": o2_wrong,
    }
    return quiz, [q1, q2], opts


# ═══════════════════════════════════════════════════════════════════════════
#  BLOCK TESTS
# ═══════════════════════════════════════════════════════════════════════════


# ── GET /api/v1/blocks/chapter/{chapter_id} ──────────────────────────────


def test_list_blocks_teacher_success(client: TestClient, db: Session):
    _seed_course(db)
    db.add(ChapterBlock(chapter_id="ch-1", block_type="text", order_index=0, content="Hello"))
    db.commit()

    resp = client.get("/api/v1/blocks/chapter/ch-1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["content"] == "Hello"
    assert data[0]["block_type"] == "text"


def test_list_blocks_enrolled_student(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    db.add(ChapterBlock(chapter_id="ch-1", block_type="text", order_index=0, content="Lesson"))
    db.commit()

    resp = student_client.get("/api/v1/blocks/chapter/ch-1")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_blocks_returns_ordered(client: TestClient, db: Session):
    _seed_course(db)
    db.add_all(
        [
            ChapterBlock(chapter_id="ch-1", block_type="text", order_index=2, content="Second"),
            ChapterBlock(chapter_id="ch-1", block_type="text", order_index=0, content="First"),
        ]
    )
    db.commit()

    data = client.get("/api/v1/blocks/chapter/ch-1").json()
    assert data[0]["content"] == "First"
    assert data[1]["content"] == "Second"


def test_list_blocks_empty(client: TestClient, db: Session):
    _seed_course(db)
    resp = client.get("/api/v1/blocks/chapter/ch-1")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_blocks_chapter_not_found(client: TestClient, db: Session):
    resp = client.get("/api/v1/blocks/chapter/nonexistent")
    assert resp.status_code == 404


def test_list_blocks_anon_unauthorized(anon_client: TestClient):
    resp = anon_client.get("/api/v1/blocks/chapter/ch-1")
    assert resp.status_code == 401


# ── GET /api/v1/blocks/chapter/{chapter_id}?source=1 (editor escape hatch) ──


def _seed_block_with_en_translation(db: Session):
    """Seed a chapter block with RU content and an EN translation overlay."""
    block = ChapterBlock(
        chapter_id="ch-1",
        block_type="text",
        order_index=0,
        content="Русский контент",
    )
    db.add(block)
    db.flush()
    db.add(
        ContentTranslation(
            entity_type="chapter_block",
            entity_id=str(block.id),
            field="content",
            locale="en",
            text="<p>English content</p>",
            source_hash="bh1",
            status="ok",
            origin="mt",
        )
    )
    db.commit()
    return block


def test_list_blocks_source_param_returns_raw_for_owner(client: TestClient, db: Session):
    """Editor path: teacher in EN UI editing their RU course must see the
    source HTML (or PATCH would overwrite ``content`` with the EN translation)."""
    _seed_course(db)
    _seed_block_with_en_translation(db)

    resp = client.get(
        "/api/v1/blocks/chapter/ch-1",
        params={"source": "1"},
        headers={"Accept-Language": "en"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["content"] == "Русский контент"


def test_list_blocks_source_param_returns_raw_for_admin(admin_client: TestClient, db: Session):
    _seed_course(db)
    _seed_block_with_en_translation(db)

    resp = admin_client.get(
        "/api/v1/blocks/chapter/ch-1",
        params={"source": "1"},
        headers={"Accept-Language": "en"},
    )
    assert resp.status_code == 200
    assert resp.json()[0]["content"] == "Русский контент"


def test_list_blocks_source_param_403_for_enrolled_student(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    _seed_block_with_en_translation(db)

    resp = student_client.get(
        "/api/v1/blocks/chapter/ch-1",
        params={"source": "1"},
        headers={"Accept-Language": "en"},
    )
    assert resp.status_code == 403


# ── POST /api/v1/blocks/chapter/{chapter_id} ─────────────────────────────


def test_create_block_text(client: TestClient, db: Session):
    _seed_course(db)
    resp = client.post(
        "/api/v1/blocks/chapter/ch-1",
        json={
            "block_type": "text",
            "order_index": 0,
            "content": "New block content",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["block_type"] == "text"
    assert body["content"] == "New block content"
    assert body["chapter_id"] == "ch-1"


def test_create_block_file(client: TestClient, db: Session):
    _seed_course(db)
    resp = client.post(
        "/api/v1/blocks/chapter/ch-1",
        json={
            "block_type": "file",
            "order_index": 1,
            "file_bucket": "course-materials",
            "file_path": "ch-1/1745000000-handout.pdf",
            "file_name": "handout.pdf",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["file_bucket"] == "course-materials"
    assert body["file_path"] == "ch-1/1745000000-handout.pdf"
    assert body["file_name"] == "handout.pdf"


def test_create_block_student_forbidden(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    resp = student_client.post(
        "/api/v1/blocks/chapter/ch-1",
        json={
            "block_type": "text",
            "order_index": 0,
            "content": "nope",
        },
    )
    assert resp.status_code == 403


def test_create_block_anon_unauthorized(anon_client: TestClient):
    resp = anon_client.post(
        "/api/v1/blocks/chapter/ch-1",
        json={
            "block_type": "text",
            "order_index": 0,
        },
    )
    assert resp.status_code == 401


def test_create_block_chapter_not_found(client: TestClient, db: Session):
    resp = client.post(
        "/api/v1/blocks/chapter/nonexistent",
        json={
            "block_type": "text",
            "order_index": 0,
        },
    )
    assert resp.status_code == 404


# ── PUT /api/v1/blocks/{block_id} ────────────────────────────────────────


def test_update_block_success(client: TestClient, db: Session):
    _seed_course(db)
    block = ChapterBlock(chapter_id="ch-1", block_type="text", order_index=0, content="Old")
    db.add(block)
    db.commit()
    db.refresh(block)

    resp = client.put(f"/api/v1/blocks/{block.id}", json={"content": "Updated"})
    assert resp.status_code == 200
    assert resp.json()["content"] == "Updated"


def test_update_block_partial(client: TestClient, db: Session):
    _seed_course(db)
    block = ChapterBlock(chapter_id="ch-1", block_type="text", order_index=0, content="Keep")
    db.add(block)
    db.commit()
    db.refresh(block)

    resp = client.put(f"/api/v1/blocks/{block.id}", json={"order_index": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["order_index"] == 5
    assert body["content"] == "Keep"


def test_update_block_student_forbidden(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    block = ChapterBlock(chapter_id="ch-1", block_type="text", order_index=0)
    db.add(block)
    db.commit()
    db.refresh(block)

    resp = student_client.put(f"/api/v1/blocks/{block.id}", json={"content": "hack"})
    assert resp.status_code == 403


def test_update_block_not_found(client: TestClient, db: Session):
    resp = client.put(f"/api/v1/blocks/{uuid.uuid4()}", json={"content": "nope"})
    assert resp.status_code == 404


def test_update_block_anon_unauthorized(anon_client: TestClient):
    resp = anon_client.put(f"/api/v1/blocks/{uuid.uuid4()}", json={"content": "x"})
    assert resp.status_code == 401


def test_create_block_sanitizes_html_server_side(client: TestClient, db: Session):
    """A direct API caller bypasses the frontend's DOMPurify. The server
    must still strip ``<script>`` and event handlers before persisting."""
    _seed_course(db)
    malicious = "<p>ok</p><script>alert('xss')</script><img src=x onerror=alert(1)>"
    resp = client.post(
        "/api/v1/blocks/chapter/ch-1",
        json={"block_type": "text", "order_index": 0, "content": malicious},
    )
    assert resp.status_code == 201
    stored = resp.json()["content"]
    assert "<script>" not in stored
    assert "onerror" not in stored
    assert "<p>ok</p>" in stored


# ── DELETE /api/v1/blocks/{block_id} ──────────────────────────────────────


def test_delete_block_success(client: TestClient, db: Session):
    _seed_course(db)
    block = ChapterBlock(chapter_id="ch-1", block_type="text", order_index=0, content="Bye")
    db.add(block)
    db.commit()
    db.refresh(block)

    resp = client.delete(f"/api/v1/blocks/{block.id}")
    assert resp.status_code == 204
    assert db.query(ChapterBlock).filter(ChapterBlock.id == block.id).first() is None


def test_delete_block_student_forbidden(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    block = ChapterBlock(chapter_id="ch-1", block_type="text", order_index=0)
    db.add(block)
    db.commit()
    db.refresh(block)

    resp = student_client.delete(f"/api/v1/blocks/{block.id}")
    assert resp.status_code == 403


def test_delete_block_not_found(client: TestClient, db: Session):
    resp = client.delete(f"/api/v1/blocks/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_delete_block_anon_unauthorized(anon_client: TestClient):
    resp = anon_client.delete(f"/api/v1/blocks/{uuid.uuid4()}")
    assert resp.status_code == 401


# ── PUT /api/v1/blocks/chapter/{chapter_id}/reorder ───────────────────────


def test_reorder_blocks_success(client: TestClient, db: Session):
    _seed_course(db)
    b1 = ChapterBlock(chapter_id="ch-1", block_type="text", order_index=0, content="A")
    b2 = ChapterBlock(chapter_id="ch-1", block_type="text", order_index=1, content="B")
    db.add_all([b1, b2])
    db.commit()
    db.refresh(b1)
    db.refresh(b2)

    resp = client.put(
        "/api/v1/blocks/chapter/ch-1/reorder",
        json=[
            {"id": str(b1.id), "order_index": 1},
            {"id": str(b2.id), "order_index": 0},
        ],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["content"] == "B"
    assert data[1]["content"] == "A"


def test_reorder_blocks_empty_list(client: TestClient, db: Session):
    _seed_course(db)
    resp = client.put("/api/v1/blocks/chapter/ch-1/reorder", json=[])
    assert resp.status_code == 200
    assert resp.json() == []


def test_reorder_blocks_student_forbidden(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    resp = student_client.put("/api/v1/blocks/chapter/ch-1/reorder", json=[])
    assert resp.status_code == 403


def test_reorder_blocks_chapter_not_found(client: TestClient, db: Session):
    resp = client.put("/api/v1/blocks/chapter/nonexistent/reorder", json=[])
    assert resp.status_code == 404


def test_reorder_blocks_anon_unauthorized(anon_client: TestClient):
    resp = anon_client.put("/api/v1/blocks/chapter/ch-1/reorder", json=[])
    assert resp.status_code == 401


def test_reorder_blocks_unknown_id_returns_400(client: TestClient, db: Session):
    # Previous behaviour: a payload referencing a block id that doesn't
    # belong to this chapter (or no longer exists) silently dropped the
    # offending item and committed a partial reorder. Now we reject the
    # whole reorder so the teacher's drag-and-drop view stays in sync
    # with what's persisted.
    import uuid as _uuid

    _seed_course(db)
    b1 = ChapterBlock(chapter_id="ch-1", block_type="text", order_index=0, content="A")
    db.add(b1)
    db.commit()
    db.refresh(b1)
    bogus = str(_uuid.uuid4())
    resp = client.put(
        "/api/v1/blocks/chapter/ch-1/reorder",
        json=[
            {"id": str(b1.id), "order_index": 1},
            {"id": bogus, "order_index": 0},
        ],
    )
    assert resp.status_code == 400
    assert bogus in resp.json()["detail"]
    # And the existing block's order MUST NOT have shifted: the whole
    # reorder is rejected, not partially applied.
    db.refresh(b1)
    assert b1.order_index == 0


# ═══════════════════════════════════════════════════════════════════════════
#  QUIZ TESTS
# ═══════════════════════════════════════════════════════════════════════════


# ── GET /api/v1/quizzes/chapter/{chapter_id} (student view) ──────────────


def test_get_chapter_quiz_enrolled_student(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    _seed_quiz_with_questions(db)

    resp = student_client.get("/api/v1/quizzes/chapter/ch-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Test Quiz"
    assert len(data["questions"]) == 2
    for q in data["questions"]:
        for opt in q["options"]:
            assert "is_correct" not in opt


def test_get_chapter_quiz_teacher_owner(client: TestClient, db: Session):
    _seed_course(db)
    _seed_quiz_with_questions(db)

    resp = client.get("/api/v1/quizzes/chapter/ch-1")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Test Quiz"


def test_get_chapter_quiz_none_exists(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    resp = student_client.get("/api/v1/quizzes/chapter/ch-1")
    assert resp.status_code == 200
    assert resp.json() is None


def test_get_chapter_quiz_chapter_not_found(student_client: TestClient, db: Session):
    resp = student_client.get("/api/v1/quizzes/chapter/nonexistent")
    assert resp.status_code == 404


def test_get_chapter_quiz_anon_unauthorized(anon_client: TestClient):
    resp = anon_client.get("/api/v1/quizzes/chapter/ch-1")
    assert resp.status_code == 401


# ── GET /api/v1/quizzes/chapter/{chapter_id}?source=1 (editor escape hatch) ──


def _seed_quiz_with_en_translations(db: Session):
    """Seed an RU-source quiz plus an EN ``content_translations`` overlay."""
    quiz, questions, _opts = _seed_quiz_with_questions(db)
    q1, q2 = questions
    quiz.title = "RU тест"
    quiz.description = "Описание"
    q1.question_text = "Вопрос 1"
    q2.question_text = "Вопрос 2"
    db.add(
        ContentTranslation(
            entity_type="quiz",
            entity_id=str(quiz.id),
            field="title",
            locale="en",
            text="EN quiz title",
            source_hash="qh1",
            status="ok",
            origin="mt",
        )
    )
    db.add(
        ContentTranslation(
            entity_type="quiz_question",
            entity_id=str(q1.id),
            field="question_text",
            locale="en",
            text="EN question 1",
            source_hash="qh2",
            status="ok",
            origin="mt",
        )
    )
    db.commit()
    return quiz, q1, q2


def test_get_chapter_quiz_source_param_returns_raw_for_owner(client: TestClient, db: Session):
    """``?source=1`` returns source columns even with ``Accept-Language: en``,
    so a teacher in EN UI can't accidentally save the EN translation back to
    the source ``question_text``."""
    _seed_course(db)
    _seed_quiz_with_en_translations(db)

    resp = client.get(
        "/api/v1/quizzes/chapter/ch-1",
        params={"source": "1"},
        headers={"Accept-Language": "en"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "RU тест"
    questions = sorted(body["questions"], key=lambda q: q["order_index"])
    assert questions[0]["question_text"] == "Вопрос 1"


def test_get_chapter_quiz_source_param_returns_raw_for_admin(admin_client: TestClient, db: Session):
    _seed_course(db)
    _seed_quiz_with_en_translations(db)

    resp = admin_client.get(
        "/api/v1/quizzes/chapter/ch-1",
        params={"source": "1"},
        headers={"Accept-Language": "en"},
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "RU тест"


def test_get_chapter_quiz_source_param_403_for_enrolled_student(student_client: TestClient, db: Session):
    """Source content (typos, unredacted teacher drafts) shouldn't leak to
    students. Even an enrolled student gets 403 — fail loudly so frontend
    bugs surface immediately."""
    _seed_course_with_enrollment(db)
    _seed_quiz_with_en_translations(db)

    resp = student_client.get(
        "/api/v1/quizzes/chapter/ch-1",
        params={"source": "1"},
        headers={"Accept-Language": "en"},
    )
    assert resp.status_code == 403


# ── GET /api/v1/quizzes/{quiz_id} (teacher detail) ──────────────────────


def test_get_quiz_detail_teacher(client: TestClient, db: Session):
    _seed_course(db)
    quiz, _, _ = _seed_quiz_with_questions(db)

    resp = client.get(f"/api/v1/quizzes/{quiz.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Test Quiz"
    assert len(data["questions"]) == 2
    for q in data["questions"]:
        for opt in q["options"]:
            assert "is_correct" in opt


def test_get_quiz_detail_student_forbidden(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    quiz, _, _ = _seed_quiz_with_questions(db)

    resp = student_client.get(f"/api/v1/quizzes/{quiz.id}")
    assert resp.status_code == 403


def test_get_quiz_detail_not_found(client: TestClient, db: Session):
    resp = client.get(f"/api/v1/quizzes/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_get_quiz_detail_anon_unauthorized(anon_client: TestClient):
    resp = anon_client.get(f"/api/v1/quizzes/{uuid.uuid4()}")
    assert resp.status_code == 401


# ── POST /api/v1/quizzes (create) ────────────────────────────────────────


def test_create_quiz_with_questions(client: TestClient, db: Session):
    _seed_course(db)
    resp = client.post(
        "/api/v1/quizzes",
        json={
            "chapter_id": "ch-1",
            "title": "New Quiz",
            "description": "Testing creation",
            "quiz_type": "quiz",
            "max_attempts": 5,
            "passing_score": 60,
            "questions": [
                {
                    "question_text": "Sky color?",
                    "question_type": "multiple_choice",
                    "order_index": 0,
                    "points": 1,
                    "options": [
                        {"option_text": "Blue", "is_correct": True, "order_index": 0},
                        {"option_text": "Red", "is_correct": False, "order_index": 1},
                    ],
                }
            ],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "New Quiz"
    assert body["passing_score"] == 60
    assert len(body["questions"]) == 1
    assert len(body["questions"][0]["options"]) == 2


def test_create_quiz_exam_auto_max_attempts(client: TestClient, db: Session):
    _seed_course(db)
    resp = client.post(
        "/api/v1/quizzes",
        json={
            "chapter_id": "ch-1",
            "title": "Final Exam",
            "quiz_type": "exam",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["max_attempts"] == 1


def test_create_quiz_no_questions(client: TestClient, db: Session):
    _seed_course(db)
    resp = client.post(
        "/api/v1/quizzes",
        json={
            "chapter_id": "ch-1",
            "title": "Empty Quiz",
        },
    )
    assert resp.status_code == 201
    assert resp.json()["questions"] == []


def test_create_quiz_student_forbidden(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    resp = student_client.post(
        "/api/v1/quizzes",
        json={
            "chapter_id": "ch-1",
            "title": "No way",
        },
    )
    assert resp.status_code == 403


def test_create_quiz_chapter_not_found(client: TestClient, db: Session):
    resp = client.post(
        "/api/v1/quizzes",
        json={
            "chapter_id": "nonexistent",
            "title": "Orphan Quiz",
        },
    )
    assert resp.status_code == 404


def test_create_quiz_anon_unauthorized(anon_client: TestClient):
    resp = anon_client.post(
        "/api/v1/quizzes",
        json={
            "chapter_id": "ch-1",
            "title": "x",
        },
    )
    assert resp.status_code == 401


# ── PUT /api/v1/quizzes/{quiz_id} (update) ───────────────────────────────


def test_update_quiz_success(client: TestClient, db: Session):
    _seed_course(db)
    quiz, _, _ = _seed_quiz_with_questions(db)

    resp = client.put(
        f"/api/v1/quizzes/{quiz.id}",
        json={
            "title": "Updated Title",
            "passing_score": 80,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Updated Title"
    assert body["passing_score"] == 80


def test_update_quiz_to_exam_sets_max_attempts(client: TestClient, db: Session):
    _seed_course(db)
    quiz, _, _ = _seed_quiz_with_questions(db)
    quiz.max_attempts = None
    db.commit()

    resp = client.put(f"/api/v1/quizzes/{quiz.id}", json={"quiz_type": "exam"})
    assert resp.status_code == 200
    assert resp.json()["max_attempts"] == 1


def test_update_quiz_student_forbidden(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    quiz, _, _ = _seed_quiz_with_questions(db)

    resp = student_client.put(f"/api/v1/quizzes/{quiz.id}", json={"title": "Hack"})
    assert resp.status_code == 403


def test_update_quiz_not_found(client: TestClient, db: Session):
    resp = client.put(f"/api/v1/quizzes/{uuid.uuid4()}", json={"title": "Ghost"})
    assert resp.status_code == 404


def test_update_quiz_anon_unauthorized(anon_client: TestClient):
    resp = anon_client.put(f"/api/v1/quizzes/{uuid.uuid4()}", json={"title": "x"})
    assert resp.status_code == 401


# ── DELETE /api/v1/quizzes/{quiz_id} ──────────────────────────────────────


def test_delete_quiz_success(client: TestClient, db: Session):
    _seed_course(db)
    quiz, _, _ = _seed_quiz_with_questions(db)

    resp = client.delete(f"/api/v1/quizzes/{quiz.id}")
    assert resp.status_code == 204
    assert db.query(Quiz).filter(Quiz.id == quiz.id).first() is None


def test_delete_quiz_student_forbidden(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    quiz, _, _ = _seed_quiz_with_questions(db)

    resp = student_client.delete(f"/api/v1/quizzes/{quiz.id}")
    assert resp.status_code == 403


def test_delete_quiz_not_found(client: TestClient, db: Session):
    resp = client.delete(f"/api/v1/quizzes/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_delete_quiz_anon_unauthorized(anon_client: TestClient):
    resp = anon_client.delete(f"/api/v1/quizzes/{uuid.uuid4()}")
    assert resp.status_code == 401


# ── POST /api/v1/quizzes/{quiz_id}/submit ─────────────────────────────────


def test_submit_quiz_survives_concurrent_chapter_progress_insert(student_client: TestClient, db: Session):
    """``submit_quiz`` upserts a ChapterProgress row when the student
    passes. A teacher manually marking the chapter complete (or a
    parallel quiz submission) at the same instant can race the INSERT,
    tripping the ``uq_progress_user_chapter`` unique key. Before the
    SAVEPOINT wrap in ``upsert_passed_chapter_progress`` this took
    down the whole submit transaction.
    """
    from sqlalchemy.orm import Query

    from app.models.chapter_progress import ChapterProgress

    _seed_course_with_enrollment(db)
    quiz, questions, opts = _seed_quiz_with_questions(db)

    db.add(
        ChapterProgress(
            user_id=STUDENT_ID,
            chapter_id="ch-1",
            completed=True,
            completion_type="teacher",
        )
    )
    db.commit()

    real_first = Query.first
    state = {"missed": False}

    def _maybe_miss(self):
        descs = self.column_descriptions
        if not state["missed"] and descs and getattr(descs[0].get("type"), "__name__", "") == "ChapterProgress":
            state["missed"] = True
            return None
        return real_first(self)

    Query.first = _maybe_miss
    try:
        resp = student_client.post(
            f"/api/v1/quizzes/{quiz.id}/submit",
            json={
                "answers": [
                    {
                        "question_id": str(questions[0].id),
                        "selected_option_id": str(opts["q1_correct"]),
                    },
                    {
                        "question_id": str(questions[1].id),
                        "selected_option_id": str(opts["q2_correct"]),
                    },
                ],
            },
        )
    finally:
        Query.first = real_first

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["passed"] is True

    db.expire_all()
    progress_rows = (
        db.query(ChapterProgress)
        .filter(
            ChapterProgress.user_id == STUDENT_ID,
            ChapterProgress.chapter_id == "ch-1",
        )
        .all()
    )
    assert len(progress_rows) == 1
    assert progress_rows[0].completed is True


def test_submit_quiz_perfect_score(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    quiz, questions, opts = _seed_quiz_with_questions(db)

    resp = student_client.post(
        f"/api/v1/quizzes/{quiz.id}/submit",
        json={
            "answers": [
                {"question_id": str(questions[0].id), "selected_option_id": str(opts["q1_correct"])},
                {"question_id": str(questions[1].id), "selected_option_id": str(opts["q2_correct"])},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["score"] == 2
    assert body["max_score"] == 2
    assert body["passed"] is True
    assert body["user_id"] == str(STUDENT_ID)


def test_submit_quiz_all_wrong(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    quiz, questions, opts = _seed_quiz_with_questions(db)

    resp = student_client.post(
        f"/api/v1/quizzes/{quiz.id}/submit",
        json={
            "answers": [
                {"question_id": str(questions[0].id), "selected_option_id": str(opts["q1_wrong"])},
                {"question_id": str(questions[1].id), "selected_option_id": str(opts["q2_wrong"])},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["score"] == 0
    assert body["passed"] is False


def test_submit_quiz_empty_answers_rejected(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    quiz, _, _ = _seed_quiz_with_questions(db)

    resp = student_client.post(f"/api/v1/quizzes/{quiz.id}/submit", json={"answers": []})
    assert resp.status_code == 422


def test_submit_quiz_partial_answers(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    quiz, questions, opts = _seed_quiz_with_questions(db)

    resp = student_client.post(
        f"/api/v1/quizzes/{quiz.id}/submit",
        json={
            "answers": [
                {"question_id": str(questions[0].id), "selected_option_id": str(opts["q1_correct"])},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["score"] == 1
    assert body["max_score"] == 2
    assert body["passed"] is True  # 50% >= 50 passing_score


def test_submit_quiz_not_enrolled(client: TestClient, db: Session):
    """Teacher owns the course but is not enrolled — should be rejected."""
    _seed_course(db)
    quiz, questions, opts = _seed_quiz_with_questions(db)

    resp = client.post(
        f"/api/v1/quizzes/{quiz.id}/submit",
        json={
            "answers": [
                {"question_id": str(questions[0].id), "selected_option_id": str(opts["q1_correct"])},
            ],
        },
    )
    assert resp.status_code == 403
    assert "enrolled" in resp.json()["detail"].lower()


def test_submit_quiz_not_found(student_client: TestClient, db: Session):
    fake_qid = uuid.uuid4()
    resp = student_client.post(
        f"/api/v1/quizzes/{fake_qid}/submit",
        json={"answers": [{"question_id": str(uuid.uuid4()), "selected_option_id": str(uuid.uuid4())}]},
    )
    assert resp.status_code == 404


def test_submit_quiz_max_attempts_exceeded(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    quiz, questions, opts = _seed_quiz_with_questions(db)
    quiz.max_attempts = 1
    db.commit()

    first = student_client.post(
        f"/api/v1/quizzes/{quiz.id}/submit",
        json={
            "answers": [
                {"question_id": str(questions[0].id), "selected_option_id": str(opts["q1_correct"])},
            ],
        },
    )
    assert first.status_code == 200

    second = student_client.post(
        f"/api/v1/quizzes/{quiz.id}/submit",
        json={
            "answers": [
                {"question_id": str(questions[0].id), "selected_option_id": str(opts["q1_correct"])},
            ],
        },
    )
    assert second.status_code == 403
    assert "attempts" in second.json()["detail"].lower()


def test_submit_quiz_extra_attempts_extend_limit(student_client: TestClient, db: Session):
    """After exhausting base attempts, extra-attempt grant should allow more."""
    from app.models.quiz import QuizExtraAttempt

    _seed_course_with_enrollment(db)
    quiz, questions, opts = _seed_quiz_with_questions(db)
    quiz.max_attempts = 1
    db.commit()

    student_client.post(
        f"/api/v1/quizzes/{quiz.id}/submit",
        json={
            "answers": [{"question_id": str(questions[0].id), "selected_option_id": str(opts["q1_wrong"])}],
        },
    )

    blocked = student_client.post(
        f"/api/v1/quizzes/{quiz.id}/submit",
        json={
            "answers": [{"question_id": str(questions[0].id), "selected_option_id": str(opts["q1_correct"])}],
        },
    )
    assert blocked.status_code == 403

    db.add(
        QuizExtraAttempt(
            quiz_id=quiz.id,
            user_id=STUDENT_ID,
            extra_attempts=1,
            granted_by=TEACHER_ID,
        )
    )
    db.commit()

    retry = student_client.post(
        f"/api/v1/quizzes/{quiz.id}/submit",
        json={
            "answers": [{"question_id": str(questions[0].id), "selected_option_id": str(opts["q1_correct"])}],
        },
    )
    assert retry.status_code == 200


def test_submit_quiz_anon_unauthorized(anon_client: TestClient):
    resp = anon_client.post(f"/api/v1/quizzes/{uuid.uuid4()}/submit", json={"answers": []})
    assert resp.status_code == 401


# ── GET /api/v1/quizzes/{quiz_id}/attempts (teacher) ─────────────────────


def test_get_all_attempts_teacher(client: TestClient, student, db: Session):
    _seed_course(db)
    quiz, _, _ = _seed_quiz_with_questions(db)
    db.add(QuizAttempt(quiz_id=quiz.id, user_id=student.id, score=2, max_score=2, passed=True))
    db.commit()

    resp = client.get(f"/api/v1/quizzes/{quiz.id}/attempts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["user_id"] == str(STUDENT_ID)


def test_get_all_attempts_empty(client: TestClient, db: Session):
    _seed_course(db)
    quiz, _, _ = _seed_quiz_with_questions(db)

    resp = client.get(f"/api/v1/quizzes/{quiz.id}/attempts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_all_attempts_student_forbidden(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    quiz, _, _ = _seed_quiz_with_questions(db)

    resp = student_client.get(f"/api/v1/quizzes/{quiz.id}/attempts")
    assert resp.status_code == 403


def test_get_all_attempts_not_found(client: TestClient, db: Session):
    resp = client.get(f"/api/v1/quizzes/{uuid.uuid4()}/attempts")
    assert resp.status_code == 404


def test_get_all_attempts_anon_unauthorized(anon_client: TestClient):
    resp = anon_client.get(f"/api/v1/quizzes/{uuid.uuid4()}/attempts")
    assert resp.status_code == 401


# ── GET /api/v1/quizzes/{quiz_id}/my-attempts (student) ──────────────────


def test_get_my_attempts_after_submit(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    quiz, questions, opts = _seed_quiz_with_questions(db)

    student_client.post(
        f"/api/v1/quizzes/{quiz.id}/submit",
        json={
            "answers": [
                {"question_id": str(questions[0].id), "selected_option_id": str(opts["q1_correct"])},
            ],
        },
    )

    resp = student_client.get(f"/api/v1/quizzes/{quiz.id}/my-attempts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["user_id"] == str(STUDENT_ID)


def test_get_my_attempts_empty(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    quiz, _, _ = _seed_quiz_with_questions(db)

    resp = student_client.get(f"/api/v1/quizzes/{quiz.id}/my-attempts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_my_attempts_teacher_sees_own(client: TestClient, db: Session):
    """Teacher can also call my-attempts; result is empty because they never submitted."""
    _seed_course(db)
    quiz, _, _ = _seed_quiz_with_questions(db)

    resp = client.get(f"/api/v1/quizzes/{quiz.id}/my-attempts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_my_attempts_anon_unauthorized(anon_client: TestClient):
    resp = anon_client.get(f"/api/v1/quizzes/{uuid.uuid4()}/my-attempts")
    assert resp.status_code == 401


# ── POST /api/v1/quizzes/{quiz_id}/extra-attempts (grant) ────────────────


def test_grant_extra_attempts_success(client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    quiz, _, _ = _seed_quiz_with_questions(db)

    resp = client.post(
        f"/api/v1/quizzes/{quiz.id}/extra-attempts",
        json={
            "user_id": str(STUDENT_ID),
            "extra_attempts": 3,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["extra_attempts"] == 3
    assert body["user_id"] == str(STUDENT_ID)
    assert body["granted_by"] == str(TEACHER_ID)


def test_grant_extra_attempts_updates_existing(client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    quiz, _, _ = _seed_quiz_with_questions(db)

    client.post(
        f"/api/v1/quizzes/{quiz.id}/extra-attempts",
        json={
            "user_id": str(STUDENT_ID),
            "extra_attempts": 2,
        },
    )
    resp = client.post(
        f"/api/v1/quizzes/{quiz.id}/extra-attempts",
        json={
            "user_id": str(STUDENT_ID),
            "extra_attempts": 5,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["extra_attempts"] == 5


def test_grant_extra_attempts_student_forbidden(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    quiz, _, _ = _seed_quiz_with_questions(db)

    resp = student_client.post(
        f"/api/v1/quizzes/{quiz.id}/extra-attempts",
        json={
            "user_id": str(STUDENT_ID),
            "extra_attempts": 1,
        },
    )
    assert resp.status_code == 403


def test_grant_extra_attempts_quiz_not_found(client: TestClient, db: Session):
    resp = client.post(
        f"/api/v1/quizzes/{uuid.uuid4()}/extra-attempts",
        json={
            "user_id": str(STUDENT_ID),
            "extra_attempts": 1,
        },
    )
    assert resp.status_code == 404


def test_grant_extra_attempts_anon_unauthorized(anon_client: TestClient):
    resp = anon_client.post(
        f"/api/v1/quizzes/{uuid.uuid4()}/extra-attempts",
        json={
            "user_id": str(STUDENT_ID),
            "extra_attempts": 1,
        },
    )
    assert resp.status_code == 401


# ── GET /api/v1/quizzes/{quiz_id}/extra-attempts (list) ──────────────────


def test_list_extra_attempts_success(client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    quiz, _, _ = _seed_quiz_with_questions(db)

    client.post(
        f"/api/v1/quizzes/{quiz.id}/extra-attempts",
        json={
            "user_id": str(STUDENT_ID),
            "extra_attempts": 2,
        },
    )

    resp = client.get(f"/api/v1/quizzes/{quiz.id}/extra-attempts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["user_id"] == str(STUDENT_ID)
    assert data[0]["extra_attempts"] == 2


def test_list_extra_attempts_empty(client: TestClient, db: Session):
    _seed_course(db)
    quiz, _, _ = _seed_quiz_with_questions(db)

    resp = client.get(f"/api/v1/quizzes/{quiz.id}/extra-attempts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_extra_attempts_student_forbidden(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    quiz, _, _ = _seed_quiz_with_questions(db)

    resp = student_client.get(f"/api/v1/quizzes/{quiz.id}/extra-attempts")
    assert resp.status_code == 403


def test_list_extra_attempts_quiz_not_found(client: TestClient, db: Session):
    resp = client.get(f"/api/v1/quizzes/{uuid.uuid4()}/extra-attempts")
    assert resp.status_code == 404


def test_list_extra_attempts_anon_unauthorized(anon_client: TestClient):
    resp = anon_client.get(f"/api/v1/quizzes/{uuid.uuid4()}/extra-attempts")
    assert resp.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════
#  ESSAY + MANUAL GRADING
# ═══════════════════════════════════════════════════════════════════════════


def _seed_essay_quiz(db: Session):
    """Seed a mixed quiz: one 1-point MCQ + one 20-point essay, passing=70."""
    quiz_id = uuid.uuid4()
    quiz = Quiz(
        id=quiz_id,
        chapter_id="ch-1",
        title="Midterm",
        description="MCQ + essay",
        quiz_type="exam",
        max_attempts=2,
        passing_score=70,
    )
    db.add(quiz)
    db.flush()

    mcq_id, essay_id = uuid.uuid4(), uuid.uuid4()
    mcq = QuizQuestion(
        id=mcq_id,
        quiz_id=quiz_id,
        question_text="2+2?",
        question_type="multiple_choice",
        order_index=0,
        points=1,
    )
    essay = QuizQuestion(
        id=essay_id,
        quiz_id=quiz_id,
        question_text="Reflect on the book of Acts (≥300 words).",
        question_type="essay",
        order_index=1,
        points=20,
        min_words=300,
    )
    db.add_all([mcq, essay])
    db.flush()

    o_wrong, o_right = uuid.uuid4(), uuid.uuid4()
    db.add_all(
        [
            QuizOption(id=o_wrong, question_id=mcq_id, option_text="3", is_correct=False, order_index=0),
            QuizOption(id=o_right, question_id=mcq_id, option_text="4", is_correct=True, order_index=1),
        ]
    )
    db.commit()
    return quiz, mcq, essay, o_right


def test_create_essay_question_accepted(client: TestClient, db: Session):
    _seed_course(db)
    resp = client.post(
        "/api/v1/quizzes",
        json={
            "chapter_id": "ch-1",
            "title": "Essay exam",
            "quiz_type": "exam",
            "passing_score": 70,
            "questions": [
                {
                    "question_text": "Write a reflective essay on the book of Acts.",
                    "question_type": "essay",
                    "order_index": 0,
                    "points": 20,
                    "min_words": 400,
                }
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["questions"][0]["question_type"] == "essay"
    assert body["questions"][0]["min_words"] == 400


def test_submit_with_essay_does_not_auto_pass(student_client: TestClient, db: Session):
    """Essay points are *potential*; auto-score alone must not clear passing_score."""
    _seed_course_with_enrollment(db)
    quiz, mcq, essay, o_right = _seed_essay_quiz(db)

    resp = student_client.post(
        f"/api/v1/quizzes/{quiz.id}/submit",
        json={
            "answers": [
                {"question_id": str(mcq.id), "selected_option_id": str(o_right)},
                {"question_id": str(essay.id), "text_answer": "My reflection on the book of Acts…"},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    # 1/21 ≈ 4.8% < 70% passing. Essay counts toward max_score.
    assert body["score"] == 1
    assert body["max_score"] == 21
    assert body["passed"] is False


def _seed_submitted_essay_attempt(db: Session, *, essay_text: str = "A thoughtful essay."):
    """Insert a student attempt + answers for the seeded essay quiz directly.

    Bypasses the API (and therefore the test's auth override) so we can
    exercise the teacher-grading endpoints without having to juggle two
    different ``TestClient`` fixtures in the same test.
    """
    from app.models.quiz import QuizAnswer

    quiz, mcq, essay, o_right = _seed_essay_quiz(db)

    attempt = QuizAttempt(
        id=uuid.uuid4(),
        quiz_id=quiz.id,
        user_id=STUDENT_ID,
        score=1,
        max_score=1 + int(essay.points),
        passed=False,
        completed_at=_now_utc(),
    )
    db.add(attempt)
    db.flush()

    mcq_answer = QuizAnswer(
        id=uuid.uuid4(),
        attempt_id=attempt.id,
        question_id=mcq.id,
        selected_option_id=o_right,
        text_answer=None,
        is_correct=True,
        points_earned=1,
    )
    essay_answer = QuizAnswer(
        id=uuid.uuid4(),
        attempt_id=attempt.id,
        question_id=essay.id,
        selected_option_id=None,
        text_answer=essay_text,
        is_correct=False,
        points_earned=0,
    )
    db.add_all([mcq_answer, essay_answer])
    db.commit()
    return quiz, essay, attempt, essay_answer


def _now_utc():
    from datetime import UTC, datetime

    return datetime.now(UTC)


def test_grade_essay_answer_recomputes_passed(client: TestClient, student, db: Session):
    _seed_course_with_enrollment(db)
    quiz, _essay, attempt, essay_answer = _seed_submitted_essay_attempt(db)

    pending = client.get(f"/api/v1/quizzes/{quiz.id}/pending-answers").json()
    assert len(pending) == 1
    pending_answer = pending[0]
    assert pending_answer["question_type"] == "essay"
    assert pending_answer["student_id"] == str(STUDENT_ID)

    graded = client.patch(
        f"/api/v1/quizzes/answers/{essay_answer.id}",
        json={"points_earned": 18, "grader_comment": "Clear and well-structured."},
    )
    assert graded.status_code == 200, graded.text
    body = graded.json()
    assert body["points_earned"] == 18
    assert body["grader_comment"] == "Clear and well-structured."

    attempts_resp = client.get(f"/api/v1/quizzes/{quiz.id}/attempts").json()
    attempt_view = next(a for a in attempts_resp if a["id"] == str(attempt.id))
    assert attempt_view["score"] == 1 + 18
    assert attempt_view["max_score"] == 21
    assert attempt_view["passed"] is True  # 19/21 ≈ 90.5% ≥ 70

    pending_after = client.get(f"/api/v1/quizzes/{quiz.id}/pending-answers").json()
    assert pending_after == []

    graded_list = client.get(f"/api/v1/quizzes/{quiz.id}/pending-answers?include_graded=true").json()
    assert len(graded_list) == 1
    assert graded_list[0]["points_earned"] == 18


def test_grade_answer_acquires_for_update_lock_on_attempt(client: TestClient, student, db: Session, monkeypatch):
    """The PATCH handler must take a ``FOR UPDATE`` row lock on the
    attempt before recomputing the aggregate score.

    Without the lock, two teachers grading two different open-ended
    answers on the same attempt race: each one's
    ``recompute_attempt_grade`` reads the answer rows from its own
    snapshot, sums them, and writes back ``attempt.score`` /
    ``attempt.passed``. The second commit overwrites the first with a
    stale total.

    SQLite compiles ``with_for_update`` to a no-op (no SAVEPOINT/lock
    syntax exists), so we can't observe the lock in the emitted SQL.
    Instead, spy on ``Query.with_for_update`` and assert it was invoked
    for a QuizAttempt query inside the handler.
    """
    from sqlalchemy.orm import Query

    _seed_course_with_enrollment(db)
    _quiz, _essay, _attempt, essay_answer = _seed_submitted_essay_attempt(db)

    locked_entities: list[str] = []
    real_with_for_update = Query.with_for_update

    def _spy(self, *args, **kwargs):
        entity_names = [str(ent) for ent in self.column_descriptions]
        locked_entities.extend(entity_names)
        return real_with_for_update(self, *args, **kwargs)

    monkeypatch.setattr(Query, "with_for_update", _spy)

    resp = client.patch(
        f"/api/v1/quizzes/answers/{essay_answer.id}",
        json={"points_earned": 5},
    )
    assert resp.status_code == 200, resp.text

    quiz_attempt_locks = [e for e in locked_entities if "QuizAttempt" in e]
    assert quiz_attempt_locks, f"grade_answer must SELECT the attempt with FOR UPDATE; saw locks on: {locked_entities}"


def test_grade_zero_with_no_comment_clears_pending_queue(client: TestClient, student, db: Session):
    """A 0-point grade with no comment must still drop out of the pending queue.

    Regression for the bug where the pending-answers filter used
    ``(grader_comment IS NULL AND points_earned == 0)`` as its
    "still pending" heuristic — that's exactly what a "graded as 0 with
    no feedback" row also looks like, so the row would silently reappear
    on every reload and the teacher could never actually mark a poor
    essay as zero without inventing a comment.
    """
    _seed_course_with_enrollment(db)
    quiz, _essay, _attempt, essay_answer = _seed_submitted_essay_attempt(db)

    # Pre-state: row visible in the pending queue.
    pending = client.get(f"/api/v1/quizzes/{quiz.id}/pending-answers").json()
    assert len(pending) == 1
    assert pending[0]["answer_id"] == str(essay_answer.id)

    # Grade with the exact ambiguous combo: 0 points, no comment.
    resp = client.patch(
        f"/api/v1/quizzes/answers/{essay_answer.id}",
        json={"points_earned": 0},
    )
    assert resp.status_code == 200, resp.text

    # Post-state: row is no longer pending.
    pending_after = client.get(f"/api/v1/quizzes/{quiz.id}/pending-answers").json()
    assert pending_after == []

    # And it does show up when the teacher asks for graded rows too.
    graded = client.get(f"/api/v1/quizzes/{quiz.id}/pending-answers?include_graded=true").json()
    assert len(graded) == 1
    assert graded[0]["answer_id"] == str(essay_answer.id)
    assert graded[0]["points_earned"] == 0
    assert graded[0]["grader_comment"] is None


def test_grade_answer_rejects_points_above_cap(client: TestClient, student, db: Session):
    _seed_course_with_enrollment(db)
    _quiz, _essay, _attempt, essay_answer = _seed_submitted_essay_attempt(db)

    resp = client.patch(
        f"/api/v1/quizzes/answers/{essay_answer.id}",
        json={"points_earned": 99},
    )
    assert resp.status_code == 400
    assert "exceeds" in resp.json()["detail"].lower()


def test_grade_answer_rejects_auto_graded_question(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    quiz, questions, opts = _seed_quiz_with_questions(db)
    submit = student_client.post(
        f"/api/v1/quizzes/{quiz.id}/submit",
        json={"answers": [{"question_id": str(questions[0].id), "selected_option_id": str(opts["q1_correct"])}]},
    )
    assert submit.status_code == 200
    answer_id = submit.json()["answers"][0]["id"]

    # ``student_client`` can't hit the teacher endpoint (403), so we flip the
    # override inline just for this assertion.
    from app.api.dependencies import get_current_user
    from app.main import app

    teacher_user = db.query(User).filter(User.id == TEACHER_ID).first()

    def _as_teacher():
        return teacher_user

    original = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = _as_teacher
    try:
        resp = student_client.patch(
            f"/api/v1/quizzes/answers/{answer_id}",
            json={"points_earned": 1, "grader_comment": "n/a"},
        )
    finally:
        if original is not None:
            app.dependency_overrides[get_current_user] = original
    assert resp.status_code == 400
    assert "open-ended" in resp.json()["detail"].lower()


def test_grade_answer_student_forbidden(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    _quiz, _essay, _attempt, essay_answer = _seed_submitted_essay_attempt(db)
    resp = student_client.patch(
        f"/api/v1/quizzes/answers/{essay_answer.id}",
        json={"points_earned": 15},
    )
    assert resp.status_code == 403


def test_pending_answers_student_forbidden(student_client: TestClient, db: Session):
    _seed_course_with_enrollment(db)
    quiz, *_ = _seed_essay_quiz(db)
    resp = student_client.get(f"/api/v1/quizzes/{quiz.id}/pending-answers")
    assert resp.status_code == 403


def test_grade_answer_not_found(client: TestClient, db: Session):
    _seed_course(db)
    resp = client.patch(
        f"/api/v1/quizzes/answers/{uuid.uuid4()}",
        json={"points_earned": 1},
    )
    assert resp.status_code == 404
