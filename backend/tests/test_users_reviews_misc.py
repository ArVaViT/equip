"""Comprehensive tests for Users, Reviews, Prerequisites, Analytics,
Health, Audit, and Modules/Chapters endpoints.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_optional_user, require_admin, require_teacher
from app.core.database import get_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.certificate import Certificate
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.prerequisite import CoursePrerequisite
from app.models.review import CourseReview
from app.models.user import User, UserRole
from tests.conftest import STUDENT_ID, TEACHER_ID

ADMIN_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_admin(db: Session) -> User:
    admin = User(
        id=ADMIN_ID,
        email="admin@example.com",
        full_name="Test Admin",
        role=UserRole.ADMIN.value,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def _seed_course(
    db: Session, course_id: str = "course-1", *, owner=TEACHER_ID, status: str = "published", title: str = "Test Course"
) -> Course:
    course = Course(
        id=course_id,
        title=title,
        description="A course for testing",
        status=status,
        created_by=owner,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _seed_module(db: Session, course_id: str = "course-1", module_id: str = "mod-1", title: str = "Module 1") -> Module:
    module = Module(id=module_id, course_id=course_id, title=title, order_index=0)
    db.add(module)
    db.commit()
    db.refresh(module)
    return module


def _seed_chapter(
    db: Session, module_id: str = "mod-1", chapter_id: str = "chap-1", title: str = "Chapter 1"
) -> Chapter:
    chapter = Chapter(id=chapter_id, module_id=module_id, title=title, order_index=0)
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter


def _seed_enrollment(db: Session, user_id=STUDENT_ID, course_id: str = "course-1", progress: int = 0) -> Enrollment:
    enrollment = Enrollment(
        id=str(uuid.uuid4()),
        user_id=user_id,
        course_id=course_id,
        progress=progress,
    )
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return enrollment


def _seed_certificate(
    db: Session, user_id=STUDENT_ID, course_id: str = "course-1", status: str = "approved"
) -> Certificate:
    cert = Certificate(
        user_id=user_id,
        course_id=course_id,
        status=status,
        certificate_number=f"CERT-{uuid.uuid4().hex[:8].upper()}",
    )
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


def _seed_review(
    db: Session, user_id=STUDENT_ID, course_id: str = "course-1", rating: int = 5, comment: str = "Great course!"
) -> CourseReview:
    review = CourseReview(
        user_id=user_id,
        course_id=course_id,
        rating=rating,
        comment=comment,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


def _seed_audit_log(db: Session, user_id=TEACHER_ID) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        action="create",
        resource_type="course",
        resource_id="course-1",
        details={"title": "Test Course"},
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def admin_client(db: Session, teacher: "User") -> TestClient:
    """TestClient authenticated as an admin user."""
    admin_user = _make_admin(db)

    def _override_db():
        yield db

    def _override_user():
        return admin_user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_optional_user] = _override_user
    app.dependency_overrides[require_admin] = _override_user
    app.dependency_overrides[require_teacher] = _override_user

    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc

    app.dependency_overrides.clear()


# ===================================================================
# USERS — GET /api/v1/users/me/courses
# ===================================================================


class TestGetMyCourses:
    def test_returns_empty_when_no_enrollments(self, student_client: TestClient):
        resp = student_client.get("/api/v1/users/me/courses")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_enrolled_courses(self, student_client: TestClient, db: Session):
        _seed_course(db)
        _seed_enrollment(db, user_id=STUDENT_ID)
        resp = student_client.get("/api/v1/users/me/courses")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["course_id"] == "course-1"

    def test_anon_gets_401(self, anon_client: TestClient):
        resp = anon_client.get("/api/v1/users/me/courses")
        assert resp.status_code in (401, 403)


# ===================================================================
# USERS — self-account deletion has been removed. Only admins can hard
# -delete users; see TestAdminDeleteUser below.
# ===================================================================


class TestSelfDeleteIsGone:
    """The ``DELETE /users/me`` route was removed (see commit history).

    Exercising it here guarantees that no regression re-introduces a
    self-destruct button on the public API surface.
    """

    def test_self_delete_route_is_404(self, student_client: TestClient):
        resp = student_client.request("DELETE", "/api/v1/users/me", json={"confirm": "DELETE"})
        assert resp.status_code in (404, 405)


# ===================================================================
# USERS — GET /api/v1/users/admin/users (admin only)
# ===================================================================


class TestAdminListUsers:
    def test_admin_can_list_users(self, admin_client: TestClient):
        resp = admin_client.get("/api/v1/users/admin/users")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 2  # teacher + admin at minimum

    def test_teacher_is_rejected(self, client: TestClient):
        resp = client.get("/api/v1/users/admin/users")
        assert resp.status_code == 403

    def test_student_is_rejected(self, student_client: TestClient):
        resp = student_client.get("/api/v1/users/admin/users")
        assert resp.status_code == 403

    def test_anon_is_rejected(self, anon_client: TestClient):
        resp = anon_client.get("/api/v1/users/admin/users")
        assert resp.status_code in (401, 403)


# ===================================================================
# USERS — PUT /api/v1/users/admin/users/{user_id}/role
# ===================================================================


class TestAdminUpdateRole:
    def test_admin_can_change_role(self, admin_client: TestClient, db: Session):
        resp = admin_client.put(f"/api/v1/users/admin/users/{TEACHER_ID}/role?role=admin")
        assert resp.status_code == 200
        body = resp.json()
        assert body["role"] == "admin"

    def test_invalid_role(self, admin_client: TestClient):
        resp = admin_client.put(f"/api/v1/users/admin/users/{TEACHER_ID}/role?role=superadmin")
        assert resp.status_code == 400

    def test_user_not_found(self, admin_client: TestClient):
        fake_id = uuid.uuid4()
        resp = admin_client.put(f"/api/v1/users/admin/users/{fake_id}/role?role=student")
        assert resp.status_code == 404

    def test_teacher_cannot_change_role(self, client: TestClient):
        resp = client.put(f"/api/v1/users/admin/users/{STUDENT_ID}/role?role=admin")
        assert resp.status_code == 403

    def test_missing_role_query_param(self, admin_client: TestClient):
        resp = admin_client.put(f"/api/v1/users/admin/users/{TEACHER_ID}/role")
        assert resp.status_code == 422


# ===================================================================
# REVIEWS — GET /api/v1/reviews/course/{course_id}
# ===================================================================


class TestListReviews:
    def test_list_reviews_empty(self, client: TestClient, db: Session):
        _seed_course(db)
        resp = client.get("/api/v1/reviews/course/course-1")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_reviews_with_data(self, client: TestClient, db: Session):
        _seed_course(db)
        _seed_review(db, user_id=STUDENT_ID, course_id="course-1")
        resp = client.get("/api/v1/reviews/course/course-1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["rating"] == 5

    def test_nonexistent_course_returns_404(self, client: TestClient):
        resp = client.get("/api/v1/reviews/course/no-such-course")
        assert resp.status_code == 404

    def test_unpublished_course_reviews_hidden(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-draft", status="draft")
        resp = client.get("/api/v1/reviews/course/course-draft")
        assert resp.status_code == 404


# ===================================================================
# REVIEWS — POST /api/v1/reviews/course/{course_id}
# ===================================================================


class TestCreateReview:
    def test_create_review_with_approved_cert(self, student_client: TestClient, db: Session):
        _seed_course(db)
        _seed_certificate(db, user_id=STUDENT_ID, course_id="course-1", status="approved")
        resp = student_client.post(
            "/api/v1/reviews/course/course-1",
            json={"rating": 4, "comment": "Good course"},
        )
        assert resp.status_code in (200, 201)
        body = resp.json()
        assert body["rating"] == 4
        assert body["comment"] == "Good course"

    def test_create_review_without_cert_fails(self, student_client: TestClient, db: Session):
        _seed_course(db)
        resp = student_client.post(
            "/api/v1/reviews/course/course-1",
            json={"rating": 3, "comment": "OK"},
        )
        assert resp.status_code == 403

    def test_create_review_with_pending_cert_fails(self, student_client: TestClient, db: Session):
        _seed_course(db)
        _seed_certificate(db, user_id=STUDENT_ID, course_id="course-1", status="pending")
        resp = student_client.post(
            "/api/v1/reviews/course/course-1",
            json={"rating": 3, "comment": "Pending"},
        )
        assert resp.status_code == 403

    def test_update_existing_review(self, student_client: TestClient, db: Session):
        _seed_course(db)
        _seed_certificate(db, user_id=STUDENT_ID, course_id="course-1", status="approved")
        student_client.post(
            "/api/v1/reviews/course/course-1",
            json={"rating": 3, "comment": "First"},
        )
        resp = student_client.post(
            "/api/v1/reviews/course/course-1",
            json={"rating": 5, "comment": "Updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["rating"] == 5
        assert resp.json()["comment"] == "Updated"

    def test_rating_out_of_range(self, student_client: TestClient, db: Session):
        _seed_course(db)
        _seed_certificate(db, user_id=STUDENT_ID, course_id="course-1", status="approved")
        resp = student_client.post(
            "/api/v1/reviews/course/course-1",
            json={"rating": 0},
        )
        assert resp.status_code == 422

        resp = student_client.post(
            "/api/v1/reviews/course/course-1",
            json={"rating": 6},
        )
        assert resp.status_code == 422

    def test_anon_cannot_create_review(self, anon_client: TestClient, db: Session):
        _seed_course(db)
        resp = anon_client.post(
            "/api/v1/reviews/course/course-1",
            json={"rating": 5},
        )
        assert resp.status_code in (401, 403)


# ===================================================================
# REVIEWS — DELETE /api/v1/reviews/{review_id}
# ===================================================================


class TestDeleteReview:
    def test_delete_own_review(self, student_client: TestClient, db: Session):
        _seed_course(db)
        review = _seed_review(db, user_id=STUDENT_ID, course_id="course-1")
        resp = student_client.delete(f"/api/v1/reviews/{review.id}")
        assert resp.status_code == 204

    def test_delete_nonexistent_review(self, student_client: TestClient):
        fake_id = uuid.uuid4()
        resp = student_client.delete(f"/api/v1/reviews/{fake_id}")
        assert resp.status_code == 404

    def test_delete_others_review_forbidden(self, client: TestClient, db: Session):
        _seed_course(db)
        review = _seed_review(db, user_id=STUDENT_ID, course_id="course-1")
        resp = client.delete(f"/api/v1/reviews/{review.id}")
        assert resp.status_code == 403

    def test_anon_cannot_delete(self, anon_client: TestClient, db: Session):
        _seed_course(db)
        review = _seed_review(db, user_id=STUDENT_ID, course_id="course-1")
        resp = anon_client.delete(f"/api/v1/reviews/{review.id}")
        assert resp.status_code in (401, 403)


# ===================================================================
# PREREQUISITES — GET /api/v1/prerequisites/course/{course_id}
# ===================================================================


class TestGetPrerequisites:
    def test_empty_prerequisites(self, client: TestClient, db: Session):
        _seed_course(db)
        resp = client.get("/api/v1/prerequisites/course/course-1")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_with_prerequisite(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1")
        _seed_course(db, course_id="course-2", title="Prereq Course")
        prereq = CoursePrerequisite(course_id="course-1", prerequisite_course_id="course-2")
        db.add(prereq)
        db.commit()

        resp = client.get("/api/v1/prerequisites/course/course-1")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["prerequisite_course_id"] == "course-2"
        assert data[0]["prerequisite_course_title"] == "Prereq Course"


# ===================================================================
# PREREQUISITES — PUT /api/v1/prerequisites/course/{course_id}
# ===================================================================


class TestSetPrerequisites:
    def test_set_prerequisites(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1")
        _seed_course(db, course_id="course-2", title="Prereq")
        resp = client.put(
            "/api/v1/prerequisites/course/course-1",
            json={"prerequisite_course_ids": ["course-2"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["prerequisite_course_id"] == "course-2"

    def test_self_prerequisite_rejected(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1")
        resp = client.put(
            "/api/v1/prerequisites/course/course-1",
            json={"prerequisite_course_ids": ["course-1"]},
        )
        assert resp.status_code == 400

    def test_two_node_cycle_rejected(self, client: TestClient, db: Session):
        # A -> B already exists; attempting to add B -> A would close a
        # cycle. The self-cycle short-circuit doesn't catch this; only
        # the DFS through the existing prerequisite graph does.
        _seed_course(db, course_id="course-a")
        _seed_course(db, course_id="course-b")
        # A -> B
        client.put(
            "/api/v1/prerequisites/course/course-a",
            json={"prerequisite_course_ids": ["course-b"]},
        )
        # B -> A would close the cycle
        resp = client.put(
            "/api/v1/prerequisites/course/course-b",
            json={"prerequisite_course_ids": ["course-a"]},
        )
        assert resp.status_code == 400
        assert "circular" in resp.json()["detail"].lower()

    def test_three_node_cycle_rejected(self, client: TestClient, db: Session):
        # A -> B -> C already exists; C -> A would close a 3-node cycle.
        _seed_course(db, course_id="course-a")
        _seed_course(db, course_id="course-b")
        _seed_course(db, course_id="course-c")
        client.put(
            "/api/v1/prerequisites/course/course-a",
            json={"prerequisite_course_ids": ["course-b"]},
        )
        client.put(
            "/api/v1/prerequisites/course/course-b",
            json={"prerequisite_course_ids": ["course-c"]},
        )
        resp = client.put(
            "/api/v1/prerequisites/course/course-c",
            json={"prerequisite_course_ids": ["course-a"]},
        )
        assert resp.status_code == 400

    def test_nonexistent_prerequisite_course(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1")
        resp = client.put(
            "/api/v1/prerequisites/course/course-1",
            json={"prerequisite_course_ids": ["does-not-exist"]},
        )
        assert resp.status_code == 404

    def test_replace_prerequisites(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1")
        _seed_course(db, course_id="course-2", title="Old prereq")
        _seed_course(db, course_id="course-3", title="New prereq")
        client.put(
            "/api/v1/prerequisites/course/course-1",
            json={"prerequisite_course_ids": ["course-2"]},
        )
        resp = client.put(
            "/api/v1/prerequisites/course/course-1",
            json={"prerequisite_course_ids": ["course-3"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["prerequisite_course_id"] == "course-3"

    def test_clear_all_prerequisites(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1")
        _seed_course(db, course_id="course-2", title="Prereq")
        client.put(
            "/api/v1/prerequisites/course/course-1",
            json={"prerequisite_course_ids": ["course-2"]},
        )
        resp = client.put(
            "/api/v1/prerequisites/course/course-1",
            json={"prerequisite_course_ids": []},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_student_cannot_set_prerequisites(self, student_client: TestClient, db: Session):
        _seed_course(db, course_id="course-1")
        resp = student_client.put(
            "/api/v1/prerequisites/course/course-1",
            json={"prerequisite_course_ids": []},
        )
        assert resp.status_code == 403

    def test_non_owner_teacher_rejected(self, client: TestClient, db: Session):
        other_teacher_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
        other = User(
            id=other_teacher_id, email="other@example.com", full_name="Other Teacher", role=UserRole.TEACHER.value
        )
        db.add(other)
        db.commit()
        _seed_course(db, course_id="course-1", owner=other_teacher_id)
        resp = client.put(
            "/api/v1/prerequisites/course/course-1",
            json={"prerequisite_course_ids": []},
        )
        assert resp.status_code == 403


# ===================================================================
# ANALYTICS — GET /api/v1/analytics/course/{course_id}
# ===================================================================


class TestCourseAnalytics:
    def test_owner_gets_analytics(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        student = User(
            id=STUDENT_ID, email="student@example.com", full_name="Test Student", role=UserRole.STUDENT.value
        )
        db.add(student)
        db.commit()
        _seed_enrollment(db, user_id=STUDENT_ID, course_id="course-1", progress=50)
        resp = client.get("/api/v1/analytics/course/course-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["course_id"] == "course-1"
        assert body["total_students"] == 1
        assert body["avg_progress"] == 50.0

    def test_non_owner_rejected(self, client: TestClient, db: Session):
        other_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
        other = User(id=other_id, email="other@example.com", full_name="Other", role=UserRole.TEACHER.value)
        db.add(other)
        db.commit()
        _seed_course(db, course_id="course-1", owner=other_id)
        resp = client.get("/api/v1/analytics/course/course-1")
        assert resp.status_code == 403

    def test_student_rejected(self, student_client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        resp = student_client.get("/api/v1/analytics/course/course-1")
        assert resp.status_code == 403

    def test_course_not_found(self, client: TestClient):
        resp = client.get("/api/v1/analytics/course/no-such-course")
        assert resp.status_code == 404

    def test_analytics_empty_course(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        resp = client.get("/api/v1/analytics/course/course-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total_students"] == 0
        assert body["avg_progress"] == 0.0
        assert body["completion_count"] == 0


# ===================================================================
# HEALTH — GET /api/v1/health/db
# ===================================================================


class TestHealthDb:
    def test_db_health_requires_admin(self, client: TestClient):
        # /health/db now requires admin auth (tightened during pre-release
        # audit — previously leaked internal schema metadata).
        resp = client.get("/api/v1/health/db")
        assert resp.status_code == 403

    def test_db_health_anon_rejected(self, anon_client: TestClient):
        resp = anon_client.get("/api/v1/health/db")
        assert resp.status_code in (401, 403)

    def test_db_health_admin_ok(self, admin_client: TestClient):
        resp = admin_client.get("/api/v1/health/db")
        # SQLite lacks information_schema so the endpoint may return 200 with
        # ``profiles_table_exists=False`` or 503 if the query errors out.
        assert resp.status_code in (200, 503)
        if resp.status_code == 200:
            body = resp.json()
            assert body["status"] == "ok"
            assert body["database"] == "connected"


# ===================================================================
# AUDIT — GET /api/v1/audit
# ===================================================================


class TestAuditLog:
    def test_admin_can_list_audit_logs(self, admin_client: TestClient, db: Session):
        _seed_audit_log(db, user_id=TEACHER_ID)
        resp = admin_client.get("/api/v1/audit")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert body["total"] >= 1
        assert body["page"] == 1

    def test_teacher_rejected(self, client: TestClient):
        resp = client.get("/api/v1/audit")
        assert resp.status_code == 403

    def test_student_rejected(self, student_client: TestClient):
        resp = student_client.get("/api/v1/audit")
        assert resp.status_code == 403

    def test_pagination(self, admin_client: TestClient, db: Session):
        for _ in range(5):
            _seed_audit_log(db, user_id=TEACHER_ID)
        resp = admin_client.get("/api/v1/audit?page=1&page_size=2")
        assert resp.status_code == 200
        body = resp.json()
        assert body["page_size"] == 2
        assert len(body["items"]) == 2
        assert body["total"] >= 5

    def test_filter_by_action(self, admin_client: TestClient, db: Session):
        _seed_audit_log(db)
        resp = admin_client.get("/api/v1/audit?action=create")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1

    def test_filter_by_resource_type(self, admin_client: TestClient, db: Session):
        _seed_audit_log(db)
        resp = admin_client.get("/api/v1/audit?resource_type=course")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_invalid_user_id_returns_400(self, admin_client: TestClient):
        # Used to surface a Postgres ``invalid input syntax for type uuid``
        # 500. Validate up-front and 400 so a typo in the query string is
        # a recoverable client error.
        resp = admin_client.get("/api/v1/audit?user_id=not-a-uuid")
        assert resp.status_code == 400
        assert "uuid" in resp.json()["detail"].lower()

    def test_anon_rejected(self, anon_client: TestClient):
        resp = anon_client.get("/api/v1/audit")
        assert resp.status_code in (401, 403)


# ===================================================================
# COURSES — GET /api/v1/courses/my (teacher's own courses)
# ===================================================================


class TestListMyCourses:
    def test_teacher_sees_own_courses(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        resp = client.get("/api/v1/courses/my")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert any(c["id"] == "course-1" for c in data)

    def test_teacher_does_not_see_others(self, client: TestClient, db: Session):
        other_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
        other = User(id=other_id, email="other@example.com", full_name="Other", role=UserRole.TEACHER.value)
        db.add(other)
        db.commit()
        _seed_course(db, course_id="other-course", owner=other_id)
        resp = client.get("/api/v1/courses/my")
        assert resp.status_code == 200
        ids = [c["id"] for c in resp.json()]
        assert "other-course" not in ids

    def test_student_rejected(self, student_client: TestClient):
        resp = student_client.get("/api/v1/courses/my")
        assert resp.status_code == 403


# ===================================================================
# MODULES — GET /api/v1/courses/{course_id}/modules/{module_id}
# ===================================================================


class TestGetModule:
    def test_get_module_published_course(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", status="published")
        _seed_module(db, course_id="course-1", module_id="mod-1")
        resp = client.get("/api/v1/courses/course-1/modules/mod-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == "mod-1"
        assert body["course_id"] == "course-1"

    def test_module_not_found(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1")
        resp = client.get("/api/v1/courses/course-1/modules/no-such-mod")
        assert resp.status_code == 404

    def test_course_not_found(self, client: TestClient):
        resp = client.get("/api/v1/courses/no-course/modules/no-mod")
        assert resp.status_code == 404

    def test_draft_course_visible_to_owner(self, client: TestClient, db: Session):
        _seed_course(db, course_id="draft-1", status="draft", owner=TEACHER_ID)
        _seed_module(db, course_id="draft-1", module_id="mod-draft")
        resp = client.get("/api/v1/courses/draft-1/modules/mod-draft")
        assert resp.status_code == 200


# ===================================================================
# MODULES — POST /api/v1/courses/{course_id}/modules
# ===================================================================


class TestCreateModule:
    def test_create_module(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        resp = client.post(
            "/api/v1/courses/course-1/modules",
            json={"title": "New Module", "order_index": 0},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "New Module"
        assert body["course_id"] == "course-1"

    def test_create_module_course_not_found(self, client: TestClient):
        resp = client.post(
            "/api/v1/courses/no-course/modules",
            json={"title": "Module", "order_index": 0},
        )
        assert resp.status_code == 404

    def test_student_cannot_create_module(self, student_client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        resp = student_client.post(
            "/api/v1/courses/course-1/modules",
            json={"title": "Hacker Module", "order_index": 0},
        )
        assert resp.status_code == 403

    def test_non_owner_teacher_rejected(self, client: TestClient, db: Session):
        other_id = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
        other = User(id=other_id, email="other@example.com", full_name="Other", role=UserRole.TEACHER.value)
        db.add(other)
        db.commit()
        _seed_course(db, course_id="other-course", owner=other_id)
        resp = client.post(
            "/api/v1/courses/other-course/modules",
            json={"title": "Attempt", "order_index": 0},
        )
        assert resp.status_code == 403


# ===================================================================
# MODULES — PUT /api/v1/courses/{course_id}/modules/{module_id}
# ===================================================================


class TestUpdateModule:
    def test_update_module(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        _seed_module(db, course_id="course-1", module_id="mod-1")
        resp = client.put(
            "/api/v1/courses/course-1/modules/mod-1",
            json={"title": "Updated Module"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Module"

    def test_update_module_not_found(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        resp = client.put(
            "/api/v1/courses/course-1/modules/no-mod",
            json={"title": "X"},
        )
        assert resp.status_code == 404


# ===================================================================
# MODULES — DELETE /api/v1/courses/{course_id}/modules/{module_id}
# ===================================================================


class TestDeleteModule:
    def test_delete_module(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        _seed_module(db, course_id="course-1", module_id="mod-1")
        resp = client.delete("/api/v1/courses/course-1/modules/mod-1")
        assert resp.status_code == 204

    def test_delete_module_not_found(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        resp = client.delete("/api/v1/courses/course-1/modules/no-mod")
        assert resp.status_code == 404

    def test_student_cannot_delete(self, student_client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        _seed_module(db, course_id="course-1", module_id="mod-1")
        resp = student_client.delete("/api/v1/courses/course-1/modules/mod-1")
        assert resp.status_code == 403


# ===================================================================
# CHAPTERS — POST /api/v1/courses/{cid}/modules/{mid}/chapters
# ===================================================================


class TestCreateChapter:
    def test_create_chapter(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        _seed_module(db, course_id="course-1", module_id="mod-1")
        resp = client.post(
            "/api/v1/courses/course-1/modules/mod-1/chapters",
            json={"title": "Intro Chapter", "order_index": 0},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "Intro Chapter"
        assert body["module_id"] == "mod-1"

    def test_create_chapter_module_not_found(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        resp = client.post(
            "/api/v1/courses/course-1/modules/no-mod/chapters",
            json={"title": "X", "order_index": 0},
        )
        assert resp.status_code == 404

    def test_student_cannot_create_chapter(self, student_client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        _seed_module(db, course_id="course-1", module_id="mod-1")
        resp = student_client.post(
            "/api/v1/courses/course-1/modules/mod-1/chapters",
            json={"title": "Hack", "order_index": 0},
        )
        assert resp.status_code == 403

    def test_create_chapter_with_all_fields(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        _seed_module(db, course_id="course-1", module_id="mod-1")
        resp = client.post(
            "/api/v1/courses/course-1/modules/mod-1/chapters",
            json={
                "title": "Reading Chapter",
                "content": "Lorem ipsum",
                "order_index": 1,
                "chapter_type": "reading",
                "requires_completion": True,
                "is_locked": False,
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["chapter_type"] == "reading"
        assert body["requires_completion"] is True


# ===================================================================
# CHAPTERS — PUT /{cid}/modules/{mid}/chapters/{chid}
# ===================================================================


class TestUpdateChapter:
    def test_update_chapter(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        _seed_module(db, course_id="course-1", module_id="mod-1")
        _seed_chapter(db, module_id="mod-1", chapter_id="chap-1")
        resp = client.put(
            "/api/v1/courses/course-1/modules/mod-1/chapters/chap-1",
            json={"title": "Updated Chapter"},
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated Chapter"

    def test_update_chapter_not_found(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        _seed_module(db, course_id="course-1", module_id="mod-1")
        resp = client.put(
            "/api/v1/courses/course-1/modules/mod-1/chapters/no-chap",
            json={"title": "X"},
        )
        assert resp.status_code == 404


# ===================================================================
# CHAPTERS — DELETE /{cid}/modules/{mid}/chapters/{chid}
# ===================================================================


class TestDeleteChapter:
    def test_delete_chapter(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        _seed_module(db, course_id="course-1", module_id="mod-1")
        _seed_chapter(db, module_id="mod-1", chapter_id="chap-1")
        resp = client.delete("/api/v1/courses/course-1/modules/mod-1/chapters/chap-1")
        assert resp.status_code == 204

    def test_delete_chapter_not_found(self, client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        _seed_module(db, course_id="course-1", module_id="mod-1")
        resp = client.delete("/api/v1/courses/course-1/modules/mod-1/chapters/no-chap")
        assert resp.status_code == 404

    def test_student_cannot_delete_chapter(self, student_client: TestClient, db: Session):
        _seed_course(db, course_id="course-1", owner=TEACHER_ID)
        _seed_module(db, course_id="course-1", module_id="mod-1")
        _seed_chapter(db, module_id="mod-1", chapter_id="chap-1")
        resp = student_client.delete("/api/v1/courses/course-1/modules/mod-1/chapters/chap-1")
        assert resp.status_code == 403
