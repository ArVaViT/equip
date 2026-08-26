import hmac
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.core.security import decode_access_token
from app.models.course import Chapter, Course, CourseStatus, Module
from app.models.enrollment import Enrollment
from app.models.user import User, UserRole

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


def _unauthorized(message: str) -> HTTPException:
    """Build the standard 401 envelope (same shape for every auth failure)."""
    return equip_error(
        ErrorCode.AUTH_REQUIRED,
        status_code=status.HTTP_401_UNAUTHORIZED,
        message=message,
        headers={"WWW-Authenticate": "Bearer"},
    )


# Sync so FastAPI runs it in the threadpool: keeps the event loop free while
# decode_access_token (possible Supabase HTTP call) and the User SELECT block.
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise _unauthorized("Could not validate credentials")
    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise _unauthorized("Could not validate credentials")
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise _unauthorized("User not found")
    if user.deactivated_at is not None:
        # Soft-deleted account: the auth token may still be valid, but the
        # account is deactivated — block every authenticated surface until an
        # admin restores it. A dedicated code lets the client sign out cleanly.
        raise equip_error(
            ErrorCode.ACCOUNT_DEACTIVATED,
            status_code=status.HTTP_403_FORBIDDEN,
            message="This account has been deactivated",
        )
    return user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
    db: Session = Depends(get_db),
) -> User | None:
    if credentials is None:
        return None
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        return None
    user_id: str | None = payload.get("sub")
    if user_id is None:
        return None
    user = db.query(User).filter(User.id == user_id).first()
    # A deactivated account is treated as anonymous on optional-auth routes
    # (public surfaces stay reachable; nothing authenticated is granted).
    if user is not None and user.deactivated_at is not None:
        return None
    return user


def require_teacher(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role not in (UserRole.TEACHER.value, UserRole.ADMIN.value):
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Only teachers can perform this action",
        )
    return current_user


def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Platform staff only.

    This is Equip's own administration — the translation queue, user
    accounts, health, the audit log — and it is deliberately *not* what
    an organization's own administrator holds. For that, see
    ``require_director``.
    """
    if current_user.role != UserRole.ADMIN.value:
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Admin access required",
        )
    return current_user


def require_director(
    current_user: User = Depends(get_current_user),
) -> User:
    """An organization's own administrator — or platform staff.

    Cohorts, ведомости, invitations, certificate approval, the
    organization's settings. Until now all of these were gated by
    ``require_admin``, which is the same role that opens the translation
    queue and the audit log of the entire platform. With one
    organization that was harmless; with two it is a leak, and it is
    much harder to unpick once directors exist and hold the wrong key.

    Platform staff pass because they administer every organization by
    definition — not because the two roles are the same thing.

    What this does NOT yet check is that the object belongs to the
    caller's organization: there are no organizations to belong to. That
    check arrives with the ``organization_id`` columns, and this is the
    function it will arrive in.
    """
    if current_user.role not in (UserRole.DIRECTOR.value, UserRole.ADMIN.value):
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Only a director of this organization can perform this action",
        )
    return current_user


def require_worker_secret(
    x_worker_secret: str | None = Header(default=None, alias="X-Worker-Secret"),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    """Constant-time shared-secret check for the internal cron workers.

    Refuses every request when the env var is unset — opt-in by design so
    dev environments without the queue cron don't accidentally expose the
    endpoints.

    Accepts two header shapes so a single env var serves both flows:

    * ``X-Worker-Secret: <secret>`` — direct human / test access.
    * ``Authorization: Bearer <secret>`` — what Vercel Cron Jobs send
      automatically (Vercel signs each cron request with the
      ``CRON_SECRET`` env var; we map ``TRANSLATION_WORKER_SECRET`` to
      that value at deploy so the auth scheme matches).
    """
    expected = settings.TRANSLATION_WORKER_SECRET
    if expected is None or not expected.get_secret_value():
        raise equip_error(
            ErrorCode.TRANSLATION_WORKER_UNCONFIGURED,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            message="Translation worker is not configured on this deployment.",
            context={"resource_type": "translation_worker"},
        )
    expected_value = expected.get_secret_value()

    presented = x_worker_secret or ""
    if not presented and authorization and authorization.startswith("Bearer "):
        presented = authorization.removeprefix("Bearer ").strip()

    if not hmac.compare_digest(presented, expected_value):
        # 401 with a generic message so a probing attacker can't
        # distinguish 'wrong secret' from 'no secret header'.
        raise equip_error(
            ErrorCode.TRANSLATION_WORKER_UNAUTHORIZED,
            status_code=status.HTTP_401_UNAUTHORIZED,
            message="Worker authentication failed.",
            context={"resource_type": "translation_worker"},
        )


def _resolve_admin_flag(db: Session, teacher: User | str | UUID) -> bool:
    """Return whether ``teacher`` holds the admin role.

    Accepts either a hydrated ``User`` (no DB call) or a bare id (one SELECT).
    """
    if isinstance(teacher, User):
        return teacher.role == UserRole.ADMIN.value
    return bool(db.query(User.id).filter(User.id == teacher, User.role == UserRole.ADMIN.value).first())


def is_owner_or_admin(entity: object, user: User | None) -> bool:
    """Non-raising predicate: does ``user`` own ``entity`` (via
    ``entity.created_by``) or have the admin role?

    Use this when the access rule must influence flow control rather
    than raise a 403 — listing surfaces that hide unpublished rows from
    everyone except the owner / admin, branch on visibility. For the
    raising form, use ``assert_course_owner`` instead.

    ``entity`` is anything with a ``created_by`` attribute; works on
    Course, Announcement, CourseEvent, etc.
    """
    if user is None:
        return False
    created_by = getattr(entity, "created_by", None)
    if created_by is not None and str(created_by) == str(user.id):
        return True
    return user.role == UserRole.ADMIN.value


# ``assert_course_owner`` was moved to ``app.services.domain_access`` so
# services that need the predicate don't have to import backwards from
# the api layer. The canonical import path is now
# ``from app.services.domain_access import assert_course_owner``.
# The re-export below keeps the existing route code working unchanged.
from app.services.domain_access import assert_course_owner  # noqa: E402, F401  (re-export)


def get_live_course_or_404(db: Session, course_id: str) -> Course:
    """Fetch a non-deleted course or raise the canonical 404.

    Consolidates the course-fetch-or-404 boilerplate that several route
    modules duplicated. The error envelope (code / status / message /
    context) is byte-identical to those hand-written call sites so the
    HTTP contract is unchanged. Soft-deleted courses (``deleted_at``)
    are treated as not found.
    """
    course = db.query(Course).filter(Course.id == course_id, Course.deleted_at.is_(None)).first()
    if course is None:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Course not found",
            context={"resource_type": "course", "resource_id": course_id},
        )
    return course


def lookup_enrollment(db: Session, user_id: object, course_id: object) -> Enrollment | None:
    """Return the enrollment row for ``(user_id, course_id)`` or ``None``.

    Pure query helper: it deliberately does NOT raise. Each call site keeps
    its own ``if not enrolled: raise ...`` because the not-enrolled contract
    varies per endpoint (403 vs 400 vs 404, with different messages / staff
    bypasses). One indexed PK lookup on ``(user_id, course_id)``.
    """
    return db.query(Enrollment).filter(Enrollment.user_id == user_id, Enrollment.course_id == course_id).first()


def verify_course_owner(
    db: Session,
    course_id: str,
    teacher: User | str | UUID,
    *,
    allow_admin: bool = True,
) -> Course:
    # Soft-deleted courses are treated as "not found" so deleted courses cannot
    # be edited / enrolled into until explicitly restored. Admin recovery flows
    # that need deleted rows query the ORM directly with include_deleted.
    course = db.query(Course).filter(Course.id == course_id, Course.deleted_at.is_(None)).first()
    if not course:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Course not found",
            context={"resource_type": "course", "resource_id": course_id},
        )
    teacher_id = teacher.id if isinstance(teacher, User) else teacher
    if str(course.created_by) == str(teacher_id):
        return course
    if allow_admin and _resolve_admin_flag(db, teacher):
        return course
    raise equip_error(
        ErrorCode.AUTH_FORBIDDEN,
        status_code=status.HTTP_403_FORBIDDEN,
        message="You do not own this course",
    )


def _resolve_chapter(db: Session, chapter_id: str) -> tuple[Chapter, Module, Course]:
    # Hide soft-deleted chapters/modules/courses across every chapter-scoped
    # route (blocks, quizzes, assignments, progress). Before this filter,
    # content deleted via the teacher UI was still reachable via chapter_id.
    row = (
        db.query(Chapter, Module, Course)
        .join(Module, Chapter.module_id == Module.id)
        .join(Course, Module.course_id == Course.id)
        .filter(
            Chapter.id == chapter_id,
            Chapter.deleted_at.is_(None),
            Module.deleted_at.is_(None),
            Course.deleted_at.is_(None),
        )
        .first()
    )
    if not row:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Chapter not found",
            context={"resource_type": "chapter", "resource_id": chapter_id},
        )
    return row[0], row[1], row[2]


def verify_chapter_access(db: Session, chapter_id: str, user: User) -> Chapter:
    chapter, _module, course = _resolve_chapter(db, chapter_id)

    if user.role == UserRole.ADMIN.value:
        return chapter
    if str(course.created_by) == str(user.id):
        return chapter
    if course.status != CourseStatus.PUBLISHED:
        # 404 (not 403) so an unpublished course's existence doesn't leak
        # to students probing chapter ids.
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Chapter not found",
            context={"resource_type": "chapter", "resource_id": chapter_id},
        )
    enrolled = db.query(Enrollment).filter(Enrollment.user_id == user.id, Enrollment.course_id == course.id).first()
    if not enrolled:
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="You must be enrolled in this course",
        )
    return chapter


def verify_chapter_owner(db: Session, chapter_id: str, teacher: User | str) -> tuple[Chapter, str]:
    """Resolve chapter -> module -> course and verify ownership.

    Returns ``(chapter, course_id)`` so callers can skip redundant lookups.
    """
    chapter, _module, course = _resolve_chapter(db, chapter_id)
    teacher_id = teacher.id if isinstance(teacher, User) else teacher
    if str(course.created_by) == str(teacher_id):
        return chapter, str(course.id)
    if not _resolve_admin_flag(db, teacher):
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="You do not own this course",
        )
    return chapter, str(course.id)


# Moved to ``app.services.domain_access`` for the same reason as
# ``assert_course_owner`` above. The re-export keeps existing call sites
# in this module working without churn.
from app.services.domain_access import resolve_chapter_course_id  # noqa: E402, F401  (re-export)
