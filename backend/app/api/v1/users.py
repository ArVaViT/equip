import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_admin
from app.core.database import get_db
from app.models.assignment import AssignmentSubmission
from app.models.audit_log import AuditLog
from app.models.certificate import Certificate
from app.models.chapter_progress import ChapterProgress
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.notification import Notification
from app.models.quiz import QuizAnswer, QuizAttempt
from app.models.review import CourseReview
from app.models.student_grade import StudentGrade
from app.models.user import User
from app.schemas.course import CourseSummary, EnrollmentSummaryResponse
from app.schemas.locale import LocaleCode, normalize_locale
from app.schemas.user import PreferredLocaleUpdate, UserResponse
from app.services.audit_service import log_action
from app.services.course_service import get_user_courses
from app.services.translation.resolve_for_display import (
    batch_fetch_course_translations,
    build_localized_course_summary,
    should_apply_course_translation_overlay,
)

logger = logging.getLogger(__name__)

VALID_ROLES = ("admin", "teacher", "pending_teacher", "student")

router = APIRouter(prefix="/users", tags=["users"])


def _parse_user_uuid(user_id: str) -> UUID:
    """Parse a path-parameter user id or raise 404.

    Invalid UUIDs are indistinguishable from missing users at the API
    surface, so we normalise both to "User not found".
    """
    try:
        return UUID(user_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found") from None


@router.get("/me/courses", response_model=list[EnrollmentSummaryResponse])
def get_my_courses(
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[EnrollmentSummaryResponse]:
    # Dashboard view: slim payload (chapter body content stripped).
    response.headers["Vary"] = "Accept-Language"
    display_locale: LocaleCode = normalize_locale(accept_language)
    rows = get_user_courses(db, current_user.id, skip=skip, limit=limit)
    if not rows:
        return []
    courses = [e.course for e in rows if e.course is not None]
    if not courses:
        return [EnrollmentSummaryResponse.model_validate(e, from_attributes=True) for e in rows]
    overlay = batch_fetch_course_translations(db, course_ids=[c.id for c in courses], display_locale=display_locale)
    out: list[EnrollmentSummaryResponse] = []
    for e in rows:
        if e.course is None:
            out.append(EnrollmentSummaryResponse.model_validate(e, from_attributes=True))
            continue
        c = e.course
        if should_apply_course_translation_overlay(course=c, current_user=current_user):
            summary = build_localized_course_summary(c, overlay, display_locale)
        else:
            summary = CourseSummary.model_validate(c, from_attributes=True)
        base = EnrollmentSummaryResponse.model_validate(e, from_attributes=True)
        out.append(base.model_copy(update={"course": summary}))
    return out


@router.patch("/me/preferences", response_model=UserResponse)
def update_my_preferences(
    body: PreferredLocaleUpdate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Persist the user's preferred locale.

    The frontend hits this whenever the language switcher changes so the
    choice survives across devices. We audit-log the change because role-
    elevated users (teachers/admins) flipping languages can affect what they
    see in the editor and we want a paper trail for support tickets.
    """
    if current_user.preferred_locale == body.preferred_locale:
        return current_user

    previous = current_user.preferred_locale
    current_user.preferred_locale = body.preferred_locale

    # Audit log MUST share a transaction with the locale change. Writing
    # the audit row before the commit means a single COMMIT either makes
    # both visible or rolls both back — there is never a window in which
    # the new locale is durable but the audit trail is missing.
    log_action(
        db,
        current_user.id,
        "update",
        "user_preferences",
        str(current_user.id),
        details={"preferred_locale": {"from": previous, "to": body.preferred_locale}},
        request=request,
    )

    db.commit()
    db.refresh(current_user)

    return current_user


def _purge_user(db: Session, uid: UUID) -> None:
    """Delete every row that belongs to ``uid`` and then the ``User`` itself.

    Shared by the admin-delete-user path. We walk the FKs manually instead of
    relying on ``ON DELETE CASCADE`` because several tables intentionally keep
    history (``courses.created_by``, ``audit_logs.user_id``) — those get
    nulled out rather than removed. Runs inside the caller's transaction so a
    partial failure rolls back cleanly.
    """
    db.query(ChapterProgress).filter(ChapterProgress.user_id == uid).delete(synchronize_session=False)
    db.query(Notification).filter(Notification.user_id == uid).delete(synchronize_session=False)

    # Delete every QuizAnswer whose parent QuizAttempt belongs to this user,
    # then the QuizAttempts themselves. The answer delete is a single SQL
    # round-trip (subquery against QuizAttempt) instead of pulling all
    # attempt IDs into Python first — same result, one fewer query and no
    # memory overhead proportional to attempt count.
    db.query(QuizAnswer).filter(
        QuizAnswer.attempt_id.in_(db.query(QuizAttempt.id).filter(QuizAttempt.user_id == uid))
    ).delete(synchronize_session=False)
    db.query(QuizAttempt).filter(QuizAttempt.user_id == uid).delete(synchronize_session=False)

    db.query(AssignmentSubmission).filter(AssignmentSubmission.student_id == uid).delete(synchronize_session=False)
    db.query(StudentGrade).filter(StudentGrade.student_id == uid).delete(synchronize_session=False)
    db.query(Enrollment).filter(Enrollment.user_id == uid).delete(synchronize_session=False)
    db.query(CourseReview).filter(CourseReview.user_id == uid).delete(synchronize_session=False)
    db.query(Certificate).filter(Certificate.user_id == uid).delete(synchronize_session=False)

    db.query(Course).filter(Course.created_by == uid).update(
        {Course.created_by: None},
        synchronize_session=False,
    )
    db.query(AuditLog).filter(AuditLog.user_id == uid).update(
        {AuditLog.user_id: None},
        synchronize_session=False,
    )

    db.query(User).filter(User.id == uid).delete(synchronize_session=False)


class AdminUserRow(BaseModel):
    id: str
    email: str
    full_name: str | None
    role: str
    avatar_url: str | None
    created_at: datetime | None


@router.get("/admin/users", response_model=list[AdminUserRow])
def list_all_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AdminUserRow]:
    users = db.query(User).order_by(User.created_at.desc()).offset(skip).limit(limit).all()
    return [
        AdminUserRow(
            id=str(u.id),
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            avatar_url=u.avatar_url,
            created_at=u.created_at,
        )
        for u in users
    ]


class BulkRoleUpdate(BaseModel):
    user_ids: list[str]
    role: str


@router.put("/admin/users/bulk-role")
def bulk_update_user_roles(
    body: BulkRoleUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    if body.role not in VALID_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role")
    if len(body.user_ids) > 100:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Maximum 100 users per batch")

    valid_uuids: list[UUID] = []
    for uid_str in body.user_ids:
        try:
            valid_uuids.append(UUID(uid_str))
        except ValueError:
            continue

    if not valid_uuids:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No valid user IDs provided")

    # Admins must not demote themselves; silently skip their own id.
    safe_uuids = [u for u in valid_uuids if u != admin.id]

    updated = db.query(User).filter(User.id.in_(safe_uuids)).update({User.role: body.role}, synchronize_session="fetch")
    db.commit()

    log_action(
        db,
        admin.id,
        "bulk_role_update",
        "user",
        ",".join(str(u) for u in safe_uuids[:10]),
        details={"new_role": body.role, "count": updated},
        request=request,
    )

    return {"updated": updated, "role": body.role}


@router.put("/admin/users/{user_id}/role")
def update_user_role(
    user_id: str,
    request: Request,
    # Validated against ``VALID_ROLES`` below; cap keeps Pydantic from
    # parsing a multi-MB role string before that allow-list check runs.
    role: str = Query(..., max_length=32),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    if role not in VALID_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role")
    uid = _parse_user_uuid(user_id)
    if uid == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot change your own role")
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    old_role = user.role
    user.role = role
    db.commit()
    db.refresh(user)
    log_action(
        db, admin.id, "update", "user", user_id, details={"old_role": old_role, "new_role": role}, request=request
    )
    return {"id": str(user.id), "email": user.email, "role": user.role}


@router.delete("/admin/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def admin_delete_user(
    user_id: str,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    """Hard-delete another user and all their owned rows.

    An admin cannot delete themselves via this route — that would leave the
    platform without an admin in the worst case. Self-deletion is disabled by
    design: users cannot delete their own accounts from the UI. If the last
    admin truly wants to leave, a direct SQL operation through Supabase is the
    right escape hatch.
    """
    uid = _parse_user_uuid(user_id)
    if uid == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Admins cannot delete their own account")

    target = db.query(User).filter(User.id == uid).first()
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    log_action(
        db,
        admin.id,
        "delete",
        "user",
        str(uid),
        details={"email": target.email, "role": target.role},
        request=request,
    )

    try:
        _purge_user(db, uid)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Admin-initiated deletion failed for user %s", uid)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User deletion failed. Please try again or contact support.",
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
