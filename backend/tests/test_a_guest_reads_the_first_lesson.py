"""A visitor reads the first lesson before signing up (2026-10-03).

Everything else about a course stays behind an account: the other
lessons, a test, a lesson of a course only an organization can see, and a
course whose first lesson is a test rather than something to read.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.course import Chapter

from ._cv_helpers import make_chapter_block_with_content, make_course_with_text, make_module_with_text
from .conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _chapter(db: Session, course_id: str, module_id: str | None, order: int, kind: str = "reading") -> Chapter:
    ch = Chapter(
        id=f"ch-{uuid.uuid4().hex[:8]}",
        course_id=course_id,
        module_id=module_id,
        title=f"Lesson {order}",
        order_index=order,
        chapter_type=kind,
    )
    db.add(ch)
    db.commit()
    return ch


def _course(db: Session, *, access_mode: str = "public", first_kind: str = "reading") -> tuple[str, Chapter, Chapter]:
    course = make_course_with_text(
        db,
        course_id=f"guest-{uuid.uuid4().hex[:6]}",
        title="Acts",
        status="published",
        access_mode=access_mode,
        created_by=TEACHER_ID,
    )
    module = make_module_with_text(db, course_id=course.id, title="Part one", order_index=0)
    first = _chapter(db, course.id, module.id, 0, first_kind)
    second = _chapter(db, course.id, module.id, 1)
    make_chapter_block_with_content(db, chapter_id=first.id, content="<p>In the beginning</p>")
    make_chapter_block_with_content(db, chapter_id=second.id, content="<p>Later on</p>")
    return course.id, first, second


def test_the_course_page_names_the_lesson_a_guest_may_read(db: Session, anon_client: TestClient) -> None:
    course_id, first, _ = _course(db)
    r = anon_client.get(f"/api/v1/courses/{course_id}")
    assert r.status_code == 200
    assert r.json()["preview_chapter_id"] == first.id


def test_a_guest_reads_the_first_lesson_and_is_asked_to_sign_in_for_the_second(
    db: Session, anon_client: TestClient
) -> None:
    _course_id, first, second = _course(db)
    r = anon_client.get(f"/api/v1/blocks/chapter/{first.id}")
    assert r.status_code == 200, r.text
    assert "In the beginning" in r.json()[0]["content"]
    r = anon_client.get(f"/api/v1/blocks/chapter/{second.id}")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "auth.required"


def test_an_organization_s_course_shows_a_guest_nothing(db: Session, anon_client: TestClient) -> None:
    _course_id, first, _ = _course(db, access_mode="institute")
    assert anon_client.get(f"/api/v1/blocks/chapter/{first.id}").status_code == 404


def test_a_course_that_opens_with_a_test_has_no_preview(db: Session, anon_client: TestClient) -> None:
    course_id, first, _ = _course(db, first_kind="quiz")
    assert anon_client.get(f"/api/v1/courses/{course_id}").json()["preview_chapter_id"] is None
    assert anon_client.get(f"/api/v1/blocks/chapter/{first.id}").status_code == 401


def test_a_signed_in_reader_is_not_handed_a_preview_and_still_needs_enrolment(
    db: Session, client: TestClient, student_client: TestClient
) -> None:
    course_id, first, _ = _course(db)
    assert student_client.get(f"/api/v1/courses/{course_id}").json()["preview_chapter_id"] is None
    assert student_client.get(f"/api/v1/blocks/chapter/{first.id}").status_code == 403
