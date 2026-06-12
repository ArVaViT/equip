import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_admin
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.user import User
from app.schemas.course import CourseDashboardSummary, EnrollmentSummaryResponse
from app.schemas.locale import LocaleCode, normalize_locale
from app.schemas.user import PreferredLocaleUpdate, UserResponse
from app.services.audit_service import log_action
from app.services.course_service import get_user_courses
from app.services.translation.resolve_for_display import (
    build_localized_course_dashboard_summaries,
    populate_spine_texts,
    should_apply_course_translation_overlay,
)

logger = logging.getLogger(__name__)

VALID_ROLES = ("admin", "teacher", "student")

router = APIRouter(prefix="/users", tags=["users"])


def _parse_user_uuid(user_id: str) -> UUID:
    """Parse a path-parameter user id or raise 404.

    Invalid UUIDs are indistinguishable from missing users at the API
    surface, so we normalise both to "User not found".
    """
    try:
        return UUID(user_id)
    except ValueError:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="User not found",
            context={"resource_type": "user", "resource_id": user_id},
        ) from None


@router.get("/me/courses", response_model=list[EnrollmentSummaryResponse])
def get_my_courses(
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[EnrollmentSummaryResponse]:
    # Dashboard view: slim payload — only course scalars (no module/chapter
    # tree). ``get_user_courses`` loads courses WITHOUT the tree, so all text
    # hydration here is course-only (``hydrate_modules=False``) to avoid an
    # N+1 lazy-load over modules the dashboard never renders.
    response.headers["Vary"] = "Accept-Language"
    display_locale: LocaleCode = normalize_locale(accept_language)
    rows = get_user_courses(db, current_user.id, skip=skip, limit=limit)
    if not rows:
        return []
    courses = [e.course for e in rows if e.course is not None]
    if not courses:
        return [EnrollmentSummaryResponse.model_validate(e, from_attributes=True) for e in rows]
    # Pre-hydrate course title/description at the source locale (baseline used
    # by the owner / admin non-overlay path). The student / non-owner path
    # overwrites with a display-locale summary below; overlay choice is
    # per-course and depends on the caller's role.
    populate_spine_texts(db, courses, hydrate_modules=False)
    localized = {
        c.id: s
        for c, s in zip(
            courses,
            build_localized_course_dashboard_summaries(db, courses, display_locale),
            strict=True,
        )
    }
    out: list[EnrollmentSummaryResponse] = []
    for e in rows:
        if e.course is None:
            out.append(EnrollmentSummaryResponse.model_validate(e, from_attributes=True))
            continue
        c = e.course
        summary = (
            localized[c.id]
            if should_apply_course_translation_overlay(course=c, current_user=current_user)
            else CourseDashboardSummary.model_validate(c, from_attributes=True)
        )
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

    # ``log_action`` COMMITS the session itself (its trailing commit is
    # load-bearing — see audit_service.py). Calling it here, after the
    # locale mutation, makes the locale change and the audit row durable
    # in the SAME commit — both visible or both rolled back. The explicit
    # ``db.commit()`` below is then a no-op kept for readability; do NOT
    # reorder this call after other uncommitted writes you don't want
    # committed along with it.
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


class AdminUserRow(BaseModel):
    id: str
    email: str
    full_name: str | None
    role: str
    avatar_url: str | None
    created_at: datetime | None
    # Non-null when the account is soft-deleted; the admin panel surfaces this
    # so a deactivated user can be told apart and restored.
    deactivated_at: datetime | None


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
            deactivated_at=u.deactivated_at,
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
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Invalid role",
            context={"resource_type": "user", "role": body.role, "valid_roles": list(VALID_ROLES)},
        )
    if len(body.user_ids) > 100:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Maximum 100 users per batch",
            context={"resource_type": "user", "submitted": len(body.user_ids), "max": 100},
        )

    valid_uuids: list[UUID] = []
    for uid_str in body.user_ids:
        try:
            valid_uuids.append(UUID(uid_str))
        except ValueError:
            continue

    if not valid_uuids:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="No valid user IDs provided",
            context={"resource_type": "user"},
        )

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
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Invalid role",
            context={"resource_type": "user", "role": role, "valid_roles": list(VALID_ROLES)},
        )
    uid = _parse_user_uuid(user_id)
    if uid == admin.id:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Cannot change your own role",
            context={"resource_type": "user", "user_id": str(uid)},
        )
    user = db.query(User).filter(User.id == uid).first()
    if not user:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="User not found",
            context={"resource_type": "user", "resource_id": str(uid)},
        )
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
    """Soft-delete (deactivate) another user.

    Sets ``deactivated_at`` and blocks the account's login, but PRESERVES every
    owned row (courses, grades, certificates) so the account can be restored
    via ``POST /admin/users/{id}/restore``. This is deliberately reversible —
    it avoids the old half-state where data was hard-deleted while the auth
    identity lingered and resurrected an empty profile on next login.

    An admin cannot delete themselves via this route — that would leave the
    platform without an admin in the worst case. If the last admin truly wants
    to leave, a direct SQL operation through Supabase is the right escape hatch.
    """
    uid = _parse_user_uuid(user_id)
    if uid == admin.id:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Admins cannot delete their own account",
            context={"resource_type": "user", "user_id": str(uid)},
        )

    target = db.query(User).filter(User.id == uid).first()
    if not target:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="User not found",
            context={"resource_type": "user", "resource_id": str(uid)},
        )

    if target.deactivated_at is not None:
        # Already deactivated — idempotent success.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    try:
        log_action(
            db,
            admin.id,
            "delete",
            "user",
            str(uid),
            details={"email": target.email, "role": target.role, "mode": "soft_delete"},
            request=request,
        )
        target.deactivated_at = datetime.now(UTC)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Admin-initiated deactivation failed for user %s", uid)
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="User deletion failed. Please try again or contact support.",
            context={"resource_type": "user", "user_id": str(uid)},
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/admin/users/{user_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
def admin_restore_user(
    user_id: str,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    """Reactivate a soft-deleted account (clears ``deactivated_at``).

    The user's data was preserved on deactivation, so restoring re-enables
    login and returns the account exactly as it was.
    """
    uid = _parse_user_uuid(user_id)

    target = db.query(User).filter(User.id == uid).first()
    if not target:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="User not found",
            context={"resource_type": "user", "resource_id": str(uid)},
        )

    if target.deactivated_at is None:
        # Already active — idempotent success.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    log_action(
        db,
        admin.id,
        "restore",
        "user",
        str(uid),
        details={"email": target.email, "role": target.role},
        request=request,
    )

    target.deactivated_at = None
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
