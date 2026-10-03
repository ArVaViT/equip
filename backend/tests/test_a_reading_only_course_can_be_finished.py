"""A course with nothing to assess is finished by reading it (2026-10-03).

Progress counted assessed chapters only and set 0 when there were none, while
the certificate gate for such a course is «progress == 100». Every lesson read,
«course not complete», no certificate — for any reading-only course.
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


@pytest.fixture
def c(db: Session) -> Iterator[TestClient]:
    def _db() -> Iterator[Session]:
        yield db

    app.dependency_overrides[get_db] = _db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def _as(user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_optional_user] = lambda: user
    app.dependency_overrides[consent_subject] = lambda: user


def _ok(r: Any, status: int = 200) -> Any:
    assert r.status_code == status, f"{r.request.method} {r.request.url}: {r.text}"
    return r.json()


def _course(c: TestClient, teacher: User, *, with_quiz: bool) -> tuple[str, list[str], str | None, str]:
    _as(teacher)
    course = _ok(c.post(f"{API}/courses", json={"title": "Reading", "description": "x"}), 201)
    cid = course["id"]
    module = _ok(c.post(f"{API}/courses/{cid}/modules", json={"title": "M", "order_index": 0}), 201)
    readings = []
    quiz_chapter_id = None
    for i in range(2):
        ch = _ok(
            c.post(
                f"{API}/courses/{cid}/modules/{module['id']}/chapters",
                json={"title": f"L{i}", "chapter_type": "reading", "order_index": i},
            ),
            201,
        )
        _ok(
            c.post(
                f"{API}/blocks/chapter/{ch['id']}", json={"block_type": "text", "order_index": 0, "content": "<p>t</p>"}
            ),
            201,
        )
        readings.append(ch["id"])
    if with_quiz:
        quiz_ch = _ok(
            c.post(
                f"{API}/courses/{cid}/modules/{module['id']}/chapters",
                json={"title": "Q", "chapter_type": "quiz", "order_index": 9},
            ),
            201,
        )
        quiz_chapter_id = quiz_ch["id"]
        _ok(
            c.post(
                f"{API}/quizzes",
                json={
                    "chapter_id": quiz_ch["id"],
                    "title": "Q",
                    "questions": [
                        {
                            "question_text": "?",
                            "question_type": "multiple_choice",
                            "options": [
                                {"option_text": "a", "is_correct": True, "order_index": 0},
                                {"option_text": "b", "is_correct": False, "order_index": 1},
                            ],
                        }
                    ],
                },
            ),
            201,
        )
    _ok(c.put(f"{API}/courses/{cid}", json={"status": "published"}))
    return cid, readings, quiz_chapter_id, module["id"]


def test_reading_every_lesson_finishes_a_course_with_nothing_to_assess(
    c: TestClient, teacher: User, student: User
) -> None:
    cid, readings, _quiz, _module = _course(c, teacher, with_quiz=False)
    _as(student)
    _ok(c.post(f"{API}/courses/{cid}/enroll", json={}))

    _ok(c.put(f"{API}/progress/chapter/{readings[0]}/read"))
    assert _ok(c.get(f"{API}/grades/my/{cid}/breakdown"))["progress"] == 50

    _ok(c.put(f"{API}/progress/chapter/{readings[1]}/read"))
    standing = _ok(c.get(f"{API}/grades/my/{cid}/breakdown"))
    assert standing["progress"] == 100
    assert "course_not_complete" not in [b["code"] for b in standing["certificate_blockers"]]


def test_on_a_course_with_a_quiz_reading_does_not_move_progress(c: TestClient, teacher: User, student: User) -> None:
    cid, readings, _quiz, _module = _course(c, teacher, with_quiz=True)
    _as(student)
    _ok(c.post(f"{API}/courses/{cid}/enroll", json={}))
    for chapter in readings:
        _ok(c.put(f"{API}/progress/chapter/{chapter}/read"))

    # Assessment-only, as before: the quiz is still to do.
    assert _ok(c.get(f"{API}/grades/my/{cid}/breakdown"))["progress"] == 0


def test_reading_on_an_assessed_course_does_not_recompute(
    c: TestClient, teacher: User, student: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Every recompute writes a metric line, and reading is the most frequent
    # thing anybody does: only a course with nothing to assess needs it.
    import app.api.v1.progress as progress_routes

    cid, readings, _quiz, _module = _course(c, teacher, with_quiz=True)
    _as(student)
    _ok(c.post(f"{API}/courses/{cid}/enroll", json={}))
    calls: list[str] = []
    monkeypatch.setattr(progress_routes, "sync_enrollment_progress", lambda *a, **k: calls.append("sync"))

    _ok(c.put(f"{API}/progress/chapter/{readings[0]}/read"))

    assert calls == []


def test_somebody_who_read_it_all_before_the_fix_gets_out_with_one_press(
    c: TestClient, db: Session, teacher: User, student: User
) -> None:
    # Read everything under the old rule and stored at 0: every chapter is
    # already read, so pressing «read» again was the idempotent return and
    # nothing moved them.
    from app.models.enrollment import Enrollment

    cid, readings, _quiz, _module = _course(c, teacher, with_quiz=False)
    _as(student)
    _ok(c.post(f"{API}/courses/{cid}/enroll", json={}))
    for chapter in readings:
        _ok(c.put(f"{API}/progress/chapter/{chapter}/read"))
    db.query(Enrollment).filter(Enrollment.course_id == cid).update({Enrollment.progress: 0})
    db.commit()

    _ok(c.put(f"{API}/progress/chapter/{readings[0]}/read"))

    assert _progress(c, cid) == 100


def _progress(c: TestClient, cid: str) -> int:
    return _ok(c.get(f"{API}/grades/my/{cid}/breakdown"))["progress"]


def test_deleting_the_only_quiz_does_not_strand_a_student_who_read_everything(
    c: TestClient, teacher: User, student: User
) -> None:
    cid, readings, quiz, _module = _course(c, teacher, with_quiz=True)
    _as(student)
    _ok(c.post(f"{API}/courses/{cid}/enroll", json={}))
    for chapter in readings:
        _ok(c.put(f"{API}/progress/chapter/{chapter}/read"))
    assert _progress(c, cid) == 0  # the quiz is still to do

    _as(teacher)
    assert c.delete(f"{API}/courses/{cid}/chapters/{quiz}").status_code == 204

    # Nothing left to assess: what they read is the course.
    _as(student)
    assert _progress(c, cid) == 100


def test_a_lesson_added_or_removed_moves_a_reading_course(
    c: TestClient, db: Session, teacher: User, student: User
) -> None:
    from app.services.staged_edits import promote_staged_entity_unconditionally

    cid, readings, _quiz, module = _course(c, teacher, with_quiz=False)
    _as(student)
    _ok(c.post(f"{API}/courses/{cid}/enroll", json={}))
    for chapter in readings:
        _ok(c.put(f"{API}/progress/chapter/{chapter}/read"))
    assert _progress(c, cid) == 100

    _as(teacher)
    extra = _ok(
        c.post(
            f"{API}/courses/{cid}/modules/{module}/chapters",
            json={"title": "New", "chapter_type": "reading", "order_index": 5},
        ),
        201,
    )
    _as(student)
    # The course is live, so the new lesson is held until every language
    # has it — nobody can open it yet, and it is not counted against anybody
    # (2026-10-03). It moves the number the moment it is released.
    assert _progress(c, cid) == 100
    promote_staged_entity_unconditionally(db, course_id=cid)
    assert _progress(c, cid) == 67  # a new lesson nobody has read yet

    _as(teacher)
    assert c.delete(f"{API}/courses/{cid}/chapters/{extra['id']}").status_code == 204
    _as(student)
    assert _progress(c, cid) == 100


def test_every_enrolment_the_student_holds_moves_together(
    c: TestClient, db: Session, teacher: User, student: User
) -> None:
    import uuid
    from datetime import UTC, datetime, timedelta

    from app.models.cohort import Cohort
    from app.models.enrollment import Enrollment

    cid, readings, _quiz, _module = _course(c, teacher, with_quiz=False)
    _as(student)
    _ok(c.post(f"{API}/courses/{cid}/enroll", json={}))
    # A second row on the same course — a second cohort, or a retake.
    now = datetime.now(UTC)
    cohort = Cohort(id=uuid.uuid4(), start_date=now, end_date=now + timedelta(days=60))
    db.add(cohort)
    db.flush()
    db.add(Enrollment(id=f"enr-second-{cid}", user_id=student.id, course_id=cid, cohort_id=cohort.id, progress=0))
    db.commit()

    for chapter in readings:
        _ok(c.put(f"{API}/progress/chapter/{chapter}/read"))

    rows = db.query(Enrollment).filter_by(user_id=student.id, course_id=cid).all()
    assert len(rows) == 2
    assert {row.progress for row in rows} == {100}
