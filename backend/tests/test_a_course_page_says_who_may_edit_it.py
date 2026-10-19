"""The course page says whether the reader may edit it — not who wrote it.

``CourseDetail`` decided «is this mine?» by comparing the reader's id with
``created_by``, so the author's account id went to every guest who opened a
course page. The server already knew the answer — ``is_owner_or_admin`` gates
the source text and the unreleased lessons on it — and now says it in
``viewer_can_edit``; ``created_by`` reaches only the reader it is true for.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from ._cv_helpers import make_course_with_text
from .conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _course(db: Session, status: str = "published") -> str:
    course = make_course_with_text(
        db,
        course_id=f"owner-{uuid.uuid4().hex[:6]}",
        title="Preaching",
        status=status,
        source_locale="ru",
        created_by=TEACHER_ID,
    )
    db.commit()
    return course.id


class TestWhoIsToldWhat:
    def test_a_guest_learns_neither_the_author_nor_a_right_they_do_not_have(
        self, db: Session, anon_client: TestClient
    ) -> None:
        r = anon_client.get(f"/api/v1/courses/{_course(db)}")
        assert r.status_code == 200, r.text
        assert r.json()["viewer_can_edit"] is False
        assert r.json()["created_by"] is None

    def test_a_student_is_a_reader_too(self, db: Session, student_client: TestClient) -> None:
        r = student_client.get(f"/api/v1/courses/{_course(db)}")
        assert r.status_code == 200, r.text
        assert r.json()["viewer_can_edit"] is False
        assert r.json()["created_by"] is None

    def test_the_author_may_edit_and_is_the_one_told_the_author_s_id(self, db: Session, client: TestClient) -> None:
        course_id = _course(db, status="draft")
        for query in ("", "?source=1"):
            r = client.get(f"/api/v1/courses/{course_id}{query}")
            assert r.status_code == 200, r.text
            assert r.json()["viewer_can_edit"] is True
            assert r.json()["created_by"] == str(TEACHER_ID)

    def test_platform_staff_may_edit_any_course(self, db: Session, admin_client: TestClient) -> None:
        r = admin_client.get(f"/api/v1/courses/{_course(db)}")
        assert r.status_code == 200, r.text
        assert r.json()["viewer_can_edit"] is True

    def test_a_guest_in_every_language_the_overlay_serves(self, db: Session, anon_client: TestClient) -> None:
        # The translated page is built by a different path than the source
        # one; both must say the same.
        course_id = _course(db)
        for language in ("ru", "en", "de", "uk"):
            r = anon_client.get(f"/api/v1/courses/{course_id}", headers={"Accept-Language": language})
            assert r.status_code == 200, r.text
            assert r.json()["viewer_can_edit"] is False
            assert r.json()["created_by"] is None
