from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.course import Chapter, Course, CourseStatus, Module
from app.models.enrollment import Enrollment
from app.models.user import User, UserRole

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


# Sync so FastAPI runs it in the threadpool: keeps the event loop free while
# decode_access_token (possible Supabase HTTP call) and the User SELECT block.
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
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
    return db.query(User).filter(User.id == user_id).first()


def require_teacher(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role not in (UserRole.TEACHER.value, UserRole.ADMIN.value):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers can perform this action",
        )
    return current_user


def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return current_user


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


def assert_course_owner(
    course: Course,
    user: User,
    *,
    allow_admin: bool = True,
    detail: str = "You do not own this course",
) -> None:
    """Raise 403 unless ``user`` owns ``course`` (or is admin and allowed).

    Callers can override ``detail`` to return a more specific 403 message
    (e.g. "You can only approve certificates for your own courses"), which
    avoids wrapping this call in a ``try/except HTTPException`` block.

    For the non-raising form (predicate that returns ``bool``), use
    ``is_owner_or_admin``.
    """
    if str(course.created_by) == str(user.id):
        return
    if allow_admin and user.role == UserRole.ADMIN.value:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    teacher_id = teacher.id if isinstance(teacher, User) else teacher
    if str(course.created_by) == str(teacher_id):
        return course
    if allow_admin and _resolve_admin_flag(db, teacher):
        return course
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not own this course",
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chapter not found")
    return row[0], row[1], row[2]


def verify_chapter_access(db: Session, chapter_id: str, user: User) -> Chapter:
    chapter, _module, course = _resolve_chapter(db, chapter_id)

    if user.role == UserRole.ADMIN.value:
        return chapter
    if str(course.created_by) == str(user.id):
        return chapter
    if course.status != CourseStatus.PUBLISHED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chapter not found")
    enrolled = db.query(Enrollment).filter(Enrollment.user_id == user.id, Enrollment.course_id == course.id).first()
    if not enrolled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be enrolled in this course",
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this course",
        )
    return chapter, str(course.id)


def resolve_chapter_course_id(db: Session, chapter_id: str) -> str:
    """Return the course_id for a chapter (single joined query). Raises 404."""
    row = (
        db.query(Module.course_id)
        .join(Chapter, Chapter.module_id == Module.id)
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chapter not found")
    return row[0]
