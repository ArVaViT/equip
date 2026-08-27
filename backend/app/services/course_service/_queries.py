"""Read-side helpers for courses / modules / chapters.

Every query uses the shared ``_COURSE_TREE`` loader to avoid the
cartesian row explosion a chained ``joinedload`` would produce on
large courses.

Every getter that returns courses (or modules) hydrates their
``.title`` / ``.description`` runtime attributes from
``content_versions`` before returning, so downstream code that reads
``course.title`` etc. keeps working unchanged after the column drop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import joinedload, selectinload

from app.models.content_version import ContentVersion, ContentVersionStatus
from app.models.course import Chapter, Course, CourseStatus, Module
from app.services.translation.resolve_for_display import populate_module_texts, populate_spine_texts

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

# Eager-load modules + their chapters without the cartesian row explosion a
# chained ``joinedload`` would produce: one IN query per level means the
# course detail page fetches ~3 rows of wire instead of ``courses * modules
# * chapters`` when a course has many chapters.
#
# The ``.and_()`` filters strip soft-deleted children at load time so the
# course tree mirrors what students actually see. Trash and restore flows
# operate via bulk UPDATEs (see ``_courses.delete_course`` / ``restore_course``)
# so they don't depend on this filtered relationship.
_COURSE_TREE: tuple = (
    selectinload(Course.modules.and_(Module.deleted_at.is_(None))).selectinload(
        Module.chapters.and_(Chapter.deleted_at.is_(None))
    ),
)

# Slim loader for **catalog** views: pulls each course's modules so the UI
# can show "X modules" on a card, but skips the chapter level entirely. A
# typical catalog with 10 courses x 5 modules x 10 chapters drops from
# ~500 rows of chapter wire data per page to zero, with no UI regression —
# ``CourseCard`` only consumes ``course.modules?.length``. Course-detail
# requests stay on the full ``_COURSE_TREE`` so the nested chapter list
# is still there for the enrolled-course view.
_COURSE_LIST_TREE: tuple = (selectinload(Course.modules.and_(Module.deleted_at.is_(None))),)


def _hydrate(db: Session, courses: list[Course]) -> list[Course]:
    """Call ``populate_spine_texts`` and return the same list — convenience
    so getters can ``return _hydrate(db, query.all())``."""
    populate_spine_texts(db, courses)
    return courses


def get_courses(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 100,
    search: str | None = None,
    organization_id: UUID | None = None,
) -> list[Course]:
    """The public catalogue, or one organization's own list.

    Without ``organization_id`` this is the catalogue a stranger sees:
    every published course marked ``public``, whichever organization made
    it. That is the decided shape — a public course is public, and the
    catalogue naming the organization behind it is what makes the name
    worth having.

    ``institute`` courses are an organization's own and were in this list
    until 2026-08-27, visible to anyone who opened the home page. Passing
    an organization returns that organization's published courses
    instead, both kinds, for the people who belong to it.
    """
    query = (
        db.query(Course)
        .options(*_COURSE_LIST_TREE)
        .filter(Course.status == CourseStatus.PUBLISHED, Course.deleted_at.is_(None))
    )
    if organization_id is None:
        query = query.filter(Course.access_mode == "public")
    else:
        query = query.filter(Course.organization_id == organization_id)
    if search:
        # Catalog search runs ILIKE against ``content_versions`` text rows
        # for course title + description (any locale matches → the course
        # surfaces). Dropping the title column removed the Postgres tsvector
        # + GIN index that previously backed an FTS query here.
        # TODO(@scale >= ~2000 courses): re-introduce FTS by materialising
        # a tsvector column on ``content_versions``. ILIKE is fine while
        # the active row count stays below ~50k (typical Bible-school
        # catalog with handfuls of courses x {ru,en} x revision history).
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        term = f"%{escaped}%"
        matching_ids_stmt = (
            select(ContentVersion.entity_id)
            .where(
                ContentVersion.entity_type == "course",
                ContentVersion.field.in_(["title", "description"]),
                ContentVersion.superseded_by.is_(None),
                ContentVersion.status == ContentVersionStatus.OK,
                ContentVersion.text.ilike(term),
            )
            .distinct()
        )
        query = query.filter(Course.id.in_(matching_ids_stmt))
    return _hydrate(db, query.order_by(Course.created_at.desc()).offset(skip).limit(limit).all())


def get_course(db: Session, course_id: str, include_deleted: bool = False) -> Course | None:
    query = db.query(Course).options(*_COURSE_TREE).filter(Course.id == course_id)
    if not include_deleted:
        query = query.filter(Course.deleted_at.is_(None))
    course = query.first()
    if course is not None:
        _hydrate(db, [course])
    return course


def get_teacher_courses(
    db: Session,
    teacher_id: str | UUID,
    *,
    deleted_only: bool = False,
    skip: int = 0,
    limit: int | None = None,
) -> list[Course]:
    # ``_COURSE_LIST_TREE`` (modules only, no chapters) keeps the
    # teacher dashboard fast even when the teacher owns many courses
    # with many chapters each — the dashboard CourseCard only reads
    # ``course.modules?.length`` and the per-course actions navigate
    # into the editor for full-tree fetches.
    query = db.query(Course).options(*_COURSE_LIST_TREE).filter(Course.created_by == teacher_id)
    query = query.filter(Course.deleted_at.isnot(None)) if deleted_only else query.filter(Course.deleted_at.is_(None))
    query = query.order_by(Course.created_at.desc())
    if skip:
        query = query.offset(skip)
    if limit is not None:
        query = query.limit(limit)
    return _hydrate(db, query.all())


def get_module(db: Session, course_id: str, module_id: str) -> Module | None:
    module = (
        db.query(Module)
        .options(joinedload(Module.chapters.and_(Chapter.deleted_at.is_(None))))
        .filter(
            Module.id == module_id,
            Module.course_id == course_id,
            Module.deleted_at.is_(None),
        )
        .first()
    )
    if module is not None:
        # Single module: look up the parent course's source_locale for fallback.
        from app.schemas.locale import normalize_locale

        src = db.query(Course.source_locale).filter(Course.id == course_id).scalar() or "en"
        populate_module_texts(db, [module], source_locale=normalize_locale(src))
    return module


def get_chapter(db: Session, course_id: str, module_id: str, chapter_id: str) -> Chapter | None:
    return (
        db.query(Chapter)
        .join(Module, Chapter.module_id == Module.id)
        .filter(
            Chapter.id == chapter_id,
            Chapter.module_id == module_id,
            Module.course_id == course_id,
            Chapter.deleted_at.is_(None),
            Module.deleted_at.is_(None),
        )
        .first()
    )
