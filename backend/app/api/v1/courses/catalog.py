"""Course catalog read endpoints (listings + detail views)."""

from fastapi import Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_optional_user, is_owner_or_admin, require_teacher
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
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
    build_localized_course_response_with_tree,
    build_localized_course_summaries,
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
    return build_localized_course_summaries(db, courses, display_locale)


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
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            message=f"Course '{course_id}' not found",
            context={"resource_type": "course", "resource_id": course_id},
        )
    if course.status != CourseStatus.PUBLISHED and not is_owner_or_admin(course, current_user):
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            message=f"Course '{course_id}' not found",
            context={"resource_type": "course", "resource_id": course_id},
        )
    if source:
        # Explicit "give me source columns" path for editor surfaces. Gated to
        # owner + admin: returning unredacted source text to a regular student
        # is an information leak (typos, draft notes, unreleased material).
        if not is_owner_or_admin(course, current_user):
            raise equip_error(
                ErrorCode.AUTH_FORBIDDEN,
                status_code=403,
                message="Only the course owner or an admin can request source-language content",
                context={"resource_type": "course", "resource_id": course_id},
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
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            message=f"Course '{course_id}' not found",
            context={"resource_type": "course", "resource_id": course_id},
        )
    course_status, course_owner_id, course_source_locale = course_row
    if course_status != CourseStatus.PUBLISHED:
        if not current_user or (
            str(course_owner_id) != str(current_user.id) and current_user.role != UserRole.ADMIN.value
        ):
            raise equip_error(
                ErrorCode.RESOURCE_NOT_FOUND,
                status_code=404,
                message=f"Course '{course_id}' not found",
                context={"resource_type": "course", "resource_id": course_id},
            )
    module = get_module(db, course_id, module_id)
    if not module:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            message=f"Module '{module_id}' not found in course '{course_id}'",
            context={"resource_type": "module", "resource_id": module_id, "course_id": course_id},
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
            raise equip_error(
                ErrorCode.AUTH_FORBIDDEN,
                status_code=403,
                message="Only the course owner or an admin can request source-language content",
                context={"resource_type": "course", "resource_id": course_id},
            )
        # ``?source=1`` returns the teacher-authored source text regardless
        # of overlay locale. Read the earliest active human-origin row
        # per field; fall back to the earliest of any origin so a content
        # row written by an importer still surfaces.
        from app.models.content_version import ContentVersion, ContentVersionStatus

        cv_rows = (
            db.query(ContentVersion.field, ContentVersion.text, ContentVersion.origin)
            .filter(
                ContentVersion.entity_type == "module",
                ContentVersion.entity_id == str(module.id),
                ContentVersion.field.in_(["title", "description"]),
                ContentVersion.superseded_by.is_(None),
                ContentVersion.status == ContentVersionStatus.OK,
            )
            .order_by(ContentVersion.created_at)
            .all()
        )
        human_by_field: dict[str, str] = {}
        any_by_field: dict[str, str] = {}
        for field, text, origin in cv_rows:
            any_by_field.setdefault(field, text)
            if origin == "human":
                human_by_field.setdefault(field, text)
        module.title = human_by_field.get("title") or any_by_field.get("title") or ""
        module.description = human_by_field.get("description") or any_by_field.get("description")
        return ModuleResponse.model_validate(module, from_attributes=True)

    # No implicit bypass. Reading is reading, whoever is reading — the
    # editor asks for source text with ``?source=1``, which every editor
    # surface in the web app already sends. This route kept the old
    # role-based bypass after the course-detail route dropped it, so an
    # admin checking the German build got the module and every chapter
    # under it in Russian.

    display_locale: LocaleCode = normalize_locale(accept_language)
    source_locale: LocaleCode = normalize_locale(course_source_locale)
    return build_localized_module_response(
        db,
        module,
        display_locale=display_locale,
        source_locale=source_locale,
    )
