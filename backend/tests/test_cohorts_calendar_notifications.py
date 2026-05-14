"""Tests for Cohorts, Calendar Events, Notifications, and Announcements endpoints."""

import contextlib
import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy.types as _sa_types
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.announcement import Announcement
from app.models.cohort import Cohort, CohortCourse
from app.models.course import Course, Module
from app.models.course_event import CourseEvent
from app.models.enrollment import Enrollment
from app.models.notification import Notification
from tests.conftest import ADMIN_ID, STUDENT_ID, TEACHER_ID

# ---------------------------------------------------------------------------
# SQLite compatibility: Uuid.bind_processor expects uuid.UUID objects but
# routers pass plain strings for UUID path parameters.  PostgreSQL casts
# implicitly; SQLite does not.  Patch once at import time.
# ---------------------------------------------------------------------------
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

COHORT_PREFIX = "/api/v1/cohorts"
CALENDAR_PREFIX = "/api/v1/calendar"
COURSES_PREFIX = "/api/v1/courses"
NOTIFICATION_PREFIX = "/api/v1/notifications"
ANNOUNCEMENT_PREFIX = "/api/v1/announcements"

NOW = datetime.now(UTC)
TOMORROW = NOW + timedelta(days=1)
NEXT_WEEK = NOW + timedelta(weeks=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_course(db: Session, *, course_id: str = "test-course-1", owner_id=TEACHER_ID) -> Course:
    course = Course(
        id=course_id,
        title="Test Course",
        description="A test course",
        status="published",
        created_by=owner_id,
        quiz_weight=30,
        assignment_weight=50,
        participation_weight=20,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _seed_enrollment(
    db: Session, *, user_id=STUDENT_ID, course_id: str = "test-course-1", cohort_id=None
) -> Enrollment:
    enrollment = Enrollment(
        id=f"enroll-{uuid.uuid4().hex[:8]}",
        user_id=user_id,
        course_id=course_id,
        cohort_id=cohort_id,
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return enrollment


def _create_course_via_api(client: TestClient) -> dict:
    resp = client.post(COURSES_PREFIX, json={"title": "API Course", "description": "via API"})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _cohort_payload(**overrides) -> dict:
    data = {
        "name": "Spring 2026",
        "start_date": NOW.isoformat(),
        "end_date": NEXT_WEEK.isoformat(),
    }
    data.update(overrides)
    return data


def _event_payload(**overrides) -> dict:
    data = {
        "title": "Midterm Exam",
        "description": "Covers chapters 1-5",
        "event_type": "exam",
        "event_date": TOMORROW.isoformat(),
    }
    data.update(overrides)
    return data


def _announcement_payload(**overrides) -> dict:
    data = {
        "title": "Welcome everyone!",
        "content": "We are glad to have you in this course.",
    }
    data.update(overrides)
    return data


# ===========================================================================
# COHORT TESTS — ADR-010 top-level admin model
# ===========================================================================
#
# Cohorts are admin-owned. Creation is a two-step intent: first create an
# empty cohort (POST /cohorts), then attach courses + students via
# the junction endpoints. Teacher and student roles can READ the
# course-scoped listing (for gradebook filter / enroll dialog) but not
# write anything.


def _attach_course_via_junction(db: Session, cohort_id, course_id: str) -> None:
    """Test helper — bypass the API to attach a course directly. Use when
    a test only needs the junction row in place and doesn't care about the
    auto-enroll side effect of the public POST endpoint."""
    db.add(CohortCourse(cohort_id=cohort_id, course_id=course_id))
    db.commit()


def _seed_cohort_with_course(db: Session, *, course_id: str = "test-course-1", **kw) -> Cohort:
    # ``created_by`` defaults to NULL — only set it explicitly in tests
    # that pull in the ``admin`` fixture. Otherwise the FK to profiles
    # would fail on tests that only seed teacher/student users.
    cohort = Cohort(
        name=kw.get("name", "X"),
        start_date=kw.get("start_date", NOW),
        end_date=kw.get("end_date", NEXT_WEEK),
        status=kw.get("status", "upcoming"),
        max_students=kw.get("max_students"),
        created_by=kw.get("created_by"),
    )
    db.add(cohort)
    db.commit()
    db.refresh(cohort)
    db.add(CohortCourse(cohort_id=cohort.id, course_id=course_id))
    db.commit()
    return cohort


class TestListCohortsForCourse:
    """``GET /cohorts/course/{id}`` — read-only, returns cohorts whose
    junction includes the course. Used by the catalog enroll dialog and
    a teacher's gradebook filter."""

    def test_empty_list(self, client: TestClient, db: Session):
        _seed_course(db)
        resp = client.get(f"{COHORT_PREFIX}/course/test-course-1")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_cohorts_via_junction(self, client: TestClient, db: Session):
        _seed_course(db)
        _seed_cohort_with_course(db, course_id="test-course-1", name="Cohort A")
        _seed_cohort_with_course(db, course_id="test-course-1", name="Cohort B")

        resp = client.get(f"{COHORT_PREFIX}/course/test-course-1")
        assert resp.status_code == 200
        names = {c["name"] for c in resp.json()}
        assert names == {"Cohort A", "Cohort B"}

    def test_does_not_return_cohorts_from_unrelated_courses(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1")
        _seed_course(db, course_id="course-2")
        _seed_cohort_with_course(db, course_id="course-1", name="One")
        _seed_cohort_with_course(db, course_id="course-2", name="Two")

        resp = client.get(f"{COHORT_PREFIX}/course/course-1")
        names = [c["name"] for c in resp.json()]
        assert names == ["One"]


class TestListAllCohorts:
    """``GET /cohorts`` — admin-wide list with optional status filter."""

    def test_empty_admin_list(self, admin_client: TestClient):
        resp = admin_client.get(COHORT_PREFIX)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_all_cohorts_ordered_by_start_date_desc(self, admin_client: TestClient, db: Session):
        _seed_course(db)
        older = NOW - timedelta(days=30)
        newer = NOW - timedelta(days=5)
        _seed_cohort_with_course(db, name="Older", start_date=older)
        _seed_cohort_with_course(db, name="Newer", start_date=newer)

        resp = admin_client.get(COHORT_PREFIX)
        assert resp.status_code == 200
        names = [c["name"] for c in resp.json()]
        assert names == ["Newer", "Older"]

    def test_status_filter_returns_only_matching(self, admin_client: TestClient, db: Session):
        _seed_course(db)
        _seed_cohort_with_course(db, name="Upcoming One", status="upcoming")
        _seed_cohort_with_course(db, name="Active One", status="active")
        _seed_cohort_with_course(db, name="Completed One", status="completed")

        resp = admin_client.get(COHORT_PREFIX, params={"status": "active"})
        assert resp.status_code == 200
        names = [c["name"] for c in resp.json()]
        assert names == ["Active One"]

    def test_serializes_course_ids_and_student_count(self, admin_client: TestClient, db: Session, student):
        _seed_course(db, course_id="c-1")
        _seed_course(db, course_id="c-2")
        cohort = _seed_cohort_with_course(db, course_id="c-1", name="N")
        # Attach second course + enrol the student in both.
        db.add(CohortCourse(cohort_id=cohort.id, course_id="c-2"))
        _seed_enrollment(db, course_id="c-1", cohort_id=cohort.id)
        _seed_enrollment(db, course_id="c-2", cohort_id=cohort.id)
        db.commit()

        resp = admin_client.get(COHORT_PREFIX)
        body = resp.json()
        assert len(body) == 1
        # student_count counts DISTINCT users — one student in two courses = 1.
        assert body[0]["student_count"] == 1
        assert set(body[0]["course_ids"]) == {"c-1", "c-2"}

    def test_teacher_cannot_list(self, client: TestClient):
        resp = client.get(COHORT_PREFIX)
        assert resp.status_code == 403

    def test_student_cannot_list(self, student_client: TestClient):
        resp = student_client.get(COHORT_PREFIX)
        assert resp.status_code == 403


class TestGetCohort:
    """``GET /cohorts/{id}`` — single-fetch with computed course_ids +
    student_count."""

    def test_admin_gets_cohort_with_computed_fields(self, admin_client: TestClient, db: Session, student):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db, name="Spring")
        _seed_enrollment(db, course_id="test-course-1", cohort_id=cohort.id)

        resp = admin_client.get(f"{COHORT_PREFIX}/{cohort.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Spring"
        assert body["course_ids"] == ["test-course-1"]
        assert body["student_count"] == 1

    def test_nonexistent_returns_404(self, admin_client: TestClient):
        resp = admin_client.get(f"{COHORT_PREFIX}/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_teacher_cannot_get(self, client: TestClient, db: Session):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db)
        resp = client.get(f"{COHORT_PREFIX}/{cohort.id}")
        assert resp.status_code == 403

    def test_student_cannot_get(self, student_client: TestClient, db: Session):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db)
        resp = student_client.get(f"{COHORT_PREFIX}/{cohort.id}")
        assert resp.status_code == 403


class TestListCohortCourses:
    """``GET /cohorts/{id}/courses`` — plain list[str] junction reader."""

    def test_returns_attached_course_ids(self, admin_client: TestClient, db: Session):
        _seed_course(db, course_id="c-A")
        _seed_course(db, course_id="c-B")
        cohort = _seed_cohort_with_course(db, course_id="c-A")
        db.add(CohortCourse(cohort_id=cohort.id, course_id="c-B"))
        db.commit()

        resp = admin_client.get(f"{COHORT_PREFIX}/{cohort.id}/courses")
        assert resp.status_code == 200
        assert set(resp.json()) == {"c-A", "c-B"}

    def test_empty_when_no_courses_attached(self, admin_client: TestClient, db: Session):
        # Cohort with no junction rows
        cohort = Cohort(name="Empty", start_date=NOW, end_date=NEXT_WEEK)
        db.add(cohort)
        db.commit()
        db.refresh(cohort)

        resp = admin_client.get(f"{COHORT_PREFIX}/{cohort.id}/courses")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_nonexistent_cohort_returns_404(self, admin_client: TestClient):
        resp = admin_client.get(f"{COHORT_PREFIX}/{uuid.uuid4()}/courses")
        assert resp.status_code == 404

    def test_teacher_cannot_list(self, client: TestClient, db: Session):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db)
        resp = client.get(f"{COHORT_PREFIX}/{cohort.id}/courses")
        assert resp.status_code == 403


class TestCreateCohort:
    """``POST /cohorts`` — admin-only, creates an empty cohort. Courses
    and students are attached separately."""

    def test_admin_creates_empty_cohort(self, admin_client: TestClient):
        resp = admin_client.post(COHORT_PREFIX, json=_cohort_payload())
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Spring 2026"
        assert body["status"] == "upcoming"
        assert body["course_ids"] == []
        assert body["student_count"] == 0
        assert body["created_by"] == str(ADMIN_ID)

    def test_teacher_cannot_create(self, client: TestClient):
        resp = client.post(COHORT_PREFIX, json=_cohort_payload())
        assert resp.status_code == 403

    def test_student_cannot_create(self, student_client: TestClient):
        resp = student_client.post(COHORT_PREFIX, json=_cohort_payload())
        assert resp.status_code == 403

    def test_missing_name_returns_422(self, admin_client: TestClient):
        resp = admin_client.post(
            COHORT_PREFIX,
            json={"start_date": NOW.isoformat(), "end_date": NEXT_WEEK.isoformat()},
        )
        assert resp.status_code == 422


class TestUpdateCohort:
    def test_admin_updates_name(self, admin_client: TestClient, db: Session):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db, name="Old")
        resp = admin_client.patch(f"{COHORT_PREFIX}/{cohort.id}", json={"name": "Fall 2026"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Fall 2026"

    def test_admin_updates_status(self, admin_client: TestClient, db: Session):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db)
        resp = admin_client.patch(f"{COHORT_PREFIX}/{cohort.id}", json={"status": "active"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_update_nonexistent_returns_404(self, admin_client: TestClient):
        resp = admin_client.patch(f"{COHORT_PREFIX}/{uuid.uuid4()}", json={"name": "Nope"})
        assert resp.status_code == 404

    def test_teacher_cannot_update(self, client: TestClient, db: Session):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db)
        resp = client.patch(f"{COHORT_PREFIX}/{cohort.id}", json={"name": "Hacked"})
        assert resp.status_code == 403


class TestDeleteCohort:
    def test_admin_deletes_cohort_and_orphans_enrollments(self, admin_client: TestClient, db: Session, student):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db)
        _seed_enrollment(db, course_id="test-course-1", cohort_id=cohort.id)

        resp = admin_client.delete(f"{COHORT_PREFIX}/{cohort.id}")
        assert resp.status_code == 204

        # Cohort row gone, junction cascaded, but enrollment row survives
        # with cohort_id set to NULL (orphan = solo) — historical grade
        # data is intentionally preserved.
        assert db.query(Cohort).filter(Cohort.id == cohort.id).first() is None
        assert db.query(CohortCourse).filter(CohortCourse.cohort_id == cohort.id).count() == 0
        surviving = db.query(Enrollment).filter(Enrollment.user_id == STUDENT_ID).all()
        assert len(surviving) == 1
        assert surviving[0].cohort_id is None

    def test_delete_nonexistent_returns_404(self, admin_client: TestClient):
        resp = admin_client.delete(f"{COHORT_PREFIX}/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_student_cannot_delete(self, student_client: TestClient, db: Session):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db)
        resp = student_client.delete(f"{COHORT_PREFIX}/{cohort.id}")
        assert resp.status_code == 403


class TestAttachCourse:
    def test_attach_creates_junction_row(self, admin_client: TestClient, db: Session):
        _seed_course(db)
        cohort_resp = admin_client.post(COHORT_PREFIX, json=_cohort_payload())
        cohort_id = cohort_resp.json()["id"]

        resp = admin_client.post(
            f"{COHORT_PREFIX}/{cohort_id}/courses",
            json={"course_id": "test-course-1"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["course_ids"] == ["test-course-1"]

    def test_attach_auto_enrolls_existing_cohort_students(self, admin_client: TestClient, db: Session, student):
        # Two courses exist. Cohort starts attached to course-1 with one
        # student. Attaching course-2 should auto-create an enrollment.
        _seed_course(db, course_id="course-1")
        _seed_course(db, course_id="course-2")
        cohort = _seed_cohort_with_course(db, course_id="course-1")
        _seed_enrollment(db, course_id="course-1", cohort_id=cohort.id)

        resp = admin_client.post(f"{COHORT_PREFIX}/{cohort.id}/courses", json={"course_id": "course-2"})
        assert resp.status_code == 201
        new_enrollment = (
            db.query(Enrollment).filter(Enrollment.user_id == STUDENT_ID, Enrollment.course_id == "course-2").first()
        )
        assert new_enrollment is not None
        assert new_enrollment.cohort_id == cohort.id

    def test_attach_is_idempotent(self, admin_client: TestClient, db: Session):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db)  # course already attached
        resp = admin_client.post(f"{COHORT_PREFIX}/{cohort.id}/courses", json={"course_id": "test-course-1"})
        assert resp.status_code == 201
        assert resp.json()["course_ids"] == ["test-course-1"]

    def test_attach_nonexistent_course_returns_404(self, admin_client: TestClient, db: Session):
        cohort_resp = admin_client.post(COHORT_PREFIX, json=_cohort_payload())
        resp = admin_client.post(
            f"{COHORT_PREFIX}/{cohort_resp.json()['id']}/courses",
            json={"course_id": "no-such-course"},
        )
        assert resp.status_code == 404


class TestDetachCourse:
    def test_detach_orphans_enrollments_to_null_cohort(self, admin_client: TestClient, db: Session, student):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db)
        _seed_enrollment(db, course_id="test-course-1", cohort_id=cohort.id)

        resp = admin_client.delete(f"{COHORT_PREFIX}/{cohort.id}/courses/test-course-1")
        assert resp.status_code == 204

        # Junction row removed
        assert db.query(CohortCourse).filter(CohortCourse.cohort_id == cohort.id).count() == 0
        # Enrollment survives with cohort_id nulled — grades preserved
        surviving = db.query(Enrollment).filter(Enrollment.user_id == STUDENT_ID).all()
        assert len(surviving) == 1
        assert surviving[0].cohort_id is None

    def test_detach_nonexistent_link_is_noop(self, admin_client: TestClient, db: Session):
        _seed_course(db)
        cohort_resp = admin_client.post(COHORT_PREFIX, json=_cohort_payload())
        resp = admin_client.delete(f"{COHORT_PREFIX}/{cohort_resp.json()['id']}/courses/test-course-1")
        assert resp.status_code == 204


class TestAddStudent:
    def test_add_by_user_id_auto_enrolls_in_all_cohort_courses(self, admin_client: TestClient, db: Session, student):
        _seed_course(db, course_id="course-1")
        _seed_course(db, course_id="course-2")
        cohort = _seed_cohort_with_course(db, course_id="course-1")
        _attach_course_via_junction(db, cohort.id, "course-2")

        resp = admin_client.post(f"{COHORT_PREFIX}/{cohort.id}/students", json={"user_id": str(STUDENT_ID)})
        assert resp.status_code == 201
        enrollments = (
            db.query(Enrollment).filter(Enrollment.user_id == STUDENT_ID, Enrollment.cohort_id == cohort.id).all()
        )
        assert {e.course_id for e in enrollments} == {"course-1", "course-2"}

    def test_add_by_email(self, admin_client: TestClient, db: Session, student):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db)
        resp = admin_client.post(f"{COHORT_PREFIX}/{cohort.id}/students", json={"email": "student@example.com"})
        assert resp.status_code == 201

    def test_add_unknown_email_returns_404(self, admin_client: TestClient, db: Session):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db)
        resp = admin_client.post(f"{COHORT_PREFIX}/{cohort.id}/students", json={"email": "nobody@example.com"})
        assert resp.status_code == 404

    def test_add_without_user_id_or_email_returns_400(self, admin_client: TestClient, db: Session):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db)
        resp = admin_client.post(f"{COHORT_PREFIX}/{cohort.id}/students", json={})
        assert resp.status_code == 400

    def test_max_students_capacity_rejects_new(self, admin_client: TestClient, db: Session, student, teacher):
        # Capacity = 1. Pre-seed one enrollment so the cohort is full,
        # then try to add a different student via the API → 403.
        _seed_course(db)
        cohort = _seed_cohort_with_course(db, max_students=1)
        _seed_enrollment(db, user_id=TEACHER_ID, course_id="test-course-1", cohort_id=cohort.id)

        resp = admin_client.post(f"{COHORT_PREFIX}/{cohort.id}/students", json={"user_id": str(STUDENT_ID)})
        assert resp.status_code == 403
        assert "capacity" in resp.json()["detail"].lower()


class TestRemoveStudent:
    def test_remove_nulls_cohort_id_on_enrollments(self, admin_client: TestClient, db: Session, student):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db)
        _seed_enrollment(db, course_id="test-course-1", cohort_id=cohort.id)

        resp = admin_client.delete(f"{COHORT_PREFIX}/{cohort.id}/students/{STUDENT_ID}")
        assert resp.status_code == 204
        surviving = db.query(Enrollment).filter(Enrollment.user_id == STUDENT_ID).all()
        assert len(surviving) == 1
        assert surviving[0].cohort_id is None


class TestCohortStudents:
    def test_empty_roster(self, admin_client: TestClient, db: Session):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db)
        resp = admin_client.get(f"{COHORT_PREFIX}/{cohort.id}/students")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_roster_per_course_shape(self, admin_client: TestClient, db: Session, student):
        _seed_course(db, course_id="course-1")
        _seed_course(db, course_id="course-2")
        cohort = _seed_cohort_with_course(db, course_id="course-1")
        _attach_course_via_junction(db, cohort.id, "course-2")
        _seed_enrollment(db, course_id="course-1", cohort_id=cohort.id)
        _seed_enrollment(db, course_id="course-2", cohort_id=cohort.id)

        resp = admin_client.get(f"{COHORT_PREFIX}/{cohort.id}/students")
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["user_id"] == str(STUDENT_ID)
        assert set(rows[0]["per_course"].keys()) == {"course-1", "course-2"}

    def test_nonexistent_cohort_returns_404(self, admin_client: TestClient):
        resp = admin_client.get(f"{COHORT_PREFIX}/{uuid.uuid4()}/students")
        assert resp.status_code == 404

    def test_student_cannot_view_roster(self, student_client: TestClient, db: Session):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db)
        resp = student_client.get(f"{COHORT_PREFIX}/{cohort.id}/students")
        assert resp.status_code == 403


class TestCompleteCohort:
    def test_admin_completes_cohort(self, admin_client: TestClient, db: Session):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db)
        resp = admin_client.post(f"{COHORT_PREFIX}/{cohort.id}/complete")
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    def test_already_completed_returns_400(self, admin_client: TestClient, db: Session):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db, status="completed")
        resp = admin_client.post(f"{COHORT_PREFIX}/{cohort.id}/complete")
        assert resp.status_code == 400

    def test_nonexistent_returns_404(self, admin_client: TestClient):
        resp = admin_client.post(f"{COHORT_PREFIX}/{uuid.uuid4()}/complete")
        assert resp.status_code == 404

    def test_student_cannot_complete(self, student_client: TestClient, db: Session):
        _seed_course(db)
        cohort = _seed_cohort_with_course(db)
        resp = student_client.post(f"{COHORT_PREFIX}/{cohort.id}/complete")
        assert resp.status_code == 403


class TestSoloEnrollmentAccessMode:
    """ADR-010 §1: ``access_mode='institute'`` blocks the solo-enroll
    path (no cohort_id in the request body). Cohort-route enrollment
    still works — that's the director's explicit invitation."""

    def test_solo_enroll_on_institute_course_returns_403(self, student_client: TestClient, db: Session, student):
        course = Course(
            id="institute-course",
            title="Greek 1",
            status="published",
            access_mode="institute",
            created_by=TEACHER_ID,
        )
        db.add(course)
        db.commit()

        resp = student_client.post(f"{COURSES_PREFIX}/{course.id}/enroll", json={})
        assert resp.status_code == 403
        assert "invitation" in resp.json()["detail"].lower()

    def test_solo_enroll_on_public_course_succeeds(self, student_client: TestClient, db: Session, student):
        course = Course(
            id="public-course",
            title="Jubilee Overview",
            status="published",
            access_mode="public",
            created_by=TEACHER_ID,
        )
        db.add(course)
        db.commit()

        resp = student_client.post(f"{COURSES_PREFIX}/{course.id}/enroll", json={})
        assert resp.status_code == 200, resp.text


# ===========================================================================
# CALENDAR / COURSE EVENT TESTS
# ===========================================================================


class TestCalendarAggregatedEvents:
    def test_no_enrollments_returns_empty(self, client: TestClient):
        resp = client.get(f"{CALENDAR_PREFIX}/events")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_course_events_for_enrolled_user(self, client: TestClient, db: Session):
        course = _create_course_via_api(client)
        cid = course["id"]
        _seed_enrollment(db, user_id=TEACHER_ID, course_id=cid)

        client.post(f"{COURSES_PREFIX}/{cid}/events", json=_event_payload())

        resp = client.get(f"{CALENDAR_PREFIX}/events")
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) >= 1
        sources = {e["source"] for e in events}
        assert "course_event" in sources

    def test_filter_by_course_id(self, client: TestClient, db: Session):
        c1 = _create_course_via_api(client)
        c2_resp = client.post(COURSES_PREFIX, json={"title": "Other", "description": "x"})
        c2 = c2_resp.json()

        _seed_enrollment(db, user_id=TEACHER_ID, course_id=c1["id"])
        _seed_enrollment(db, user_id=TEACHER_ID, course_id=c2["id"])

        client.post(f"{COURSES_PREFIX}/{c1['id']}/events", json=_event_payload(title="E1"))
        client.post(f"{COURSES_PREFIX}/{c2['id']}/events", json=_event_payload(title="E2"))

        resp = client.get(f"{CALENDAR_PREFIX}/events", params={"course_id": c1["id"]})
        assert resp.status_code == 200
        titles = [e["title"] for e in resp.json()]
        assert "E1" in titles
        assert "E2" not in titles

    def test_includes_module_deadlines(self, client: TestClient, db: Session):
        course = _create_course_via_api(client)
        cid = course["id"]
        _seed_enrollment(db, user_id=TEACHER_ID, course_id=cid)

        mod = Module(id="mod-1", course_id=cid, title="Module 1", order_index=0, due_date=TOMORROW)
        db.add(mod)
        db.commit()

        resp = client.get(f"{CALENDAR_PREFIX}/events")
        assert resp.status_code == 200
        sources = [e["source"] for e in resp.json()]
        assert "module_deadline" in sources


class TestCreateCourseEvent:
    def test_create_returns_201(self, client: TestClient):
        course = _create_course_via_api(client)
        resp = client.post(
            f"{COURSES_PREFIX}/{course['id']}/events",
            json=_event_payload(),
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "Midterm Exam"
        assert body["event_type"] == "exam"
        assert body["course_id"] == course["id"]
        assert body["created_by"] == str(TEACHER_ID)

    def test_student_cannot_create_event(self, student_client: TestClient, db: Session):
        _seed_course(db)
        resp = student_client.post(
            f"{COURSES_PREFIX}/test-course-1/events",
            json=_event_payload(),
        )
        assert resp.status_code == 403

    def test_create_for_nonexistent_course(self, client: TestClient):
        resp = client.post(
            f"{COURSES_PREFIX}/no-such-course/events",
            json=_event_payload(),
        )
        assert resp.status_code == 404

    def test_create_missing_title_returns_422(self, client: TestClient):
        course = _create_course_via_api(client)
        resp = client.post(
            f"{COURSES_PREFIX}/{course['id']}/events",
            json={"event_date": TOMORROW.isoformat()},
        )
        assert resp.status_code == 422


class TestListCourseEvents:
    def test_owner_can_list(self, client: TestClient):
        course = _create_course_via_api(client)
        client.post(f"{COURSES_PREFIX}/{course['id']}/events", json=_event_payload(title="E1"))
        client.post(f"{COURSES_PREFIX}/{course['id']}/events", json=_event_payload(title="E2"))

        resp = client.get(f"{COURSES_PREFIX}/{course['id']}/events")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_enrolled_student_can_list(self, student_client: TestClient, db: Session):
        _seed_course(db)
        _seed_enrollment(db, user_id=STUDENT_ID, course_id="test-course-1")

        ev = CourseEvent(
            course_id="test-course-1",
            title="Lecture",
            event_type="live_session",
            event_date=TOMORROW,
            created_by=TEACHER_ID,
        )
        db.add(ev)
        db.commit()

        resp = student_client.get(f"{COURSES_PREFIX}/test-course-1/events")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_unenrolled_student_gets_403(self, student_client: TestClient, db: Session):
        _seed_course(db)
        resp = student_client.get(f"{COURSES_PREFIX}/test-course-1/events")
        assert resp.status_code == 403

    def test_nonexistent_course_returns_404(self, client: TestClient):
        resp = client.get(f"{COURSES_PREFIX}/no-such-course/events")
        assert resp.status_code == 404

    def test_empty_events_list(self, client: TestClient):
        course = _create_course_via_api(client)
        resp = client.get(f"{COURSES_PREFIX}/{course['id']}/events")
        assert resp.status_code == 200
        assert resp.json() == []


class TestUpdateCourseEvent:
    def _setup(self, client):
        course = _create_course_via_api(client)
        resp = client.post(
            f"{COURSES_PREFIX}/{course['id']}/events",
            json=_event_payload(),
        )
        event = resp.json()
        return course["id"], event["id"]

    def test_update_title(self, client: TestClient):
        course_id, event_id = self._setup(client)
        resp = client.put(
            f"{COURSES_PREFIX}/{course_id}/events/{event_id}",
            json={"title": "Final Exam"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Final Exam"

    def test_update_event_type(self, client: TestClient):
        course_id, event_id = self._setup(client)
        resp = client.put(
            f"{COURSES_PREFIX}/{course_id}/events/{event_id}",
            json={"event_type": "live_session"},
        )
        assert resp.status_code == 200
        assert resp.json()["event_type"] == "live_session"

    def test_update_nonexistent_event_returns_404(self, client: TestClient):
        course = _create_course_via_api(client)
        resp = client.put(
            f"{COURSES_PREFIX}/{course['id']}/events/{uuid.uuid4()}",
            json={"title": "Nope"},
        )
        assert resp.status_code == 404

    def test_student_cannot_update(self, student_client: TestClient, db: Session):
        _seed_course(db)
        ev = CourseEvent(
            course_id="test-course-1",
            title="Lecture",
            event_type="other",
            event_date=TOMORROW,
            created_by=TEACHER_ID,
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)

        resp = student_client.put(
            f"{COURSES_PREFIX}/test-course-1/events/{ev.id}",
            json={"title": "Hacked"},
        )
        assert resp.status_code == 403


class TestDeleteCourseEvent:
    def test_delete_returns_204(self, client: TestClient):
        course = _create_course_via_api(client)
        resp = client.post(
            f"{COURSES_PREFIX}/{course['id']}/events",
            json=_event_payload(),
        )
        event_id = resp.json()["id"]

        resp = client.delete(f"{COURSES_PREFIX}/{course['id']}/events/{event_id}")
        assert resp.status_code == 204

        resp = client.get(f"{COURSES_PREFIX}/{course['id']}/events")
        assert resp.json() == []

    def test_delete_nonexistent_returns_404(self, client: TestClient):
        course = _create_course_via_api(client)
        resp = client.delete(f"{COURSES_PREFIX}/{course['id']}/events/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_student_cannot_delete(self, student_client: TestClient, db: Session):
        _seed_course(db)
        ev = CourseEvent(
            course_id="test-course-1",
            title="Lecture",
            event_type="other",
            event_date=TOMORROW,
            created_by=TEACHER_ID,
        )
        db.add(ev)
        db.commit()
        db.refresh(ev)

        resp = student_client.delete(f"{COURSES_PREFIX}/test-course-1/events/{ev.id}")
        assert resp.status_code == 403


# ===========================================================================
# NOTIFICATION TESTS
# ===========================================================================


def _seed_notification(db: Session, *, user_id=TEACHER_ID, is_read=False, title="Test Notification") -> Notification:
    n = Notification(
        user_id=user_id,
        type="info",
        title=title,
        message="Test message body",
        is_read=is_read,
    )
    db.add(n)
    db.commit()
    db.refresh(n)
    return n


class TestListNotifications:
    def test_empty_list(self, client: TestClient):
        resp = client.get(NOTIFICATION_PREFIX)
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_returns_user_notifications(self, client: TestClient, db: Session):
        _seed_notification(db, user_id=TEACHER_ID, title="N1")
        _seed_notification(db, user_id=TEACHER_ID, title="N2")

        resp = client.get(NOTIFICATION_PREFIX)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    def test_does_not_return_other_users_notifications(self, client: TestClient, db: Session, student):
        _seed_notification(db, user_id=TEACHER_ID, title="Mine")
        _seed_notification(db, user_id=STUDENT_ID, title="Theirs")

        resp = client.get(NOTIFICATION_PREFIX)
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["title"] == "Mine"

    def test_pagination(self, client: TestClient, db: Session):
        for i in range(5):
            _seed_notification(db, user_id=TEACHER_ID, title=f"N{i}")

        resp = client.get(NOTIFICATION_PREFIX, params={"page": 1, "page_size": 2})
        body = resp.json()
        assert body["total"] == 5
        assert len(body["items"]) == 2
        assert body["page"] == 1
        assert body["page_size"] == 2

        resp = client.get(NOTIFICATION_PREFIX, params={"page": 3, "page_size": 2})
        body = resp.json()
        assert len(body["items"]) == 1


class TestUnreadCount:
    def test_zero_when_none(self, client: TestClient):
        resp = client.get(f"{NOTIFICATION_PREFIX}/unread-count")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0

    def test_counts_only_unread(self, client: TestClient, db: Session):
        _seed_notification(db, user_id=TEACHER_ID, is_read=False)
        _seed_notification(db, user_id=TEACHER_ID, is_read=False)
        _seed_notification(db, user_id=TEACHER_ID, is_read=True)

        resp = client.get(f"{NOTIFICATION_PREFIX}/unread-count")
        assert resp.json()["count"] == 2

    def test_ignores_other_users(self, client: TestClient, db: Session, student):
        _seed_notification(db, user_id=TEACHER_ID, is_read=False)
        _seed_notification(db, user_id=STUDENT_ID, is_read=False)

        resp = client.get(f"{NOTIFICATION_PREFIX}/unread-count")
        assert resp.json()["count"] == 1


class TestMarkOneRead:
    def test_marks_as_read(self, client: TestClient, db: Session):
        n = _seed_notification(db, user_id=TEACHER_ID, is_read=False)

        resp = client.patch(f"{NOTIFICATION_PREFIX}/{n.id}/read")
        assert resp.status_code == 200
        assert resp.json()["is_read"] is True

    def test_already_read_stays_read(self, client: TestClient, db: Session):
        n = _seed_notification(db, user_id=TEACHER_ID, is_read=True)

        resp = client.patch(f"{NOTIFICATION_PREFIX}/{n.id}/read")
        assert resp.status_code == 200
        assert resp.json()["is_read"] is True

    def test_nonexistent_returns_404(self, client: TestClient):
        resp = client.patch(f"{NOTIFICATION_PREFIX}/{uuid.uuid4()}/read")
        assert resp.status_code == 404

    def test_cannot_mark_other_users_notification(self, client: TestClient, db: Session, student):
        n = _seed_notification(db, user_id=STUDENT_ID, is_read=False)

        resp = client.patch(f"{NOTIFICATION_PREFIX}/{n.id}/read")
        assert resp.status_code == 404


class TestMarkAllRead:
    def test_marks_all_read(self, client: TestClient, db: Session):
        _seed_notification(db, user_id=TEACHER_ID, is_read=False)
        _seed_notification(db, user_id=TEACHER_ID, is_read=False)

        resp = client.post(f"{NOTIFICATION_PREFIX}/read-all")
        assert resp.status_code == 200

        resp = client.get(f"{NOTIFICATION_PREFIX}/unread-count")
        assert resp.json()["count"] == 0

    def test_does_not_affect_other_users(self, client: TestClient, db: Session, student):
        _seed_notification(db, user_id=TEACHER_ID, is_read=False)
        _seed_notification(db, user_id=STUDENT_ID, is_read=False)

        client.post(f"{NOTIFICATION_PREFIX}/read-all")

        still_unread = (
            db.query(Notification)
            .filter(
                Notification.user_id == STUDENT_ID,
                Notification.is_read == False,
            )
            .count()
        )
        assert still_unread == 1

    def test_idempotent_when_already_read(self, client: TestClient, db: Session):
        _seed_notification(db, user_id=TEACHER_ID, is_read=True)
        resp = client.post(f"{NOTIFICATION_PREFIX}/read-all")
        assert resp.status_code == 200


class TestDeleteNotification:
    def test_delete_returns_204(self, client: TestClient, db: Session):
        n = _seed_notification(db, user_id=TEACHER_ID)

        resp = client.delete(f"{NOTIFICATION_PREFIX}/{n.id}")
        assert resp.status_code == 204

        resp = client.get(NOTIFICATION_PREFIX)
        assert resp.json()["total"] == 0

    def test_delete_nonexistent_returns_404(self, client: TestClient):
        resp = client.delete(f"{NOTIFICATION_PREFIX}/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_cannot_delete_other_users_notification(self, client: TestClient, db: Session, student):
        n = _seed_notification(db, user_id=STUDENT_ID)

        resp = client.delete(f"{NOTIFICATION_PREFIX}/{n.id}")
        assert resp.status_code == 404


# ===========================================================================
# ANNOUNCEMENT TESTS
# ===========================================================================


class TestListAnnouncements:
    def test_empty_list(self, client: TestClient):
        resp = client.get(ANNOUNCEMENT_PREFIX)
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_all_announcements(self, client: TestClient):
        client.post(ANNOUNCEMENT_PREFIX, json=_announcement_payload(title="A1"))
        client.post(ANNOUNCEMENT_PREFIX, json=_announcement_payload(title="A2"))

        resp = client.get(ANNOUNCEMENT_PREFIX)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_filter_by_course_id(self, client: TestClient):
        course = _create_course_via_api(client)
        cid = course["id"]

        client.post(ANNOUNCEMENT_PREFIX, json=_announcement_payload(title="Global", course_id=None))
        client.post(ANNOUNCEMENT_PREFIX, json=_announcement_payload(title="Course-specific", course_id=cid))

        resp = client.get(ANNOUNCEMENT_PREFIX, params={"course_id": cid})
        assert resp.status_code == 200
        titles = [a["title"] for a in resp.json()]
        assert "Course-specific" in titles
        assert "Global" not in titles

    def test_no_filter_returns_all(self, client: TestClient):
        course = _create_course_via_api(client)
        client.post(ANNOUNCEMENT_PREFIX, json=_announcement_payload(title="Global"))
        client.post(ANNOUNCEMENT_PREFIX, json=_announcement_payload(title="Specific", course_id=course["id"]))

        resp = client.get(ANNOUNCEMENT_PREFIX)
        assert len(resp.json()) == 2


class TestCreateAnnouncement:
    def test_create_global_returns_201(self, client: TestClient):
        resp = client.post(ANNOUNCEMENT_PREFIX, json=_announcement_payload())
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "Welcome everyone!"
        assert body["created_by"] == str(TEACHER_ID)
        assert body["course_id"] is None

    def test_create_course_specific(self, client: TestClient):
        course = _create_course_via_api(client)
        resp = client.post(
            ANNOUNCEMENT_PREFIX,
            json=_announcement_payload(course_id=course["id"]),
        )
        assert resp.status_code == 201
        assert resp.json()["course_id"] == course["id"]

    def test_student_cannot_create(self, student_client: TestClient):
        resp = student_client.post(ANNOUNCEMENT_PREFIX, json=_announcement_payload())
        assert resp.status_code == 403

    def test_create_for_nonexistent_course_returns_404(self, client: TestClient):
        resp = client.post(
            ANNOUNCEMENT_PREFIX,
            json=_announcement_payload(course_id="nonexistent-course"),
        )
        assert resp.status_code == 404

    def test_create_missing_title_returns_422(self, client: TestClient):
        resp = client.post(
            ANNOUNCEMENT_PREFIX,
            json={"content": "no title here"},
        )
        assert resp.status_code == 422

    def test_create_missing_content_returns_422(self, client: TestClient):
        resp = client.post(
            ANNOUNCEMENT_PREFIX,
            json={"title": "no content here"},
        )
        assert resp.status_code == 422

    def test_creates_notification_for_enrolled_students(self, client: TestClient, db: Session, student):
        course = _create_course_via_api(client)
        _seed_enrollment(db, user_id=STUDENT_ID, course_id=course["id"])

        client.post(
            ANNOUNCEMENT_PREFIX,
            json=_announcement_payload(course_id=course["id"]),
        )

        notifs = (
            db.query(Notification)
            .filter(
                Notification.user_id == STUDENT_ID,
                Notification.type == "new_announcement",
            )
            .all()
        )
        assert len(notifs) == 1


class TestUpdateAnnouncement:
    def _create_announcement(self, client):
        resp = client.post(ANNOUNCEMENT_PREFIX, json=_announcement_payload())
        assert resp.status_code == 201
        return resp.json()

    def test_update_title(self, client: TestClient):
        ann = self._create_announcement(client)
        resp = client.put(
            f"{ANNOUNCEMENT_PREFIX}/{ann['id']}",
            json={"title": "Updated Title"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Title"

    def test_update_content(self, client: TestClient):
        ann = self._create_announcement(client)
        resp = client.put(
            f"{ANNOUNCEMENT_PREFIX}/{ann['id']}",
            json={"content": "Updated content"},
        )
        assert resp.status_code == 200
        assert resp.json()["content"] == "Updated content"

    def test_update_nonexistent_returns_404(self, client: TestClient):
        resp = client.put(
            f"{ANNOUNCEMENT_PREFIX}/{uuid.uuid4()}",
            json={"title": "Nope"},
        )
        assert resp.status_code == 404

    def test_student_cannot_update(self, student_client: TestClient, db: Session):
        ann = Announcement(
            id=uuid.uuid4(),
            title="Teacher Ann",
            content="Some content",
            created_by=TEACHER_ID,
        )
        db.add(ann)
        db.commit()
        db.refresh(ann)

        resp = student_client.put(
            f"{ANNOUNCEMENT_PREFIX}/{ann.id}",
            json={"title": "Hacked"},
        )
        assert resp.status_code == 403


class TestDeleteAnnouncement:
    def test_delete_returns_204(self, client: TestClient):
        resp = client.post(ANNOUNCEMENT_PREFIX, json=_announcement_payload())
        ann_id = resp.json()["id"]

        resp = client.delete(f"{ANNOUNCEMENT_PREFIX}/{ann_id}")
        assert resp.status_code == 204

        resp = client.get(ANNOUNCEMENT_PREFIX)
        assert resp.json() == []

    def test_delete_nonexistent_returns_404(self, client: TestClient):
        resp = client.delete(f"{ANNOUNCEMENT_PREFIX}/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_student_cannot_delete(self, student_client: TestClient, db: Session):
        ann = Announcement(
            id=uuid.uuid4(),
            title="Teacher Ann",
            content="Some content",
            created_by=TEACHER_ID,
        )
        db.add(ann)
        db.commit()
        db.refresh(ann)

        resp = student_client.delete(f"{ANNOUNCEMENT_PREFIX}/{ann.id}")
        assert resp.status_code == 403

    def test_teacher_cannot_delete_others_announcement(self, client: TestClient, db: Session):
        other_teacher_id = uuid.uuid4()
        from app.models.user import User, UserRole

        other = User(
            id=other_teacher_id,
            email="other-teacher@example.com",
            full_name="Other Teacher",
            role=UserRole.TEACHER.value,
        )
        db.add(other)
        db.commit()

        ann = Announcement(
            id=uuid.uuid4(),
            title="Other's Announcement",
            content="Other content",
            created_by=other_teacher_id,
        )
        db.add(ann)
        db.commit()
        db.refresh(ann)

        resp = client.delete(f"{ANNOUNCEMENT_PREFIX}/{ann.id}")
        assert resp.status_code == 403
