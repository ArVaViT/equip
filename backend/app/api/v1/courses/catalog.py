"""Course catalog read endpoints (listings + detail views)."""

from fastapi import Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_optional_user, is_owner_or_admin, require_teacher
from app.core.database import get_db
from app.models.course import Course, CourseStatus
from app.models.user import User, UserRole
from app.schemas.course import CourseResponse, CourseSummary, ModuleResponse
from app.schemas.locale import LocaleCode, normalize_locale
from app.services.course_service import (
    get_course,
    get_courses,
    get_module,
    get_teacher_courses,
)
from app.services.translation.resolve_for_display import (
    batch_fetch_course_translations,
    build_localized_course_response_with_tree,
    build_localized_course_summary,
    build_localized_module_response,
    should_apply_course_translation_overlay,
)

from ._router import router


@router.get("", response_model=list[CourseSummary])
def list_courses(
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    search: str | None = Query(None, min_length=1, max_length=200),
    db: Session = Depends(get_db),
) -> list[CourseSummary]:
    # Catalog view: slim payload (no chapter body content).
    # Full tree is served from GET /courses/{id}.
    #
    # Cache-Control: the catalog is public (RLS restricts to published courses)
    # and changes on a human editorial cadence, not per-request. Short private
    # cache + a slightly longer CDN window with stale-while-revalidate keeps the
    # home page snappy without holding onto stale content for long.
    response.headers["Cache-Control"] = "public, max-age=30, s-maxage=60, stale-while-revalidate=120"
    response.headers["Vary"] = "Accept-Language"
    display_locale: LocaleCode = normalize_locale(accept_language)
    courses = get_courses(db, skip=skip, limit=limit, search=search)
    if not courses:
        return []
    overlay = batch_fetch_course_translations(
        db,
        course_ids=[c.id for c in courses],
        display_locale=display_locale,
    )
    return [build_localized_course_summary(c, overlay, display_locale) for c in courses]


@router.get("/my", response_model=list[CourseSummary])
def list_my_courses(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    return get_teacher_courses(db, current_user.id, skip=skip, limit=limit)


@router.get("/my/trash", response_model=list[CourseSummary])
def list_my_trashed_courses(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    return get_teacher_courses(db, current_user.id, deleted_only=True, skip=skip, limit=limit)


@router.get("/{course_id}", response_model=CourseResponse)
def get_course_detail(
    course_id: str,
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    source: bool = Query(
        False,
        description=(
            "Bypass the translation overlay and return source-language columns. "
            "Owner / admin only — used by the course editor so a teacher viewing "
            "their RU course in EN UI doesn't accidentally save the EN translation "
            "back into the source title/description."
        ),
    ),
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> CourseResponse:
    display_locale: LocaleCode = normalize_locale(accept_language)
    course = get_course(db, course_id)
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course '{course_id}' not found",
        )
    if course.status != CourseStatus.PUBLISHED and not is_owner_or_admin(course, current_user):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course '{course_id}' not found",
        )
    if source:
        # Explicit "give me source columns" path for editor surfaces. Gated to
        # owner + admin: returning unredacted source text to a regular student
        # is an information leak (typos, draft notes, unreleased material).
        if not is_owner_or_admin(course, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the course owner or an admin can request source-language content",
            )
        response.headers["Vary"] = "Accept-Language"
        return CourseResponse.model_validate(course, from_attributes=True)
    response.headers["Vary"] = "Accept-Language"
    if not should_apply_course_translation_overlay(course=course, current_user=current_user):
        return CourseResponse.model_validate(course, from_attributes=True)
    return build_localized_course_response_with_tree(db, course, display_locale)


@router.get("/{course_id}/modules/{module_id}", response_model=ModuleResponse)
def get_module_detail(
    course_id: str,
    module_id: str,
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    source: bool = Query(
        False,
        description=(
            "Bypass the translation overlay and return source-language columns. "
            "Owner / admin only — used by the module editor."
        ),
    ),
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> ModuleResponse:
    # Lightweight access probe — avoids loading the whole course→modules→chapters
    # tree just to check publication state. Pull source_locale here too so we
    # don't need a second course fetch to apply the translation overlay below.
    course_row = (
        db.query(Course.status, Course.created_by, Course.source_locale)
        .filter(Course.id == course_id, Course.deleted_at.is_(None))
        .first()
    )
    if not course_row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course '{course_id}' not found",
        )
    course_status, course_owner_id, course_source_locale = course_row
    if course_status != CourseStatus.PUBLISHED:
        if not current_user or (
            str(course_owner_id) != str(current_user.id) and current_user.role != UserRole.ADMIN.value
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Course '{course_id}' not found",
            )
    module = get_module(db, course_id, module_id)
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Module '{module_id}' not found in course '{course_id}'",
        )

    response.headers["Vary"] = "Accept-Language"

    is_owner = current_user is not None and str(course_owner_id) == str(current_user.id)
    is_admin = current_user is not None and current_user.role == UserRole.ADMIN.value

    # Explicit "give me source columns" path for editor surfaces. Owner / admin
    # only. Today's main also routes owner + admin to source via the implicit
    # ``should_apply_course_translation_overlay`` rule; the explicit param
    # survives once that implicit skip is removed (see PR #340).
    if source:
        if not (is_owner or is_admin):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the course owner or an admin can request source-language content",
            )
        return ModuleResponse.model_validate(module, from_attributes=True)

    # Owner + admin always see source for editorial accuracy (matches the
    # rule in ``should_apply_course_translation_overlay`` for the parent
    # course-detail endpoint). Everyone else (students, anonymous catalog
    # browsers, other teachers) gets the locale overlay.
    if is_owner or is_admin:
        return ModuleResponse.model_validate(module, from_attributes=True)

    display_locale: LocaleCode = normalize_locale(accept_language)
    source_locale: LocaleCode = normalize_locale(course_source_locale)
    return build_localized_module_response(
        db,
        module,
        display_locale=display_locale,
        source_locale=source_locale,
    )
