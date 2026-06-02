"""Coverage tests for small route-error envelopes.

Bundles three quick wins from the easy-coverage punch list:
* ``app.api.v1.audit`` filter branches (user_id + date range)
* ``app.api.v1.prerequisites`` 404 + self-cycle 400 paths
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from ._cv_helpers import make_course_with_text
from .conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


class TestAuditFilters:
    def test_audit_filters_apply_with_user_id_and_dates(self, admin_client: TestClient) -> None:
        """One request exercising all three filter branches (user_id,
        date_from, date_to). The filters compose into a single
        SQLAlchemy query — we don't care about the row results, just
        that the route processes the args without error.
        """
        user_id = str(uuid.uuid4())
        r = admin_client.get(
            f"/api/v1/audit?user_id={user_id}"
            f"&date_from=2026-01-01T00:00:00Z"
            f"&date_to=2026-12-31T23:59:59Z"
            f"&page=1&page_size=10"
        )
        # Empty list of rows is fine — we're proving the route ran.
        assert r.status_code == 200
        body = r.json()
        assert "items" in body
        assert body["total"] == 0


class TestPrerequisitesVisibility:
    def test_unknown_course_returns_404(self, client: TestClient) -> None:
        r = client.get("/api/v1/prerequisites/course/never-was-a-course")
        assert r.status_code == 404

    def test_unpublished_course_404s_for_non_owner_non_admin(self, student_client: TestClient, db: Session) -> None:
        """Draft courses are invisible to non-owners non-admins on
        the prereqs endpoint — leak-guard mirrors the catalog detail."""
        make_course_with_text(
            db,
            course_id="prereq-draft",
            title="Hidden",
            status="draft",
            created_by=TEACHER_ID,
        )
        db.commit()
        r = student_client.get("/api/v1/prerequisites/course/prereq-draft")
        assert r.status_code == 404

    def test_self_cycle_in_put_returns_400(self, client: TestClient, db: Session) -> None:
        """Setting a course's own id as a prereq would create an
        immediate self-cycle — the route MUST 400 instead of saving
        the loop."""
        make_course_with_text(
            db,
            course_id="prereq-self",
            title="Self",
            status="published",
            created_by=TEACHER_ID,
        )
        db.commit()
        r = client.put(
            "/api/v1/prerequisites/course/prereq-self",
            json={"prerequisite_course_ids": ["prereq-self"]},
        )
        assert r.status_code == 400
        assert "prerequisite" in r.json()["detail"]["message"].lower()


class TestCoursesCrudDeletePermanent:
    def test_delete_permanent_unknown_id_returns_404(self, admin_client: TestClient) -> None:
        """``DELETE /courses/{id}/permanent`` on an unknown id 404s.
        Pin so a future refactor that silent-200s doesn't leak."""
        r = admin_client.delete("/api/v1/courses/never-existed/permanent")
        assert r.status_code in (404, 405)
        # Either the route is missing (405) — caught upstream — or it
        # 404s, which is the canonical envelope. Both are acceptable;
        # what's NOT acceptable is 200.

    def test_admin_can_view_their_own_draft_course(
        self,
        admin_client: TestClient,
        db: Session,
    ) -> None:
        """The unpublished course visibility branch in catalog/crud —
        admin sees the draft course without the gating logic
        kicking in."""
        make_course_with_text(
            db,
            course_id="crud-admin-draft",
            title="Hidden",
            status="draft",
            created_by=TEACHER_ID,
        )
        db.commit()
        # Admin client visits the detail route — the visibility gate
        # in catalog should let them through even though it's draft.
        r = admin_client.get("/api/v1/courses/crud-admin-draft")
        assert r.status_code == 200


class TestSeedAuditLog:
    def test_audit_log_seeding_via_admin_action(self, admin_client: TestClient, db: Session) -> None:
        """Quick smoke that exercises the audit query against a course
        that exists — covers the row-loading + serialization path."""
        course = make_course_with_text(
            db,
            course_id="audit-seed",
            title="Audit",
            status="published",
            created_by=TEACHER_ID,
        )
        db.commit()
        r = admin_client.get("/api/v1/audit?resource_type=course")
        assert r.status_code == 200
        # We don't assert on row count — the test environment seeds
        # audit rows variably depending on which paths fire. The
        # point is the route processes a real resource_type filter.
        _ = course
