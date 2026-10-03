"""Course catalog read endpoints (listings + detail views)."""

from fastapi import Depends, Header, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_optional_user, is_owner_or_admin, require_teacher
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.course import Course, CourseStatus
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.schemas.course import CourseResponse, CourseSummary, ModuleResponse
from app.schemas.locale import LocaleCode, normalize_locale
from app.services import guest_preview
from app.services.course_service import (
    get_course,
    get_courses,
    get_module,
    get_teacher_courses,
)
from app.services.reading_time import course_reading_minutes
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


@router.get("/my-organization", response_model=list[CourseSummary])
def list_my_organization_courses(
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    search: str | None = Query(None, min_length=1, max_length=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CourseSummary]:
    """Everything published inside the caller's own organization.

    A separate route rather than widening ``GET /courses``. That one is
    public and cached at the edge; making its answer depend on whether a
    token was sent would make the cache a liability — one reader's
    organization served to the next.

    Platform staff belong to no organization and get an empty list here,
    not an error: there is nothing wrong with the request, there is
    simply no "my organization" for them.
    """
    response.headers["Vary"] = "Accept-Language"
    if current_user.organization_id is None:
        return []
    display_locale: LocaleCode = normalize_locale(accept_language)
    courses = get_courses(
        db,
        skip=skip,
        limit=limit,
        search=search,
        organization_id=current_user.organization_id,
    )
    if not courses:
        return []
    return build_localized_course_summaries(db, courses, display_locale)


@router.get("/my", response_model=list[CourseSummary])
def list_my_courses(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    response.headers["Vary"] = "Accept-Language"
    display_locale = normalize_locale(accept_language) if accept_language else None
    return get_teacher_courses(db, current_user.id, skip=skip, limit=limit, display_locale=display_locale)


@router.get("/my/trash", response_model=list[CourseSummary])
def list_my_trashed_courses(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    response.headers["Vary"] = "Accept-Language"
    display_locale = normalize_locale(accept_language) if accept_language else None
    return get_teacher_courses(
        db, current_user.id, deleted_only=True, skip=skip, limit=limit, display_locale=display_locale
    )


def _course_a_reader_may_see(db: Session, course_id: str, current_user: User | None) -> Course:
    """The course, or the same 404 for "not there" and "not yours to see".

    Shared by the course page and everything a reader asks about the course
    from it, so the two cannot drift: what one hides the other must too.
    """
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
    # An ``institute`` course belongs to its organization and to nobody
    # else. Until 2026-08-27 anyone with the id could read the whole tree
    # of one, because there were no organizations to belong to.
    #
    # 404 rather than 403, deliberately. A 403 answers the question the
    # request was really asking — does this course exist — and a course id
    # is guessable enough to be worth not confirming. The owner and
    # platform staff still see it, and they are the only two who should
    # be able to tell the difference between "not yours" and "not there".
    if (
        course.access_mode == "institute"
        and not is_owner_or_admin(course, current_user)
        and not (
            current_user is not None
            and current_user.organization_id is not None
            and current_user.organization_id == course.organization_id
        )
    ):
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=404,
            message=f"Course '{course_id}' not found",
            context={"resource_type": "course", "resource_id": course_id},
        )
    return course


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
    course = _course_a_reader_may_see(db, course_id, current_user)
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
    # A chapter held for its first release is the owner's and the
    # admin's to see — the same two the ``?source=1`` gate above trusts.
    # Everybody else is a reader, and a reader is not shown it.
    localized = build_localized_course_response_with_tree(
        db, course, display_locale, hide_unreleased=not is_owner_or_admin(course, current_user)
    )
    # A guest, or a signed-in reader not enrolled yet: both may read the
    # first lesson before deciding.
    if current_user is None or not guest_preview.reads_course_as_enrolled(db, course, current_user):
        localized.preview_chapter_id = guest_preview.preview_chapter_id(db, course)
    return localized


class CourseReadingTime(BaseModel):
    """Minutes of reading per lesson, and the sum, in the reader's language."""

    chapters: dict[str, int]
    total_minutes: int


@router.get("/{course_id}/reading-time", response_model=CourseReadingTime)
def get_course_reading_time(
    course_id: str,
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> CourseReadingTime:
    """How long the course takes to read — the "about N hours" on the course page.

    Visible exactly when the course page is (``_course_a_reader_may_see``).
    Counted from the text blocks in the reader's language; see
    ``services/reading_time.py``.
    """
    course = _course_a_reader_may_see(db, course_id, current_user)
    response.headers["Vary"] = "Accept-Language"
    minutes = course_reading_minutes(db, course, normalize_locale(accept_language))
    return CourseReadingTime(chapters=minutes, total_minutes=sum(minutes.values()))


class CourseAuthor(BaseModel):
    """Who is teaching this course, as the «Автор» tab shows it."""

    name: str | None = None
    avatar_url: str | None = None
    #: The school's public name — what its certificates print, not localized.
    school: str | None = None


@router.get("/{course_id}/author", response_model=CourseAuthor)
def get_course_author(
    course_id: str,
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> CourseAuthor:
    """The course's author: a name, a face, a school. Nothing else.

    Visible exactly when the course page is (``_course_a_reader_may_see``) —
    it is the «кто ведёт» a visitor reads before enrolling, as on
    BibleProject's course pages. No email, no role: a stranger has no use
    for either.
    """
    course = _course_a_reader_may_see(db, course_id, current_user)
    author = db.query(User.full_name, User.avatar_url).filter(User.id == course.created_by).first()
    school = None
    if course.organization_id is not None:
        school = db.query(Organization.public_name).filter(Organization.id == course.organization_id).scalar()
    return CourseAuthor(
        name=author.full_name if author else None,
        avatar_url=author.avatar_url if author else None,
        school=school,
    )


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
        # ``?source=1`` is the editor asking for its own material. An
        # edit held back from readers until its translations land is
        # still this teacher's own text, and it outranks what is
        # currently released — otherwise the editor reopens the module
        # and finds the wording it replaced.
        from app.services.staged_edits import author_texts_bulk

        held = author_texts_bulk(
            db,
            entity_type="module",
            entity_ids=[str(module.id)],
            fields=["title", "description"],
        )
        module.title = (
            held.get((str(module.id), "title")) or human_by_field.get("title") or any_by_field.get("title") or ""
        )
        module.description = (
            held.get((str(module.id), "description"))
            or human_by_field.get("description")
            or any_by_field.get("description")
        )
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
        hide_unreleased=not (is_owner or is_admin),
    )
