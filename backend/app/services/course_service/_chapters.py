"""Chapter write operations (create / update / soft-delete)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func

from app.models.course import Chapter, Module
from app.services.content_versions import dual_write_entity_content
from app.services.domain_access import course_source_locale_for_chapter

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.schemas.course import ChapterCreate, ChapterUpdate


def _next_chapter_order(db: Session, course_id: str) -> int:
    """Return the tail ``order_index`` for a new chapter of this course.

    Course-global since 2026-09-07, where it used to be the maximum
    inside one module. The decided model is one order per course, with a
    module as a label whose members sit together — and a chapter that
    belongs to no module has no per-module maximum to be the tail of, so
    the old question had no answer for it.

    Existing courses keep the order they display. Chapters render as
    modules by ``module.order_index``, then chapters by
    ``order_index`` inside each module, and a course-global maximum plus
    one is by construction greater than any single module's maximum plus
    one: an appended chapter still lands at the tail of its own module,
    exactly where the per-module number used to put it. What changes is
    the number, not the position.
    """
    current_max = (
        db.query(func.max(Chapter.order_index))
        .filter(Chapter.course_id == course_id, Chapter.deleted_at.is_(None))
        .scalar()
    )
    return 0 if current_max is None else current_max + 1


def _course_id_for_module(db: Session, module_id: str) -> str:
    """The course a module belongs to — the parent a new chapter needs.

    Raises when the module does not exist. It used to return ``None``
    and let the NOT NULL on ``chapters.course_id`` refuse the row, which
    was fine while the course id was only ever a column value; the
    course-global ``order_index`` is now read *before* the row is built,
    so "no course" has to be an answer here rather than three statements
    later. Every route checks the module first, so this is a
    programming error, not a user's.
    """
    course_id: str | None = db.query(Module.course_id).filter(Module.id == module_id).scalar()
    if course_id is None:
        raise ValueError(f"Module '{module_id}' does not exist, so it names no course for the chapter")
    return course_id


def _resync_progress_for_chapter(db: Session, chapter: Chapter) -> None:
    """Recompute everybody's percentage on the course this chapter belongs to.

    Imported here rather than at module scope: ``_enrollment`` imports from
    this package too, and the pair would deadlock at import time.
    """
    from app.constants import GRADABLE_CHAPTER_TYPES
    from app.services.course_service._enrollment import resync_course_progress

    if chapter.chapter_type not in GRADABLE_CHAPTER_TYPES:
        # Reading chapters are not in the fraction, so nothing moved.
        return
    resync_course_progress(db, chapter.course_id)


def create_chapter(
    db: Session,
    module_id: str | None,
    data: ChapterCreate,
    *,
    course_id: str | None = None,
) -> Chapter:
    """Add a chapter to a course, under a module or directly.

    ``module_id`` is the group the lesson goes into, or ``None`` for a
    lesson that sits in the course itself — the shape a four-lesson
    course wants, and the one that used to force its teacher to invent
    modules for it.

    ``course_id`` names the course. It may be omitted only when a module
    is given, in which case the module's course is the answer — that is
    the call every existing caller makes, and it keeps meaning what it
    always did.
    """
    if course_id is None:
        if module_id is None:
            raise ValueError("create_chapter needs a course_id when no module groups the chapter")
        course_id = _course_id_for_module(db, module_id)
    # Mirrors ``create_module``: default order_index (0) appends at the tail
    # of the course. NB ``0`` is still read as "not given" — the falsiness
    # is the pre-existing contract with the editor, which sends the index
    # it thinks the chapter should have and sends 0 for the first one.
    order_index = data.order_index if data.order_index else _next_chapter_order(db, course_id)
    chapter = Chapter(
        id=str(uuid.uuid4()),
        module_id=module_id,
        course_id=course_id,
        title=data.title,
        order_index=order_index,
        chapter_type=data.chapter_type,
        requires_completion=data.requires_completion,
        is_locked=data.is_locked,
    )
    db.add(chapter)
    db.flush()
    dual_write_entity_content(
        db,
        entity_type="chapter",
        entity_id=str(chapter.id),
        texts={"title": data.title},
        # By the chapter's own course, like ``update_chapter`` — the module
        # is not asked.
        fallback_locale=course_source_locale_for_chapter(db, chapter.id),
    )
    db.commit()
    db.refresh(chapter)
    # Adding a quiz enlarges the denominator for everybody already enrolled.
    _resync_progress_for_chapter(db, chapter)
    return chapter


def update_chapter(db: Session, chapter: Chapter, data: ChapterUpdate) -> Chapter:
    patch = data.model_dump(exclude_unset=True)
    # Whether this patch moves the lesson to another group (or out of
    # one). Read before the patch is applied, because after it the old
    # grouping is gone. ``module_id`` is checked against the course by
    # the route; nothing here can change which course a chapter is in.
    regrouped = "module_id" in patch and patch["module_id"] != chapter.module_id
    for field, value in patch.items():
        setattr(chapter, field, value)
    if regrouped and "order_index" not in patch:
        # A lesson that changes group without being told where to sit
        # goes to the end of the course. Keeping the number it had would
        # collide with whatever chapter already holds it in the new
        # group, and two chapters sharing an ``order_index`` are shown in
        # whichever order the query plan felt like — the same class of
        # defect that had chapters rendering backwards before the
        # relationship got its explicit ``order_by``.
        chapter.order_index = _next_chapter_order(db, chapter.course_id)
    db.flush()
    if "title" in patch:
        dual_write_entity_content(
            db,
            entity_type="chapter",
            entity_id=str(chapter.id),
            texts={"title": patch["title"]},
            fallback_locale=course_source_locale_for_chapter(db, chapter.id),
        )
    db.commit()
    db.refresh(chapter)
    if "chapter_type" in patch:
        # A lesson turned into a quiz (or back) changes what counts.
        _resync_progress_for_chapter(db, chapter)
    return chapter


def delete_chapter(db: Session, chapter: Chapter) -> None:
    chapter.deleted_at = datetime.now(UTC)
    db.commit()
    # The percentage is a fraction of the course's gradable chapters, so
    # removing one moves the denominator for every student at once. Without
    # this, a student who had passed the deleted quiz keeps the percentage
    # it earned them for ever — four enrolments on production were stored at
    # 100% while the teacher's board counted 0/5 beside them.
    _resync_progress_for_chapter(db, chapter)
