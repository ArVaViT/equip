"""Tests for cohort-route self-enrollment gates.

The cohort-aware ``POST /api/v1/courses/{course_id}/enroll`` path is
gated through ``_enforce_cohort_gates`` in
``app/api/v1/courses/enrollment.py``. Until now the broader cohort
test file covered the *solo-route* path (institute vs public) and the
*admin-direct* add-student path, but never exercised the
cohort-supplied ``body.cohort_id`` self-enroll variant. The gate
function had **0% coverage** despite holding six distinct
business-rule branches:

    1. cohort_id refers to a non-existent cohort  → 404
    2. cohort exists but is not linked to the course → 404
    3. cohort linked but not in ``active`` status → 403
    4. cohort linked + active but enrollment window not yet open → 403
    5. cohort linked + active but enrollment window already closed → 403
    6. cohort linked + active + open window but at capacity → 403
    all gates pass → silent (caller proceeds to enroll)

Tests in two layers:

  * **Unit-level**: drive ``_enforce_cohort_gates`` directly. This lets
    us pass an explicit ``now: datetime`` so we are not at the mercy of
    SQLite's ``DateTime(timezone=True)`` column type, which silently
    strips tz info on round-trip and would make ``now (aware) >
    end (naive)`` raise on the comparison.

  * **Integration via the route**: pinch through the full
    ``POST /enroll`` for the happy path plus the cohort-route-bypasses-
    solo-route checks (institute access, course-level window) — those
    cases don't hit the timezone-fragile branch.

Plus three solo-route tests for course-level ``enrollment_start`` /
``enrollment_end`` gates, which the existing suite only covered for
``status='draft'``. Those would be SQLite-fragile too, so they also
drive the underlying logic via the route with a monkeypatched ``now``.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import datetime, timedelta

import pytest
import sqlalchemy.types as _sa_types
from fastapi import HTTPException
from fastapi.testclient import TestClient  # noqa: TC002  (used at runtime by fixtures)
from sqlalchemy.orm import Session  # noqa: TC002  (used at runtime by fixtures)

from app.api.v1.courses.enrollment import _enforce_cohort_gates
from app.models.cohort import Cohort, CohortCourse
from app.models.course import Course
from app.models.enrollment import Enrollment
from tests.conftest import STUDENT_ID, TEACHER_ID

# SQLite compatibility: ``Uuid.bind_processor`` expects ``uuid.UUID``
# objects but FastAPI routes pass UUID values as plain ``str`` (the
# path-parameter / JSON-body shape). Postgres casts implicitly; SQLite
# does not. Patch once at import so cohort id lookups don't crash with
# ``'str' object has no attribute 'hex'``. Mirrors the pattern used by
# ``tests/test_cohorts_calendar_notifications.py``.
_orig_uuid_bp = _sa_types.Uuid.bind_processor


def _uuid_bp_accepting_strings(self, dialect):
    processor = _orig_uuid_bp(self, dialect)
    if processor is None:
        return None

    def _process(value):
        if isinstance(value, str):
            with contextlib.suppress(ValueError):
                value = uuid.UUID(value)
        return processor(value)

    return _process


_sa_types.Uuid.bind_processor = _uuid_bp_accepting_strings


COURSES_PREFIX = "/api/v1/courses"

NOW_NAIVE = datetime(2026, 5, 14, 12, 0, 0)
PAST_NAIVE = NOW_NAIVE - timedelta(days=30)
RECENT_PAST_NAIVE = NOW_NAIVE - timedelta(days=1)
NEAR_FUTURE_NAIVE = NOW_NAIVE + timedelta(days=1)
FAR_FUTURE_NAIVE = NOW_NAIVE + timedelta(days=30)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_public_course(
    db: Session,
    *,
    course_id: str = "test-course-1",
    status: str = "published",
) -> Course:
    course = Course(
        id=course_id,
        title="Test Course",
        description="A test course",
        status=status,
        access_mode="public",
        created_by=TEACHER_ID,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _seed_institute_course(db: Session, *, course_id: str = "institute-course") -> Course:
    course = Course(
        id=course_id,
        title="Greek I",
        description="Institute-only",
        status="published",
        access_mode="institute",
        created_by=TEACHER_ID,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _seed_cohort(
    db: Session,
    *,
    course_id: str | None = "test-course-1",
    status: str = "active",
    max_students: int | None = None,
    enrollment_start: datetime | None = None,
    enrollment_end: datetime | None = None,
) -> Cohort:
    cohort = Cohort(
        name="Spring 2026",
        start_date=NOW_NAIVE,
        end_date=FAR_FUTURE_NAIVE,
        status=status,
        max_students=max_students,
        enrollment_start=enrollment_start,
        enrollment_end=enrollment_end,
    )
    db.add(cohort)
    db.commit()
    db.refresh(cohort)
    if course_id is not None:
        db.add(CohortCourse(cohort_id=cohort.id, course_id=course_id))
        db.commit()
    return cohort


def _seed_enrollment(db: Session, *, user_id, course_id: str, cohort_id) -> None:
    db.add(
        Enrollment(
            id=f"enroll-{uuid.uuid4().hex[:8]}",
            user_id=user_id,
            course_id=course_id,
            cohort_id=cohort_id,
        )
    )
    db.commit()


# ===========================================================================
# UNIT TESTS — _enforce_cohort_gates(db, course_id, cohort_id, now)
# ===========================================================================
#
# Tests here drive the gate function directly so we can pass an explicit
# tz-naive ``now`` that matches the tz-naive datetimes SQLite stores.
# (PgUUID + DateTime(timezone=True) both round-trip transparently on
# Postgres but degrade on SQLite. This lets us exercise every branch
# without fighting that mismatch.)


class TestCohortGateCohortLookup:
    def test_nonexistent_cohort_id_raises_404(self, db: Session, teacher):
        _seed_public_course(db)
        with pytest.raises(HTTPException) as exc:
            _enforce_cohort_gates(db, "test-course-1", str(uuid.uuid4()), NOW_NAIVE)
        assert exc.value.status_code == 404
        assert exc.value.detail == "Cohort not found"

    def test_cohort_not_linked_to_course_raises_404(self, db: Session, teacher):
        _seed_public_course(db, course_id="course-a")
        _seed_public_course(db, course_id="course-b")
        cohort = _seed_cohort(db, course_id="course-a")
        with pytest.raises(HTTPException) as exc:
            _enforce_cohort_gates(db, "course-b", str(cohort.id), NOW_NAIVE)
        assert exc.value.status_code == 404
        assert exc.value.detail == "Cohort does not include this course"


class TestCohortGateStatus:
    def test_upcoming_cohort_raises_403(self, db: Session, teacher):
        _seed_public_course(db)
        cohort = _seed_cohort(db, status="upcoming")
        with pytest.raises(HTTPException) as exc:
            _enforce_cohort_gates(db, "test-course-1", str(cohort.id), NOW_NAIVE)
        assert exc.value.status_code == 403
        assert exc.value.detail == "Cohort is not active"

    def test_completed_cohort_raises_403(self, db: Session, teacher):
        _seed_public_course(db)
        cohort = _seed_cohort(db, status="completed")
        with pytest.raises(HTTPException) as exc:
            _enforce_cohort_gates(db, "test-course-1", str(cohort.id), NOW_NAIVE)
        assert exc.value.status_code == 403
        assert exc.value.detail == "Cohort is not active"


class TestCohortGateWindow:
    def test_window_not_yet_open_raises_403(self, db: Session, teacher):
        _seed_public_course(db)
        cohort = _seed_cohort(db, enrollment_start=NEAR_FUTURE_NAIVE)
        with pytest.raises(HTTPException) as exc:
            _enforce_cohort_gates(db, "test-course-1", str(cohort.id), NOW_NAIVE)
        assert exc.value.status_code == 403
        assert "not started yet" in exc.value.detail.lower()

    def test_window_already_closed_raises_403(self, db: Session, teacher):
        _seed_public_course(db)
        cohort = _seed_cohort(db, enrollment_end=RECENT_PAST_NAIVE)
        with pytest.raises(HTTPException) as exc:
            _enforce_cohort_gates(db, "test-course-1", str(cohort.id), NOW_NAIVE)
        assert exc.value.status_code == 403
        assert "ended" in exc.value.detail.lower()

    def test_window_open_now_passes_silently(self, db: Session, teacher):
        _seed_public_course(db)
        cohort = _seed_cohort(db, enrollment_start=PAST_NAIVE, enrollment_end=FAR_FUTURE_NAIVE)
        # No exception = pass.
        _enforce_cohort_gates(db, "test-course-1", str(cohort.id), NOW_NAIVE)

    def test_null_window_means_unlimited(self, db: Session, teacher):
        _seed_public_course(db)
        cohort = _seed_cohort(db)
        _enforce_cohort_gates(db, "test-course-1", str(cohort.id), NOW_NAIVE)


class TestCohortGateCapacity:
    def test_capacity_reached_raises_403(self, db: Session, teacher, student):
        _seed_public_course(db)
        cohort = _seed_cohort(db, max_students=1)
        _seed_enrollment(db, user_id=TEACHER_ID, course_id="test-course-1", cohort_id=cohort.id)
        with pytest.raises(HTTPException) as exc:
            _enforce_cohort_gates(db, "test-course-1", str(cohort.id), NOW_NAIVE)
        assert exc.value.status_code == 403
        assert "capacity" in exc.value.detail.lower()

    def test_capacity_counts_distinct_users_only(self, db: Session, teacher, student):
        """Two enrollment rows for the same user (one cohort, multiple
        courses) count as ONE seat — the SQL uses count(distinct user_id).
        Guards against a future ``count(*)`` regression.
        """
        _seed_public_course(db, course_id="course-a")
        _seed_public_course(db, course_id="course-b")
        cohort = _seed_cohort(db, course_id="course-a", max_students=2)
        db.add(CohortCourse(cohort_id=cohort.id, course_id="course-b"))
        db.commit()
        _seed_enrollment(db, user_id=TEACHER_ID, course_id="course-a", cohort_id=cohort.id)
        _seed_enrollment(db, user_id=TEACHER_ID, course_id="course-b", cohort_id=cohort.id)

        # 1 distinct user against cap of 2 → seat available.
        _enforce_cohort_gates(db, "course-a", str(cohort.id), NOW_NAIVE)

    def test_unlimited_capacity_when_max_students_null(self, db: Session, teacher, student):
        _seed_public_course(db)
        cohort = _seed_cohort(db, max_students=None)
        _seed_enrollment(db, user_id=TEACHER_ID, course_id="test-course-1", cohort_id=cohort.id)
        _enforce_cohort_gates(db, "test-course-1", str(cohort.id), NOW_NAIVE)


# ===========================================================================
# ROUTE-LEVEL TESTS — POST /api/v1/courses/{id}/enroll
# ===========================================================================
#
# These run through the FastAPI route. We focus on cases that don't
# involve datetime comparisons (status checks, access-mode bypass,
# happy path) so the SQLite tz round-trip never fires.


class TestEnrollRouteCohortStatusPath:
    """Round-trips a *single* gate (status) through the full router so
    we know dependency wiring + JSON body parsing + 403 propagation
    actually compose correctly. The remaining gates are covered at the
    unit level above."""

    def test_upcoming_cohort_returns_403(self, student_client: TestClient, db: Session, student):
        _seed_public_course(db)
        cohort = _seed_cohort(db, status="upcoming")

        resp = student_client.post(
            f"{COURSES_PREFIX}/test-course-1/enroll",
            json={"cohort_id": str(cohort.id)},
        )
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Cohort is not active"

    def test_nonexistent_cohort_returns_404(self, student_client: TestClient, db: Session, student):
        _seed_public_course(db)
        resp = student_client.post(
            f"{COURSES_PREFIX}/test-course-1/enroll",
            json={"cohort_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Cohort not found"

    def test_no_partial_enrollment_when_gate_fails(self, student_client: TestClient, db: Session, student):
        """Negative-path side-effect check: a failed gate must not leak
        a partial enrollment row. Easy to regress if a future refactor
        moves ``enroll_user_in_course`` ahead of the gate check."""
        _seed_public_course(db)
        before = db.query(Enrollment).count()

        student_client.post(
            f"{COURSES_PREFIX}/test-course-1/enroll",
            json={"cohort_id": str(uuid.uuid4())},
        )
        after = db.query(Enrollment).count()
        assert after == before


class TestEnrollRouteCohortBypassesSoloGates:
    """The cohort-route enroll explicitly bypasses the solo-route
    institute-access block — cohort membership IS the director's
    invitation (ADR-010 §1)."""

    def test_institute_course_allows_cohort_enrollment(self, student_client: TestClient, db: Session, student):
        _seed_institute_course(db)
        cohort = _seed_cohort(db, course_id="institute-course")

        resp = student_client.post(
            f"{COURSES_PREFIX}/institute-course/enroll",
            json={"cohort_id": str(cohort.id)},
        )
        assert resp.status_code == 200, resp.text


class TestEnrollRouteCohortHappyPath:
    def test_enrollment_row_records_cohort_id(self, student_client: TestClient, db: Session, student):
        _seed_public_course(db)
        cohort = _seed_cohort(db)

        resp = student_client.post(
            f"{COURSES_PREFIX}/test-course-1/enroll",
            json={"cohort_id": str(cohort.id)},
        )
        assert resp.status_code == 200, resp.text

        rows = (
            db.query(Enrollment).filter(Enrollment.user_id == STUDENT_ID, Enrollment.course_id == "test-course-1").all()
        )
        assert len(rows) == 1
        assert str(rows[0].cohort_id) == str(cohort.id)


# ===========================================================================
# SOLO ROUTE — course-level status gates (no datetime needed)
# ===========================================================================


class TestEnrollmentStatusRoute:
    """``GET /api/v1/courses/{course_id}/enrollment-status`` — the
    lightweight yes/no probe used by the catalog detail page so it
    doesn't have to pull ``/users/me/courses``. Two branches:
    enrolled vs not, plus the cohort_id surfaces only when set."""

    def test_returns_not_enrolled_when_no_row(self, student_client: TestClient, db: Session, student):
        _seed_public_course(db)
        resp = student_client.get(f"{COURSES_PREFIX}/test-course-1/enrollment-status")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"enrolled": False, "enrollment": None}

    def test_returns_enrolled_when_row_exists(self, student_client: TestClient, db: Session, student):
        _seed_public_course(db)
        _seed_enrollment(db, user_id=STUDENT_ID, course_id="test-course-1", cohort_id=None)
        resp = student_client.get(f"{COURSES_PREFIX}/test-course-1/enrollment-status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["enrolled"] is True
        assert body["enrollment"]["course_id"] == "test-course-1"
        assert body["enrollment"]["cohort_id"] is None

    def test_returns_cohort_id_when_enrolled_via_cohort(self, student_client: TestClient, db: Session, student):
        _seed_public_course(db)
        cohort = _seed_cohort(db)
        _seed_enrollment(db, user_id=STUDENT_ID, course_id="test-course-1", cohort_id=cohort.id)
        resp = student_client.get(f"{COURSES_PREFIX}/test-course-1/enrollment-status")
        assert resp.status_code == 200
        assert resp.json()["enrollment"]["cohort_id"] == str(cohort.id)


class TestSoloEnrollRouteStatusGates:
    def test_solo_enroll_on_draft_course_returns_403(self, student_client: TestClient, db: Session, student):
        _seed_public_course(db, status="draft")
        resp = student_client.post(
            f"{COURSES_PREFIX}/test-course-1/enroll",
            json={},
        )
        assert resp.status_code == 403
        assert "unpublished" in resp.json()["detail"].lower()

    def test_solo_enroll_on_archived_course_returns_403(self, student_client: TestClient, db: Session, student):
        _seed_public_course(db, status="archived")
        resp = student_client.post(
            f"{COURSES_PREFIX}/test-course-1/enroll",
            json={},
        )
        assert resp.status_code == 403
        assert "unpublished" in resp.json()["detail"].lower()

    def test_solo_enroll_on_nonexistent_course_returns_404(self, student_client: TestClient, db: Session, student):
        resp = student_client.post(
            f"{COURSES_PREFIX}/nope-doesnt-exist/enroll",
            json={},
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()
