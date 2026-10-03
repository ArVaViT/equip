"""A student walks one course from the catalog to a verified certificate.

Every piece of this path has its own tests, and none of them walks the
path. That is how a step can be right on its own and still leave a
student stranded between two others — progress a later gate never sees,
a grade the certificate never counts, a request nobody can approve.

The path below is the one the first real group will walk: a teacher
writes and publishes a course, a student finds it, reads, passes a quiz,
hands in an essay, the teacher marks it, and the certificate goes through
both signatures to a number a stranger can check. It drives the real
HTTP API, as three people taking turns at one client, and asserts what
each of them would see on their screen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from app.api.consent_gate import consent_subject
from app.api.dependencies import get_current_user, get_optional_user
from app.core.database import get_db
from app.main import app

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

    from app.models.user import User

API = "/api/v1"


class Turns:
    """One client, and whoever is at the keyboard right now.

    ``act_as`` swaps the person every auth dependency resolves to, the
    consent gate included, so the next request is made by them.
    """

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def act_as(self, user: User | None) -> TestClient:
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_optional_user] = lambda: user
        app.dependency_overrides[consent_subject] = lambda: user
        return self.client


@pytest.fixture
def turns(db: Session) -> Iterator[Turns]:
    def _db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = _db
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield Turns(tc)


def _ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, f"{response.request.method} {response.request.url}: {response.text}"
    return response.json()


def test_a_student_walks_from_the_catalog_to_a_verified_certificate(
    turns: Turns, teacher: User, student: User, admin: User
) -> None:
    # ── 1. The teacher writes the course and publishes it ─────────────
    t = turns.act_as(teacher)
    course = _ok(
        t.post(f"{API}/courses", json={"title": "Acts of the Apostles", "description": "The early church."}),
        201,
    )
    course_id = course["id"]
    assert course["status"] == "draft"

    module = _ok(t.post(f"{API}/courses/{course_id}/modules", json={"title": "Jerusalem", "order_index": 0}), 201)
    module_id = module["id"]

    def lesson(title: str, chapter_type: str, order_index: int) -> str:
        chapter = _ok(
            t.post(
                f"{API}/courses/{course_id}/modules/{module_id}/chapters",
                json={"title": title, "chapter_type": chapter_type, "order_index": order_index},
            ),
            201,
        )
        return str(chapter["id"])

    reading_id = lesson("Pentecost", "reading", 0)
    quiz_chapter_id = lesson("Pentecost: check yourself", "quiz", 1)
    assignment_chapter_id = lesson("Pentecost: an essay", "assignment", 2)

    _ok(
        t.post(
            f"{API}/blocks/chapter/{reading_id}",
            json={"block_type": "text", "order_index": 0, "content": "<p>When the day of Pentecost came…</p>"},
        ),
        201,
    )

    quiz = _ok(
        t.post(
            f"{API}/quizzes",
            json={
                "chapter_id": quiz_chapter_id,
                "title": "Pentecost",
                "questions": [
                    {
                        "question_text": "Who preached at Pentecost?",
                        "question_type": "multiple_choice",
                        "options": [
                            {"option_text": "Peter", "is_correct": True, "order_index": 0},
                            {"option_text": "Paul", "is_correct": False, "order_index": 1},
                            {"option_text": "Barnabas", "is_correct": False, "order_index": 2},
                        ],
                    }
                ],
            },
        ),
        201,
    )
    quiz_id = quiz["id"]
    [question] = quiz["questions"]
    right_option_text = "Peter"

    assignment = _ok(
        t.post(
            f"{API}/assignments",
            json={
                "chapter_id": assignment_chapter_id,
                "title": "What changed at Pentecost",
                "description": "In a page, say what changed for the disciples and why.",
                "max_score": 100,
            },
        ),
        201,
    )
    assignment_id = assignment["id"]

    # The editor will not publish while anything critical fails; the API
    # does not enforce that itself, so the walk asks the same question the
    # editor does before pressing the button.
    readiness = _ok(t.get(f"{API}/courses/{course_id}/readiness"))
    failing = [c["id"] for c in readiness["checks"] if c["severity"] == "critical" and not c["passed"]]
    assert failing == []
    assert readiness["critical_failing"] == 0

    published = _ok(t.put(f"{API}/courses/{course_id}", json={"status": "published"}))
    assert published["status"] == "published"

    # ── 2. The student finds it, enrolls, sees the lessons ────────────
    s = turns.act_as(student)
    catalog = _ok(s.get(f"{API}/courses"))
    assert course_id in [c["id"] for c in catalog]

    enrollment = _ok(s.post(f"{API}/courses/{course_id}/enroll", json={}))
    assert enrollment["progress"] == 0
    assert _ok(s.get(f"{API}/courses/{course_id}/enrollment-status"))["enrolled"] is True

    detail = _ok(s.get(f"{API}/courses/{course_id}"))
    seen = [(ch["title"], ch["chapter_type"]) for m in detail["modules"] for ch in m["chapters"]]
    assert seen == [
        ("Pentecost", "reading"),
        ("Pentecost: check yourself", "quiz"),
        ("Pentecost: an essay", "assignment"),
    ]
    blocks = _ok(s.get(f"{API}/blocks/chapter/{reading_id}"))
    assert "Pentecost came" in blocks[0]["content"]
    assert _ok(s.get(f"{API}/progress/course/{course_id}/my-progress")) == []

    # ── 3. The student reads the first lesson ─────────────────────────
    _ok(s.put(f"{API}/progress/chapter/{reading_id}/read"))
    assert _ok(s.get(f"{API}/progress/course/{course_id}/my-progress")) == [reading_id]
    [mine] = [e for e in _ok(s.get(f"{API}/users/me/courses")) if e["course_id"] == course_id]
    assert (mine["chapters_read"], mine["chapters_to_read"]) == (1, 1)

    # ── 4. The student takes the quiz and passes ──────────────────────
    student_quiz = _ok(s.get(f"{API}/quizzes/chapter/{quiz_chapter_id}"))
    [student_question] = student_quiz["questions"]
    assert all("is_correct" not in o for o in student_question["options"])
    [right] = [o for o in student_question["options"] if o["option_text"] == right_option_text]

    attempt = _ok(
        s.post(
            f"{API}/quizzes/{quiz_id}/submit",
            json={"answers": [{"question_id": question["id"], "selected_option_id": right["id"]}]},
        )
    )
    assert attempt["passed"] is True
    assert (attempt["score"], attempt["max_score"]) == (1, 1)
    assert len(_ok(s.get(f"{API}/quizzes/{quiz_id}/my-attempts"))) == 1
    assert set(_ok(s.get(f"{API}/progress/course/{course_id}/my-progress"))) == {reading_id, quiz_chapter_id}

    # ── 5. The student hands in the essay ─────────────────────────────
    submission = _ok(
        s.post(
            f"{API}/assignments/{assignment_id}/submit",
            json={
                "content": "The Spirit came, and frightened men spoke in the open.",
                "declaration": {"ai_use": "none", "statement": "I wrote this myself."},
            },
        ),
        201,
    )
    assert submission["status"] == "submitted"
    assert _ok(s.get(f"{API}/courses/{course_id}/enrollment-status"))["enrollment"]["progress"] == 100

    # Every lesson is done, and the essay is unread: the course page says
    # so, and the certificate is refused for exactly that reason. Progress
    # alone was the old gate; it would have issued here.
    standing = _ok(s.get(f"{API}/grades/my/{course_id}/breakdown"))
    assert [b["code"] for b in standing["certificate_blockers"]] == ["work_not_graded"]
    assert {i["kind"]: i["status"] for i in standing["items"]} == {"quiz": "graded", "assignment": "pending_review"}
    too_early = s.post(f"{API}/certificates/course/{course_id}")
    assert too_early.status_code == 400
    assert [b["code"] for b in too_early.json()["detail"]["context"]["blockers"]] == ["work_not_graded"]

    # ── 6. The teacher marks it; the student sees the mark ────────────
    t = turns.act_as(teacher)
    assert len(_ok(t.get(f"{API}/quizzes/{quiz_id}/attempts"))) == 1
    [waiting] = _ok(t.get(f"{API}/assignments/{assignment_id}/submissions"))
    assert waiting["id"] == submission["id"]
    assert waiting["student_id"] == str(student.id)

    graded = _ok(
        t.put(
            f"{API}/assignments/submissions/{submission['id']}/grade",
            json={"grade": 90, "feedback": "Clear and honest. Quote the text next time.", "status": "graded"},
        )
    )
    assert (graded["status"], graded["grade"]) == ("graded", 90)

    s = turns.act_as(student)
    [back] = _ok(s.get(f"{API}/assignments/{assignment_id}/my-submissions"))
    assert (back["grade"], back["feedback"]) == (90, "Clear and honest. Quote the text next time.")
    notifications = _ok(s.get(f"{API}/notifications"))
    standing = _ok(s.get(f"{API}/grades/my/{course_id}/breakdown"))
    assert standing["certificate_blockers"] == []
    assert standing["result_state"] == "graded"
    # The default split, 40 quiz / 60 assignment: 100 * 0.4 + 90 * 0.6.
    assert standing["final_score"] == 94.0
    assert standing["final_symbol"] == "A"
    assert "assignment_graded" in [n["type"] for n in notifications["items"]]

    # ── 7. The course is complete; the certificate goes through ───────
    cert = _ok(s.post(f"{API}/certificates/course/{course_id}"), 201)
    assert cert["status"] == "pending"
    assert cert["certificate_number"] is None

    t = turns.act_as(teacher)
    [queued] = _ok(t.get(f"{API}/certificates/pending"))
    assert queued["id"] == cert["id"]
    assert queued["blockers"] == []
    signed = _ok(t.put(f"{API}/certificates/{cert['id']}/teacher-approve"))
    assert signed["status"] == "teacher_approved"
    # Two pairs of eyes: the teacher cannot also issue it.
    assert t.put(f"{API}/certificates/{cert['id']}/admin-approve").status_code == 403

    a = turns.act_as(admin)
    assert cert["id"] in [c["id"] for c in _ok(a.get(f"{API}/certificates/admin/pending"))]
    issued = _ok(a.put(f"{API}/certificates/{cert['id']}/admin-approve"))
    assert issued["status"] == "approved"
    number = issued["certificate_number"]
    assert number

    s = turns.act_as(student)
    mine_now = _ok(s.get(f"{API}/certificates/course/{course_id}"))
    assert (mine_now["status"], mine_now["certificate_number"]) == ("approved", number)

    stranger = turns.act_as(None)
    verified = _ok(stranger.get(f"{API}/certificates/verify/{number}"))
    assert verified["valid"] is True
    assert verified["certificate_number"] == number
    assert verified["user_name"] == student.full_name
    assert verified["course_title"] == "Acts of the Apostles"
