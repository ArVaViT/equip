"""Unit tests for ``app.api.dependencies``.

The conftest's authenticated ``client`` / ``student_client`` / ``admin_client``
fixtures REPLACE ``get_current_user`` / ``get_optional_user`` via
``app.dependency_overrides`` so the wired-up routes never actually
exercise those resolvers in the existing suite. That leaves all the
auth/permission error paths (401, 403, 404, no-payload-claim, missing-user,
unowned-course, unpublished-not-enrolled-not-owner, etc.) uncovered.

This file calls the dependency resolvers DIRECTLY with manually
constructed ``HTTPAuthorizationCredentials`` and seeded ORM rows, then
asserts on the ``HTTPException`` shape or the success return value.
That covers the auth gates at the lowest layer without standing up a
real Supabase / FastAPI dispatch path.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from app.api import dependencies as deps
from app.models.course import Chapter, CourseStatus, Module
from app.models.enrollment import Enrollment
from app.models.user import User, UserRole

from ._cv_helpers import make_course_with_text, make_module_with_text
from .conftest import ADMIN_ID, STUDENT_ID, TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Seed helpers — keep each test self-contained.
# ---------------------------------------------------------------------------


def _bearer(token: str = "any-token") -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _seed_user(db: Session, *, user_id: uuid.UUID, role: str, email: str) -> User:
    user = User(id=user_id, email=email, full_name=email, role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _seed_teacher(db: Session) -> User:
    return _seed_user(db, user_id=TEACHER_ID, role=UserRole.TEACHER.value, email="t@e.com")


def _seed_admin(db: Session) -> User:
    return _seed_user(db, user_id=ADMIN_ID, role=UserRole.ADMIN.value, email="a@e.com")


def _seed_student(db: Session) -> User:
    return _seed_user(db, user_id=STUDENT_ID, role=UserRole.STUDENT.value, email="s@e.com")


def _seed_published_course_with_chapter(db: Session, *, course_id: str, owner: uuid.UUID) -> tuple[str, str, str]:
    course = make_course_with_text(
        db,
        course_id=course_id,
        title="C",
        status=CourseStatus.PUBLISHED,
        created_by=owner,
    )
    module = make_module_with_text(
        db,
        module_id=f"{course_id}-mod",
        course_id=course.id,
        title="M",
    )
    chapter = Chapter(
        id=f"{course_id}-ch",
        module_id=module.id,
        title="Ch",
        order_index=0,
        chapter_type="reading",
    )
    db.add(chapter)
    db.commit()
    return course.id, module.id, chapter.id


# ---------------------------------------------------------------------------
# get_current_user — the load-bearing 401 gate
# ---------------------------------------------------------------------------


class TestGetCurrentUser:
    def test_invalid_token_payload_returns_401(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``decode_access_token`` returning ``None`` (expired sig, missing
        secret, Supabase fallback failed) MUST 401 with the WWW-Authenticate
        header so the browser surfaces a re-auth prompt."""
        monkeypatch.setattr(deps, "decode_access_token", lambda _token: None)
        with pytest.raises(HTTPException) as exc:
            deps.get_current_user(credentials=_bearer(), db=db)
        assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert exc.value.headers == {"WWW-Authenticate": "Bearer"}

    def test_payload_missing_sub_returns_401(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A successfully decoded token that doesn't carry a ``sub`` claim
        is malformed for our purposes — Supabase always sets it."""
        monkeypatch.setattr(deps, "decode_access_token", lambda _t: {"email": "x"})
        with pytest.raises(HTTPException) as exc:
            deps.get_current_user(credentials=_bearer(), db=db)
        assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unknown_user_id_returns_401(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Valid token signed by Supabase for a user we've never seen
        (orphaned auth.user without an app.users row, e.g. trigger
        outage). Must not silently 200 or 500 — return 401 ``User not
        found`` so the client can re-trigger profile bootstrap.

        Note: ``sub`` is a UUID instance here rather than a string.
        Production passes strings; the User.id column is native UUID
        on Postgres (auto-coerced) but the SQLite test backend's bind
        processor requires a UUID instance. The SUT only does
        ``.get("sub")`` + filter equality, so the type is invisible to
        it.
        """
        ghost_id = uuid.uuid4()
        monkeypatch.setattr(deps, "decode_access_token", lambda _t: {"sub": ghost_id})
        with pytest.raises(HTTPException) as exc:
            deps.get_current_user(credentials=_bearer(), db=db)
        assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
        assert "User not found" in exc.value.detail

    def test_returns_user_on_happy_path(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        teacher = _seed_teacher(db)
        monkeypatch.setattr(deps, "decode_access_token", lambda _t: {"sub": teacher.id})
        out = deps.get_current_user(credentials=_bearer(), db=db)
        assert out.id == teacher.id


# ---------------------------------------------------------------------------
# get_optional_user — the don't-raise sibling
# ---------------------------------------------------------------------------


class TestGetOptionalUser:
    def test_no_credentials_returns_none(self, db: Session) -> None:
        assert deps.get_optional_user(credentials=None, db=db) is None

    def test_invalid_payload_returns_none_no_raise(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(deps, "decode_access_token", lambda _t: None)
        assert deps.get_optional_user(credentials=_bearer(), db=db) is None

    def test_missing_sub_returns_none(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(deps, "decode_access_token", lambda _t: {"email": "x"})
        assert deps.get_optional_user(credentials=_bearer(), db=db) is None

    def test_unknown_user_returns_none(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Optional-user is non-raising — a token signed for a user we
        haven't seen yet returns ``None`` rather than 401, so public
        listings still render for them as anonymous."""
        ghost_id = uuid.uuid4()
        monkeypatch.setattr(deps, "decode_access_token", lambda _t: {"sub": ghost_id})
        assert deps.get_optional_user(credentials=_bearer(), db=db) is None

    def test_returns_user_on_happy_path(
        self,
        db: Session,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        teacher = _seed_teacher(db)
        monkeypatch.setattr(deps, "decode_access_token", lambda _t: {"sub": teacher.id})
        out = deps.get_optional_user(credentials=_bearer(), db=db)
        assert out is not None
        assert out.id == teacher.id


# ---------------------------------------------------------------------------
# require_teacher / require_admin — role-gate dependencies
# ---------------------------------------------------------------------------


class TestRequireTeacher:
    """``require_teacher`` is the dependency every teacher-write route
    declares. It accepts TEACHER + ADMIN roles (admins get the same
    edit affordances). Non-teacher non-admin gets 403.
    """

    def test_teacher_passes(self) -> None:
        teacher = User(id=TEACHER_ID, email="t", full_name="t", role=UserRole.TEACHER.value)
        assert deps.require_teacher(current_user=teacher) is teacher

    def test_admin_passes(self) -> None:
        admin = User(id=ADMIN_ID, email="a", full_name="a", role=UserRole.ADMIN.value)
        assert deps.require_teacher(current_user=admin) is admin

    def test_student_is_403(self) -> None:
        student = User(id=STUDENT_ID, email="s", full_name="s", role=UserRole.STUDENT.value)
        with pytest.raises(HTTPException) as exc:
            deps.require_teacher(current_user=student)
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN
        assert "teachers" in exc.value.detail.lower()


class TestRequireAdmin:
    """``require_admin`` is stricter than ``require_teacher`` — only
    the ADMIN role passes. Teachers + students both get 403.
    """

    def test_admin_passes(self) -> None:
        admin = User(id=ADMIN_ID, email="a", full_name="a", role=UserRole.ADMIN.value)
        assert deps.require_admin(current_user=admin) is admin

    def test_teacher_is_403(self) -> None:
        teacher = User(id=TEACHER_ID, email="t", full_name="t", role=UserRole.TEACHER.value)
        with pytest.raises(HTTPException) as exc:
            deps.require_admin(current_user=teacher)
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN
        assert "admin" in exc.value.detail.lower()

    def test_student_is_403(self) -> None:
        student = User(id=STUDENT_ID, email="s", full_name="s", role=UserRole.STUDENT.value)
        with pytest.raises(HTTPException) as exc:
            deps.require_admin(current_user=student)
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# is_owner_or_admin — pure predicate
# ---------------------------------------------------------------------------


class TestIsOwnerOrAdmin:
    def test_anonymous_user_is_never_allowed(self) -> None:
        """``user=None`` short-circuits to ``False`` — used by listing
        surfaces to hide unpublished rows from logged-out viewers."""
        entity = type("E", (), {"created_by": str(TEACHER_ID)})()
        assert deps.is_owner_or_admin(entity, None) is False

    def test_owner_matches_by_created_by(self) -> None:
        owner = User(id=TEACHER_ID, email="x", full_name="x", role=UserRole.TEACHER.value)
        entity = type("E", (), {"created_by": str(TEACHER_ID)})()
        assert deps.is_owner_or_admin(entity, owner) is True

    def test_admin_passes_even_when_not_owner(self) -> None:
        admin = User(id=ADMIN_ID, email="x", full_name="x", role=UserRole.ADMIN.value)
        other_teacher = uuid.uuid4()
        entity = type("E", (), {"created_by": str(other_teacher)})()
        assert deps.is_owner_or_admin(entity, admin) is True

    def test_non_owner_non_admin_is_denied(self) -> None:
        student = User(id=STUDENT_ID, email="x", full_name="x", role=UserRole.STUDENT.value)
        entity = type("E", (), {"created_by": str(TEACHER_ID)})()
        assert deps.is_owner_or_admin(entity, student) is False


# ---------------------------------------------------------------------------
# _resolve_admin_flag — the User-or-id polymorphism
# ---------------------------------------------------------------------------


class TestResolveAdminFlag:
    def test_user_instance_short_circuits_without_query(self, db: Session) -> None:
        """Passing a hydrated User instance must not issue any SELECT —
        the role is already in memory. Pin so a refactor doesn't accidentally
        introduce a per-call DB hit."""
        admin = User(id=ADMIN_ID, email="x", full_name="x", role=UserRole.ADMIN.value)
        assert deps._resolve_admin_flag(db, admin) is True
        teacher = User(id=TEACHER_ID, email="x", full_name="x", role=UserRole.TEACHER.value)
        assert deps._resolve_admin_flag(db, teacher) is False

    def test_bare_id_path_issues_query(self, db: Session) -> None:
        """When the caller has only the id (e.g. route param) we issue
        a SELECT on users.id + role check. Verify it returns True for
        a seeded admin and False for a teacher."""
        _seed_admin(db)
        _seed_teacher(db)
        assert deps._resolve_admin_flag(db, ADMIN_ID) is True
        assert deps._resolve_admin_flag(db, TEACHER_ID) is False


# ---------------------------------------------------------------------------
# verify_course_owner — the teacher-edit gate
# ---------------------------------------------------------------------------


class TestVerifyCourseOwner:
    def test_owner_passes(self, db: Session) -> None:
        teacher = _seed_teacher(db)
        course_id, _, _ = _seed_published_course_with_chapter(db, course_id="vco-1", owner=TEACHER_ID)
        course = deps.verify_course_owner(db, course_id, teacher)
        assert course.id == course_id

    def test_admin_passes_through_allow_admin_branch(self, db: Session) -> None:
        """The default ``allow_admin=True`` is what lets the admin-takeover
        flow edit a course they didn't author. Pin the branch — a future
        refactor that flips the default to False would silently break
        admin recovery."""
        _seed_teacher(db)
        admin = _seed_admin(db)
        course_id, _, _ = _seed_published_course_with_chapter(db, course_id="vco-2", owner=TEACHER_ID)
        course = deps.verify_course_owner(db, course_id, admin)
        assert course.id == course_id

    def test_admin_denied_when_allow_admin_false(self, db: Session) -> None:
        """Some routes (e.g. teacher-only write paths) explicitly pass
        ``allow_admin=False``. Admin should be denied 403 on those."""
        _seed_teacher(db)
        admin = _seed_admin(db)
        course_id, _, _ = _seed_published_course_with_chapter(db, course_id="vco-3", owner=TEACHER_ID)
        with pytest.raises(HTTPException) as exc:
            deps.verify_course_owner(db, course_id, admin, allow_admin=False)
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    def test_unknown_course_id_returns_404(self, db: Session) -> None:
        teacher = _seed_teacher(db)
        with pytest.raises(HTTPException) as exc:
            deps.verify_course_owner(db, "nope", teacher)
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    def test_other_teacher_is_denied(self, db: Session) -> None:
        _seed_teacher(db)
        course_id, _, _ = _seed_published_course_with_chapter(db, course_id="vco-4", owner=TEACHER_ID)
        other_teacher_id = uuid.uuid4()
        other = _seed_user(db, user_id=other_teacher_id, role=UserRole.TEACHER.value, email="o@e.com")
        with pytest.raises(HTTPException) as exc:
            deps.verify_course_owner(db, course_id, other)
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN


# ---------------------------------------------------------------------------
# verify_chapter_access — the student-view gate
# ---------------------------------------------------------------------------


class TestVerifyChapterAccess:
    def test_admin_always_passes(self, db: Session) -> None:
        _seed_teacher(db)
        admin = _seed_admin(db)
        _course_id, _, chapter_id = _seed_published_course_with_chapter(db, course_id="vca-1", owner=TEACHER_ID)
        chapter = deps.verify_chapter_access(db, chapter_id, admin)
        assert chapter.id == chapter_id

    def test_course_owner_passes(self, db: Session) -> None:
        teacher = _seed_teacher(db)
        _, _, chapter_id = _seed_published_course_with_chapter(db, course_id="vca-2", owner=TEACHER_ID)
        chapter = deps.verify_chapter_access(db, chapter_id, teacher)
        assert chapter.id == chapter_id

    def test_enrolled_student_passes(self, db: Session) -> None:
        _seed_teacher(db)
        student = _seed_student(db)
        course_id, _, chapter_id = _seed_published_course_with_chapter(db, course_id="vca-3", owner=TEACHER_ID)
        db.add(
            Enrollment(
                id=f"enr-{course_id}",
                user_id=student.id,
                course_id=course_id,
                progress=0,
            )
        )
        db.commit()
        chapter = deps.verify_chapter_access(db, chapter_id, student)
        assert chapter.id == chapter_id

    def test_unpublished_course_is_404_for_non_owner(self, db: Session) -> None:
        """Unpublished courses are invisible to everyone except the owner
        and admins. A logged-in student hitting an unpublished chapter
        must get 404 (not 403) to avoid leaking course existence."""
        _seed_teacher(db)
        student = _seed_student(db)
        # Course starts as draft, NOT published.
        course = make_course_with_text(
            db,
            course_id="vca-4",
            title="Hidden",
            status=CourseStatus.DRAFT,
            created_by=TEACHER_ID,
        )
        module = make_module_with_text(db, module_id="vca-4-mod", course_id=course.id, title="M")
        chapter = Chapter(
            id="vca-4-ch",
            module_id=module.id,
            title="Ch",
            order_index=0,
            chapter_type="reading",
        )
        db.add(chapter)
        db.commit()

        with pytest.raises(HTTPException) as exc:
            deps.verify_chapter_access(db, chapter.id, student)
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    def test_not_enrolled_student_is_403(self, db: Session) -> None:
        _seed_teacher(db)
        student = _seed_student(db)
        _course_id, _, chapter_id = _seed_published_course_with_chapter(db, course_id="vca-5", owner=TEACHER_ID)
        with pytest.raises(HTTPException) as exc:
            deps.verify_chapter_access(db, chapter_id, student)
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    def test_unknown_chapter_is_404(self, db: Session) -> None:
        teacher = _seed_teacher(db)
        with pytest.raises(HTTPException) as exc:
            deps.verify_chapter_access(db, "nope", teacher)
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# verify_chapter_owner — the teacher-edit gate at chapter granularity
# ---------------------------------------------------------------------------


class TestVerifyChapterOwner:
    def test_course_owner_returns_chapter_and_course_id(self, db: Session) -> None:
        teacher = _seed_teacher(db)
        course_id, _, chapter_id = _seed_published_course_with_chapter(db, course_id="vch-1", owner=TEACHER_ID)
        chapter, returned_course_id = deps.verify_chapter_owner(db, chapter_id, teacher)
        assert chapter.id == chapter_id
        assert returned_course_id == course_id

    def test_admin_returns_chapter_and_course_id(self, db: Session) -> None:
        """Admin path — the 'else if admin' branch of the function must
        also return the chapter + course id tuple, not raise."""
        _seed_teacher(db)
        admin = _seed_admin(db)
        course_id, _, chapter_id = _seed_published_course_with_chapter(db, course_id="vch-2", owner=TEACHER_ID)
        chapter, returned_course_id = deps.verify_chapter_owner(db, chapter_id, admin)
        assert chapter.id == chapter_id
        assert returned_course_id == course_id

    def test_other_teacher_is_403(self, db: Session) -> None:
        _seed_teacher(db)
        _, _, chapter_id = _seed_published_course_with_chapter(db, course_id="vch-3", owner=TEACHER_ID)
        other_teacher_id = uuid.uuid4()
        other = _seed_user(db, user_id=other_teacher_id, role=UserRole.TEACHER.value, email="o@e.com")
        with pytest.raises(HTTPException) as exc:
            deps.verify_chapter_owner(db, chapter_id, other)
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    def test_soft_deleted_chapter_is_404(self, db: Session) -> None:
        """Soft-deleted chapters are invisible across every chapter-scoped
        route — pinning this stops the 'edit a tombstoned chapter' bug."""
        teacher = _seed_teacher(db)
        _, _, chapter_id = _seed_published_course_with_chapter(db, course_id="vch-4", owner=TEACHER_ID)
        from datetime import UTC, datetime

        db.query(Chapter).filter(Chapter.id == chapter_id).update({"deleted_at": datetime.now(UTC)})
        db.commit()
        with pytest.raises(HTTPException) as exc:
            deps.verify_chapter_owner(db, chapter_id, teacher)
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    def test_soft_deleted_module_hides_chapter(self, db: Session) -> None:
        teacher = _seed_teacher(db)
        _course_id, module_id, chapter_id = _seed_published_course_with_chapter(db, course_id="vch-5", owner=TEACHER_ID)
        from datetime import UTC, datetime

        db.query(Module).filter(Module.id == module_id).update({"deleted_at": datetime.now(UTC)})
        db.commit()
        with pytest.raises(HTTPException) as exc:
            deps.verify_chapter_owner(db, chapter_id, teacher)
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND
