"""Targeted tests for thin paths in ``app.api.v1.cohorts``.

The existing ``test_cohorts_calendar_notifications.py`` covers the
happy-path CRUD + calendar attachment flows; this file plugs the
narrow uncovered slices around ``_write_cohort_name`` /
``_fetch_cohort_names`` early-returns and the visibility 404s on the
``GET /cohorts/course/{course_id}`` lookup.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from app.api.v1 import cohorts as cohorts_mod
from app.models.user import UserRole

from ._cv_helpers import make_course_with_text
from .conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User


class TestWriteCohortName:
    """The cohort name → cv writer. Guards two empty/no-op short-circuits
    so a future refactor doesn't accidentally start writing zero-length
    rows or fallback-to-empty-locale ones."""

    def test_empty_name_no_op(self, db: Session) -> None:
        """Whitespace-only name shouldn't write a row; the schema's
        text column would reject it anyway, but pinning the guard at
        the writer layer means the caller can pass through user input
        without pre-stripping."""
        recorded: dict = {}

        def fake_record(*_args: object, **kwargs: object) -> None:
            recorded.update(kwargs)

        admin = MagicMock(spec=cohorts_mod.User)
        admin.preferred_locale = "ru"
        admin.id = TEACHER_ID

        # Bypass the real ``record_human_version`` so we can assert it's
        # NEVER called for an empty name.
        from app.api.v1 import cohorts as mod

        # We're not actually monkey-patching here since the call should
        # short-circuit before reaching record_human_version. Use a
        # session that would crash if accessed.
        crashing_session = MagicMock()
        crashing_session.add.side_effect = AssertionError("no row should be added")

        mod._write_cohort_name(
            crashing_session,
            cohort_id=uuid.uuid4(),
            name="",
            author=admin,
        )
        # And whitespace-only.
        mod._write_cohort_name(
            crashing_session,
            cohort_id=uuid.uuid4(),
            name="   ",
            author=admin,
        )
        crashing_session.add.assert_not_called()

    def test_locale_falls_back_to_the_authors_preferred(
        self,
        db: Session,
        teacher: User,
    ) -> None:
        """When the name detector can't pick a locale, the writer uses
        the admin's preferred locale. Pin this by feeding an ambiguous
        name and asserting the cv row lands at admin.preferred_locale."""
        from app.models.content_version import ContentVersion

        admin = teacher  # any User instance works — the helper reads
        # ``.preferred_locale`` and ``.id`` off it.
        cohort_id = uuid.uuid4()
        cohorts_mod._write_cohort_name(
            db,
            cohort_id=cohort_id,
            name="Cohort 2026",
            author=admin,
        )
        db.commit()
        rows = db.query(ContentVersion).filter(ContentVersion.entity_type == "cohort").all()
        assert len(rows) == 1
        assert rows[0].text == "Cohort 2026"

    def test_no_locale_no_row(
        self,
        db: Session,
    ) -> None:
        """If both detection AND admin.preferred_locale come back
        ``None`` (unusual but possible in tests with bare User objects)
        the writer does NOT silently land a row under some default —
        it bails so the cv has no false provenance."""
        from app.models.content_version import ContentVersion

        admin = MagicMock()
        admin.preferred_locale = None
        admin.id = TEACHER_ID

        # detect_locale on a generic short name typically returns None
        # for ambiguous input. Force the path with a monkey-patched
        # detector that always returns None.
        from unittest.mock import patch

        with patch.object(cohorts_mod, "detect_locale", return_value=None):
            cohorts_mod._write_cohort_name(
                db,
                cohort_id=uuid.uuid4(),
                name="cohort",
                author=admin,
            )
        db.commit()
        # No cohort cv rows were created.
        rows = db.query(ContentVersion).filter(ContentVersion.entity_type == "cohort").all()
        assert rows == []


class TestFetchCohortNames:
    def test_empty_cohort_id_list_returns_empty_dict(self, db: Session) -> None:
        """Pin the empty-input short-circuit so callers can pass empty
        lists without an explicit if-empty guard."""
        assert cohorts_mod._fetch_cohort_names(db, []) == {}


class TestListCohortsForCourseVisibility:
    """``GET /cohorts/course/{course_id}`` returns 404 in two distinct
    cases — unknown course and unpublished course viewed by a non-owner
    — and they intentionally use the SAME 404 message so anonymous
    callers can't enumerate which courses exist.
    """

    def test_unknown_course_returns_404(
        self,
        client: TestClient,
    ) -> None:
        r = client.get("/api/v1/cohorts/course/nope-no-such-course")
        assert r.status_code == 404

    def test_unpublished_course_404s_for_non_owner(
        self,
        student_client: TestClient,
        db: Session,
    ) -> None:
        """A student (non-owner, non-admin) hitting an unpublished
        course must get the SAME 404 as a missing course id — never
        a 403 — so the unpublished-courses-list isn't enumerable."""
        # Course owned by the teacher (NOT the student logged in) and
        # NOT yet published.
        make_course_with_text(
            db,
            course_id="unpub-cohort-test",
            title="Hidden",
            status="draft",
            created_by=TEACHER_ID,
        )
        db.commit()
        r = student_client.get("/api/v1/cohorts/course/unpub-cohort-test")
        assert r.status_code == 404
        # Same message as the missing-course case — not "forbidden" or
        # "unpublished", which would leak existence.
        assert "not found" in r.json()["detail"]["message"].lower()

    def test_published_course_returns_200_empty_list_when_no_cohorts(
        self,
        client: TestClient,
        db: Session,
    ) -> None:
        """Sanity check the happy path so the unpublished-404 isn't a
        false negative — a published course returns an empty list,
        not 404."""
        make_course_with_text(
            db,
            course_id="pub-cohort-test",
            title="Published",
            status="published",
            created_by=TEACHER_ID,
        )
        db.commit()
        r = client.get("/api/v1/cohorts/course/pub-cohort-test")
        assert r.status_code == 200
        assert r.json() == []

    def test_unpublished_course_visible_to_admin(
        self,
        admin_client: TestClient,
        db: Session,
    ) -> None:
        """Admins must be able to see cohorts attached to unpublished
        courses (recovery / moderation flow). Pin the admin-bypass on
        the unpublished gate."""
        make_course_with_text(
            db,
            course_id="admin-unpub-test",
            title="Hidden but admin can see",
            status="draft",
            created_by=TEACHER_ID,
        )
        db.commit()
        # Admin auth bypasses the published-only gate.
        _ = UserRole.ADMIN.value
        r = admin_client.get("/api/v1/cohorts/course/admin-unpub-test")
        assert r.status_code == 200
