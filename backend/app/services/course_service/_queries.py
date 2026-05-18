"""Read-side helpers for courses / modules / chapters.

Every query uses the shared ``_COURSE_TREE`` loader to avoid the
cartesian row explosion a chained ``joinedload`` would produce on
large courses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload, selectinload

from app.models.course import Chapter, Course, CourseStatus, Module

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
_COURSE_LIST_TREE: tuple = (
    selectinload(Course.modules.and_(Module.deleted_at.is_(None))),
)


def get_courses(
    db: Session,
    *,
    skip: int = 0,
    limit: int = 100,
    search: str | None = None,
) -> list[Course]:
    query = (
        db.query(Course)
        .options(*_COURSE_LIST_TREE)
        .filter(Course.status == CourseStatus.PUBLISHED, Course.deleted_at.is_(None))
    )
    if search:
        ts_query = func.plainto_tsquery("russian", search)
        ts_query_en = func.plainto_tsquery("english", search)
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        term = f"%{escaped}%"
        query = query.filter(
            or_(
                Course.search_vector.op("@@")(ts_query),
                Course.search_vector.op("@@")(ts_query_en),
                Course.title.ilike(term),
                Course.description.ilike(term),
            )
        )
    return query.order_by(Course.created_at.desc()).offset(skip).limit(limit).all()


def get_course(db: Session, course_id: str, include_deleted: bool = False) -> Course | None:
    query = db.query(Course).options(*_COURSE_TREE).filter(Course.id == course_id)
    if not include_deleted:
        query = query.filter(Course.deleted_at.is_(None))
    return query.first()


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
    return query.all()


def get_module(db: Session, course_id: str, module_id: str) -> Module | None:
    return (
        db.query(Module)
        .options(joinedload(Module.chapters.and_(Chapter.deleted_at.is_(None))))
        .filter(
            Module.id == module_id,
            Module.course_id == course_id,
            Module.deleted_at.is_(None),
        )
        .first()
    )


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
