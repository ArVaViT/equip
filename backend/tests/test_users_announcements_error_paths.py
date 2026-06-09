"""Error-path tests for ``app.api.v1.users`` + ``app.api.v1.announcements``.

The happy-path tests for these endpoints fly past several 400 / 403 /
500 envelopes. This file pins them so the frontend's banner mapping
doesn't silently regress.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.announcement import Announcement
from app.models.enrollment import Enrollment

from ._cv_helpers import make_course_with_text
from .conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    import pytest
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# users.py error paths
# ---------------------------------------------------------------------------


class TestBulkRoleUpdate:
    def test_no_valid_ids_returns_400(
        self,
        admin_client: TestClient,
    ) -> None:
        """All inputs malformed → 400 with the canonical envelope.
        Pin so a future input sanitiser can't accidentally promote the
        error path to a silent 200-with-0-updated."""
        r = admin_client.put(
            "/api/v1/users/admin/users/bulk-role",
            json={"user_ids": ["not-a-uuid", "also-not"], "role": "teacher"},
        )
        assert r.status_code == 400
        assert "No valid user IDs" in r.json()["detail"]["message"]


class TestUpdateOwnRole:
    def test_admin_changing_own_role_returns_400(
        self,
        admin_client: TestClient,
        admin,
    ) -> None:
        """Admins MUST NOT demote themselves — a confused admin
        accidentally yanking their own admin rights would lock the
        deployment out of the admin surface. Pin the guard so a
        refactor that loosens the check (e.g. allowing self-promote)
        surfaces."""
        r = admin_client.put(
            f"/api/v1/users/admin/users/{admin.id}/role?role=student",
        )
        assert r.status_code == 400
        assert "your own role" in r.json()["detail"]["message"]


class TestAdminDeleteUserErrorPath:
    def test_purge_failure_returns_500_envelope(
        self,
        admin_client: TestClient,
        db: Session,
        admin,
        student,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When the soft-delete write fails (DB trouble during the
        deactivation commit) the route catches it, rolls back, and
        surfaces a clean 500 — never a raw 503 or stack trace."""
        from app.api.v1 import users as route_mod

        def boom(*_a: object, **_k: object) -> None:
            raise RuntimeError("audit write exploded")

        monkeypatch.setattr(route_mod, "log_action", boom)
        r = admin_client.delete(f"/api/v1/users/admin/users/{student.id}")
        assert r.status_code == 500
        body = r.json()["detail"]
        assert "User deletion failed" in body["message"]


# ---------------------------------------------------------------------------
# announcements.py error paths
# ---------------------------------------------------------------------------


def _seed_course_with_announcement(db: Session, course_id: str) -> str:
    course = make_course_with_text(
        db,
        course_id=course_id,
        title="Annc Test",
        status="published",
        created_by=TEACHER_ID,
    )
    db.add(
        Announcement(
            id=__import__("uuid").uuid4(),
            course_id=course.id,
            created_by=TEACHER_ID,
        )
    )
    db.commit()
    return course.id


class TestAnnouncementsSourceGate:
    """``?source=1`` (editor view) requires both a course_id filter AND
    course ownership (or admin). Without the filter we'd leak draft
    content across courses; without the ownership check anyone could
    pull editor text."""

    def test_source_without_course_id_returns_400(
        self,
        client: TestClient,
    ) -> None:
        """``?source=1`` with no course_id filter would return a
        heterogeneous list of source-locale rows. The route MUST 400."""
        r = client.get("/api/v1/announcements?source=1")
        assert r.status_code == 400
        assert "course_id" in r.json()["detail"]["message"]

    def test_source_for_non_owner_non_admin_returns_403(
        self,
        student_client: TestClient,
        db: Session,
    ) -> None:
        course_id = _seed_course_with_announcement(db, "annc-src-1")
        # Enroll the student so the visibility check (non-source path)
        # would normally pass — we want to confirm ?source=1 is gated
        # SEPARATELY from regular visibility.
        db.add(
            Enrollment(
                id=f"enr-{course_id}",
                user_id=STUDENT_ID,
                course_id=course_id,
                progress=0,
            )
        )
        db.commit()

        r = student_client.get(
            f"/api/v1/announcements?source=1&course_id={course_id}",
        )
        assert r.status_code == 403
        assert "source-language" in r.json()["detail"]["message"]

    def test_owner_can_request_source(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        course_id = _seed_course_with_announcement(db, "annc-src-2")
        r = client.get(f"/api/v1/announcements?source=1&course_id={course_id}")
        assert r.status_code == 200


class TestAnnouncementsCourseFilterAccessGate:
    """Non-admin requesting a specific course's announcements must be
    enrolled OR be the course owner. Anyone else gets 403 — pre-fix,
    this branch silently returned the full list (IDOR P0.4)."""

    def test_non_enrolled_non_owner_returns_403(
        self,
        student_client: TestClient,
        db: Session,
    ) -> None:
        course_id = _seed_course_with_announcement(db, "annc-acc-1")
        # Student is logged in but NOT enrolled and NOT the owner.
        r = student_client.get(f"/api/v1/announcements?course_id={course_id}")
        assert r.status_code == 403
        assert "do not have access" in r.json()["detail"]["message"]

    def test_enrolled_student_can_see_course_announcements(
        self,
        student_client: TestClient,
        db: Session,
    ) -> None:
        course_id = _seed_course_with_announcement(db, "annc-acc-2")
        db.add(
            Enrollment(
                id=f"enr-{course_id}",
                user_id=STUDENT_ID,
                course_id=course_id,
                progress=0,
            )
        )
        db.commit()
        r = student_client.get(f"/api/v1/announcements?course_id={course_id}")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_owner_can_see_their_course_announcements(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        course_id = _seed_course_with_announcement(db, "annc-acc-3")
        r = client.get(f"/api/v1/announcements?course_id={course_id}")
        assert r.status_code == 200
        assert len(r.json()) >= 1
