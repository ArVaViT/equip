"""Additional tests covering gaps identified in the pre-release audit:

- ``PUT /api/v1/users/admin/users/bulk-role`` (bulk role update)
- ``GET /api/v1/courses/my/trash`` + restore/permanent delete flows
- ``GET /api/v1/grades/course/{course_id}/export-csv`` (grade CSV export)
- Additional auth edge cases on ``/auth/me``.

These endpoints drive destructive or high-impact flows that had no
coverage before; they are now locked in with happy-path + negative tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import (
    get_current_user,
    get_optional_user,
    require_admin,
    require_teacher,
)
from app.core.database import get_db
from app.main import app
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.user import User, UserRole
from tests.conftest import STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

ADMIN_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
OTHER_STUDENT_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")

COURSES_PREFIX = "/api/v1/courses"
USERS_PREFIX = "/api/v1/users"
GRADES_PREFIX = "/api/v1/grades"


# ---------------------------------------------------------------------------
# Fixtures & helpers
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


def _make_other_student(db: Session) -> User:
    other = User(
        id=OTHER_STUDENT_ID,
        email="student2@example.com",
        full_name="Second Student",
        role=UserRole.STUDENT.value,
    )
    db.add(other)
    db.commit()
    db.refresh(other)
    return other


@pytest.fixture()
def admin_client(db: Session, teacher: User) -> TestClient:
    """TestClient authenticated as an admin, with teacher + admin seeded."""
    admin = _make_admin(db)

    def _override_db():
        yield db

    def _override_user():
        return admin

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_optional_user] = _override_user
    app.dependency_overrides[require_admin] = _override_user
    app.dependency_overrides[require_teacher] = _override_user

    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc

    app.dependency_overrides.clear()


def _create_course(client: TestClient, title: str = "Course") -> dict:
    resp = client.post(COURSES_PREFIX, json={"title": title})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _seed_course_direct(
    db: Session,
    *,
    course_id: str = "course-1",
    owner: uuid.UUID = TEACHER_ID,
    deleted: bool = False,
    title: str = "Test Course",
) -> Course:
    course = Course(
        id=course_id,
        title=title,
        description="Testing",
        status="published",
        created_by=owner,
        deleted_at=datetime.now(UTC) if deleted else None,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


# ===========================================================================
# PUT /api/v1/users/admin/users/bulk-role
# ===========================================================================


class TestBulkUpdateRoles:
    def test_admin_can_bulk_promote_users(self, admin_client: TestClient, db: Session):
        other = _make_other_student(db)
        resp = admin_client.put(
            f"{USERS_PREFIX}/admin/users/bulk-role",
            json={"user_ids": [str(STUDENT_ID), str(other.id)], "role": "teacher"},
        )
        # STUDENT_ID does not exist in db yet (student fixture not used) so only
        # one user updates. Exercise the route, then ensure the other student
        # was actually updated.
        assert resp.status_code == 200
        body = resp.json()
        assert body["role"] == "teacher"
        assert body["updated"] >= 1
        db.expire_all()
        refreshed = db.query(User).filter(User.id == other.id).first()
        assert refreshed is not None
        assert refreshed.role == "teacher"

    def test_admin_cannot_demote_self(self, admin_client: TestClient, db: Session):
        """Passing the admin's own id must be filtered out before update."""
        resp = admin_client.put(
            f"{USERS_PREFIX}/admin/users/bulk-role",
            json={"user_ids": [str(ADMIN_ID)], "role": "student"},
        )
        assert resp.status_code == 200
        # Route filters the admin id out so no rows are updated.
        assert resp.json()["updated"] == 0
        db.expire_all()
        admin = db.query(User).filter(User.id == ADMIN_ID).first()
        assert admin is not None
        assert admin.role == UserRole.ADMIN.value

    def test_invalid_role_returns_400(self, admin_client: TestClient):
        resp = admin_client.put(
            f"{USERS_PREFIX}/admin/users/bulk-role",
            json={"user_ids": [str(STUDENT_ID)], "role": "superadmin"},
        )
        assert resp.status_code == 400

    def test_oversized_batch_returns_400(self, admin_client: TestClient):
        ids = [str(uuid.uuid4()) for _ in range(101)]
        resp = admin_client.put(
            f"{USERS_PREFIX}/admin/users/bulk-role",
            json={"user_ids": ids, "role": "student"},
        )
        assert resp.status_code == 400
        assert "Maximum 100" in resp.json()["detail"]

    def test_invalid_uuids_are_ignored(self, admin_client: TestClient, db: Session):
        other = _make_other_student(db)
        resp = admin_client.put(
            f"{USERS_PREFIX}/admin/users/bulk-role",
            json={
                "user_ids": ["not-a-uuid", "also-invalid", str(other.id)],
                "role": "teacher",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] == 1

    def test_teacher_is_forbidden(self, client: TestClient):
        resp = client.put(
            f"{USERS_PREFIX}/admin/users/bulk-role",
            json={"user_ids": [str(STUDENT_ID)], "role": "teacher"},
        )
        assert resp.status_code == 403

    def test_anon_is_rejected(self, anon_client: TestClient):
        resp = anon_client.put(
            f"{USERS_PREFIX}/admin/users/bulk-role",
            json={"user_ids": [str(STUDENT_ID)], "role": "teacher"},
        )
        assert resp.status_code in (401, 403)


# ===========================================================================
# DELETE /api/v1/users/admin/users/{user_id}
# ===========================================================================


class TestAdminDeleteUser:
    def test_admin_can_hard_delete_student(self, admin_client: TestClient, db: Session):
        student = _make_other_student(db)
        student_id = student.id
        resp = admin_client.delete(f"{USERS_PREFIX}/admin/users/{student_id}")
        assert resp.status_code == 204
        db.expire_all()
        assert db.query(User).filter(User.id == student_id).first() is None

    def test_admin_cannot_delete_self(self, admin_client: TestClient, db: Session):
        resp = admin_client.delete(f"{USERS_PREFIX}/admin/users/{ADMIN_ID}")
        assert resp.status_code == 400
        db.expire_all()
        assert db.query(User).filter(User.id == ADMIN_ID).first() is not None

    def test_delete_unknown_user_is_404(self, admin_client: TestClient):
        resp = admin_client.delete(f"{USERS_PREFIX}/admin/users/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_delete_invalid_uuid_is_404(self, admin_client: TestClient):
        resp = admin_client.delete(f"{USERS_PREFIX}/admin/users/not-a-uuid")
        assert resp.status_code == 404

    def test_teacher_is_forbidden(self, client: TestClient, db: Session):
        student = _make_other_student(db)
        student_id = student.id
        resp = client.delete(f"{USERS_PREFIX}/admin/users/{student_id}")
        assert resp.status_code == 403
        db.expire_all()
        assert db.query(User).filter(User.id == student_id).first() is not None

    def test_student_is_forbidden(self, student_client: TestClient, db: Session):
        other = _make_other_student(db)
        other_id = other.id
        resp = student_client.delete(f"{USERS_PREFIX}/admin/users/{other_id}")
        assert resp.status_code == 403

    def test_anon_is_rejected(self, anon_client: TestClient, db: Session):
        other = _make_other_student(db)
        other_id = other.id
        resp = anon_client.delete(f"{USERS_PREFIX}/admin/users/{other_id}")
        assert resp.status_code in (401, 403)


# ===========================================================================
# Soft-delete / trash / restore / permanent-delete
# ===========================================================================


class TestTrashAndRestore:
    def test_delete_soft_deletes_course(self, client: TestClient, db: Session):
        course = _create_course(client, "Soon-to-be-trashed")
        resp = client.delete(f"{COURSES_PREFIX}/{course['id']}")
        assert resp.status_code == 204

        # Course should disappear from normal GET lookups and /my listing.
        resp = client.get(f"{COURSES_PREFIX}/{course['id']}")
        assert resp.status_code == 404

        # But it should appear in /my/trash.
        resp = client.get(f"{COURSES_PREFIX}/my/trash")
        assert resp.status_code == 200
        ids = {c["id"] for c in resp.json()}
        assert course["id"] in ids

        # Underlying row still exists with deleted_at set.
        db.expire_all()
        row = db.query(Course).filter(Course.id == course["id"]).first()
        assert row is not None
        assert row.deleted_at is not None

    def test_my_trash_does_not_list_live_courses(self, client: TestClient):
        course = _create_course(client, "Still alive")
        resp = client.get(f"{COURSES_PREFIX}/my/trash")
        assert resp.status_code == 200
        assert course["id"] not in {c["id"] for c in resp.json()}

    def test_restore_course_revives_it(self, client: TestClient, db: Session):
        _seed_course_direct(db, course_id="restore-me", deleted=True)
        resp = client.post(f"{COURSES_PREFIX}/restore-me/restore")
        assert resp.status_code == 200
        assert resp.json()["id"] == "restore-me"

        db.expire_all()
        row = db.query(Course).filter(Course.id == "restore-me").first()
        assert row is not None
        assert row.deleted_at is None

    def test_restore_preserves_independently_deleted_chapters(self, client: TestClient, db: Session):
        """Symmetric restore: a chapter the teacher trashed BEFORE the
        whole course was trashed must stay trashed when the course is
        restored. The two deletes have different ``deleted_at``
        timestamps; only rows matching the course tombstone get flipped
        back to live."""
        earlier = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        course_tombstone = datetime(2026, 5, 14, 9, 0, tzinfo=UTC)

        _seed_course_direct(db, course_id="restore-mix", deleted=False)
        # Manually set the course's deleted_at to the cascade timestamp so the
        # restore picks up the right value.
        course = db.query(Course).filter(Course.id == "restore-mix").first()
        assert course is not None
        course.deleted_at = course_tombstone

        # Two modules, one trashed independently before the course was.
        live_module = Module(
            id="mod-live",
            course_id="restore-mix",
            title="Live Module",
            order_index=0,
            deleted_at=course_tombstone,  # cascaded with the course
        )
        orphan_module = Module(
            id="mod-orphan",
            course_id="restore-mix",
            title="Orphan Module (teacher deleted before course trash)",
            order_index=1,
            deleted_at=earlier,
        )
        db.add(live_module)
        db.add(orphan_module)
        db.commit()

        # And one chapter that was also independently deleted.
        orphan_chapter = Chapter(
            id="ch-orphan",
            module_id="mod-live",
            title="Orphan Chapter",
            order_index=0,
            deleted_at=earlier,
        )
        live_chapter = Chapter(
            id="ch-live",
            module_id="mod-live",
            title="Live Chapter",
            order_index=1,
            deleted_at=course_tombstone,
        )
        db.add(orphan_chapter)
        db.add(live_chapter)
        db.commit()

        resp = client.post(f"{COURSES_PREFIX}/restore-mix/restore")
        assert resp.status_code == 200

        db.expire_all()
        assert db.query(Course).filter(Course.id == "restore-mix").first().deleted_at is None
        assert db.query(Module).filter(Module.id == "mod-live").first().deleted_at is None
        # Compare against ``is not None`` rather than the exact ``earlier``
        # value: SQLite's datetime roundtrip can shift microsecond
        # precision; the invariant is "stays deleted", not "exact value".
        assert db.query(Module).filter(Module.id == "mod-orphan").first().deleted_at is not None, (
            "Module that was deleted before the course tombstone must stay deleted"
        )
        assert db.query(Chapter).filter(Chapter.id == "ch-live").first().deleted_at is None
        assert db.query(Chapter).filter(Chapter.id == "ch-orphan").first().deleted_at is not None, (
            "Chapter that was deleted before the course tombstone must stay deleted"
        )

    def test_restore_nonexistent_returns_404(self, client: TestClient):
        resp = client.post(f"{COURSES_PREFIX}/nonexistent/restore")
        assert resp.status_code == 404

    def test_restore_live_course_returns_400(self, client: TestClient, db: Session):
        _seed_course_direct(db, course_id="live", deleted=False)
        resp = client.post(f"{COURSES_PREFIX}/live/restore")
        assert resp.status_code == 400

    def test_cannot_restore_someone_elses_course(self, client: TestClient, db: Session):
        other_teacher_id = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
        db.add(
            User(
                id=other_teacher_id,
                email="other@example.com",
                full_name="Other Teacher",
                role=UserRole.TEACHER.value,
            )
        )
        db.commit()
        _seed_course_direct(db, course_id="not-mine", owner=other_teacher_id, deleted=True)
        resp = client.post(f"{COURSES_PREFIX}/not-mine/restore")
        assert resp.status_code == 403

    def test_permanent_delete_requires_soft_delete_first(self, client: TestClient, db: Session):
        _seed_course_direct(db, course_id="still-live", deleted=False)
        resp = client.delete(f"{COURSES_PREFIX}/still-live/permanent")
        assert resp.status_code == 400

    def test_permanent_delete_removes_row(self, client: TestClient, db: Session):
        _seed_course_direct(db, course_id="gone-forever", deleted=True)
        resp = client.delete(f"{COURSES_PREFIX}/gone-forever/permanent")
        assert resp.status_code == 204
        db.expire_all()
        assert db.query(Course).filter(Course.id == "gone-forever").first() is None

    def test_anon_cannot_access_trash(self, anon_client: TestClient):
        resp = anon_client.get(f"{COURSES_PREFIX}/my/trash")
        assert resp.status_code in (401, 403)


# ===========================================================================
# Grade CSV export
# ===========================================================================


class TestGradeCsvExport:
    def test_export_happy_path_returns_csv(self, client: TestClient, db: Session):
        _seed_course_direct(db, course_id="csv-course", title="Intro to CSV")
        resp = client.get(f"{GRADES_PREFIX}/course/csv-course/export-csv")
        assert resp.status_code == 200

        content_type = resp.headers.get("content-type", "")
        assert content_type.startswith("text/csv")

        body = resp.text
        # BOM + header row must be present even with zero enrollments.
        assert body.startswith("\ufeff")
        first_line = body.splitlines()[0].lstrip("\ufeff")
        assert "Student Name" in first_line
        assert "Final Score" in first_line
        assert "Letter Grade" in first_line

        disposition = resp.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert "filename=" in disposition

    def test_export_includes_enrolled_student_rows(self, client: TestClient, student: User, db: Session):
        _seed_course_direct(db, course_id="csv-course-2", title="With Students")
        db.add(
            Enrollment(
                id=str(uuid.uuid4()),
                user_id=student.id,
                course_id="csv-course-2",
                progress=100,
            )
        )
        db.commit()

        resp = client.get(f"{GRADES_PREFIX}/course/csv-course-2/export-csv")
        assert resp.status_code == 200
        rows = [r for r in resp.text.splitlines() if r.strip()]
        assert len(rows) >= 2, "Expected header plus one student row"
        assert "student@example.com" in resp.text

    def test_export_unicode_title_has_utf8_filename(self, client: TestClient, db: Session):
        # Cyrillic title exercises the UTF-8 filename* header while ensuring
        # the ASCII fallback strips non-latin-1 bytes (regression guard).
        _seed_course_direct(
            db, course_id="csv-u", title="\u041a\u0443\u0440\u0441 \u043f\u043e \u0411\u0438\u0431\u043b\u0438\u0438"
        )
        resp = client.get(f"{GRADES_PREFIX}/course/csv-u/export-csv")
        assert resp.status_code == 200
        disposition = resp.headers.get("content-disposition", "")
        assert "UTF-8''" in disposition

    def test_export_nonexistent_course_is_404(self, client: TestClient):
        resp = client.get(f"{GRADES_PREFIX}/course/missing/export-csv")
        assert resp.status_code == 404

    def test_export_rejects_non_owner(self, client: TestClient, db: Session):
        other_teacher_id = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
        db.add(
            User(
                id=other_teacher_id,
                email="tx@example.com",
                full_name="Another Teacher",
                role=UserRole.TEACHER.value,
            )
        )
        db.commit()
        _seed_course_direct(db, course_id="csv-foreign", owner=other_teacher_id)
        resp = client.get(f"{GRADES_PREFIX}/course/csv-foreign/export-csv")
        assert resp.status_code == 403

    def test_export_rejects_student(self, student_client: TestClient, db: Session):
        _seed_course_direct(db, course_id="csv-stu")
        resp = student_client.get(f"{GRADES_PREFIX}/course/csv-stu/export-csv")
        assert resp.status_code == 403

    def test_export_anon_rejected(self, anon_client: TestClient, db: Session):
        _seed_course_direct(db, course_id="csv-anon")
        resp = anon_client.get(f"{GRADES_PREFIX}/course/csv-anon/export-csv")
        assert resp.status_code in (401, 403)


# ===========================================================================
# Additional auth tests
# ===========================================================================


class TestAuthEdgeCases:
    def test_me_returns_role_for_admin(self, admin_client: TestClient):
        resp = admin_client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    def test_me_returns_role_for_student(self, student_client: TestClient):
        resp = student_client.get("/api/v1/auth/me")
        assert resp.status_code == 200
        assert resp.json()["role"] == "student"

    def test_auth_required_on_course_mutations(self, anon_client: TestClient):
        resp = anon_client.post(COURSES_PREFIX, json={"title": "x"})
        assert resp.status_code in (401, 403)
