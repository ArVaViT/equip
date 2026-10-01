"""A student's notes on lessons: their own, beside the lesson, and on one page.

Pins that a note is written, read back, replaced and cleared; that it needs
the same access as the lesson; that one student never sees another's; and
that the notes are part of the student's own data export.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.chapter_note import ChapterNote
from app.models.course import Chapter, Module
from app.models.enrollment import Enrollment
from app.models.user import User
from tests._cv_helpers import make_course_with_text
from tests.conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

NOTES = "/api/v1/notes"


def _lesson(db: Session, *, enrolled: bool = True) -> str:
    course = make_course_with_text(db, title="Acts", status="published", created_by=TEACHER_ID)
    module = Module(id=f"m-{course.id}", course_id=course.id, title="M", order_index=0)
    chapter = Chapter(id=f"c-{course.id}", course_id=course.id, module_id=module.id, title="Pentecost", order_index=0)
    db.add_all([module, chapter])
    if enrolled:
        db.add(Enrollment(id=str(uuid.uuid4()), user_id=STUDENT_ID, course_id=course.id, progress=0))
    db.commit()
    return chapter.id


def test_a_note_is_written_read_replaced_and_cleared(student_client: TestClient, db: Session, student: User) -> None:
    chapter = _lesson(db)
    assert student_client.get(f"{NOTES}/chapters/{chapter}").json()["body"] is None

    r = student_client.put(f"{NOTES}/chapters/{chapter}", json={"body": "  Acts 2:42 — four marks of the church  "})
    assert r.status_code == 200, r.text
    assert r.json()["body"] == "Acts 2:42 — four marks of the church"

    student_client.put(f"{NOTES}/chapters/{chapter}", json={"body": "Replaced"})
    assert student_client.get(f"{NOTES}/chapters/{chapter}").json()["body"] == "Replaced"

    # Saving nothing is deleting it.
    assert student_client.put(f"{NOTES}/chapters/{chapter}", json={"body": "   "}).json()["body"] is None
    assert db.query(ChapterNote).count() == 0


def test_a_lesson_one_cannot_read_takes_no_note(student_client: TestClient, db: Session, student: User) -> None:
    chapter = _lesson(db, enrolled=False)
    assert student_client.put(f"{NOTES}/chapters/{chapter}", json={"body": "x"}).status_code == 403


def test_the_notes_page_lists_mine_only_and_the_export_has_them(
    student_client: TestClient, db: Session, student: User
) -> None:
    chapter = _lesson(db)
    student_client.put(f"{NOTES}/chapters/{chapter}", json={"body": "Mine"})
    classmate = User(id=uuid.uuid4(), email="classmate@example.com", full_name="Classmate", role="student")
    db.add(classmate)
    db.flush()
    db.add(ChapterNote(user_id=classmate.id, chapter_id=chapter, body="Theirs"))
    db.commit()

    rows = student_client.get(f"{NOTES}/me").json()
    assert [(n["chapter_id"], n["body"]) for n in rows] == [(chapter, "Mine")]
    assert rows[0]["course_title"] == "Acts"
    assert student_client.get(f"{NOTES}/chapters/{chapter}").json()["body"] == "Mine"

    export = student_client.get("/api/v1/users/me/export").json()
    assert [n["body"] for n in export["lesson_notes"]] == ["Mine"]


def test_too_long_a_note_is_refused(student_client: TestClient, db: Session, student: User) -> None:
    chapter = _lesson(db)
    assert student_client.put(f"{NOTES}/chapters/{chapter}", json={"body": "x" * 10_001}).status_code == 422
