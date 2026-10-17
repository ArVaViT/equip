"""Chapter write operations (create / update / soft-delete)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.course import Chapter, Module
from app.services.content_versions import dual_write_entity_content
from app.services.course_service._outline import live_spine, next_outline_order, write_outline
from app.services.course_structure import places_of
from app.services.domain_access import course_source_locale_for_chapter

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.schemas.course import ChapterCreate, ChapterUpdate


def _next_chapter_order(db: Session, course_id: str) -> int:
    """Return the tail ``order_index`` for a new chapter of this course.

    The place after everything the course holds, modules included — see
    ``_outline.next_outline_order``. A lesson appended into a module
    lands at that module's tail (inside a module its number only has to
    be the largest there), and a loose one at the tail of the course.
    """
    return next_outline_order(db, course_id)


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
    from app.services.course_service._enrollment import resync_course_progress

    # Any chapter, not only a gradable one: on a course with nothing to
    # assess, reading chapters *are* the fraction, and a reading chapter
    # added or removed moved everybody's percentage (2026-10-03).
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


def _seat_after_module(db: Session, chapter: Chapter, module_id: str) -> None:
    """Renumber the course so ``chapter`` — already detached from
    ``module_id`` in memory — sits right after that module."""
    db.flush()
    places = [(m, ids) for m, ids in places_of(live_spine(db, chapter.course_id)) if chapter.id not in ids]
    at = next((i + 1 for i, (m, _) in enumerate(places) if m == module_id), len(places))
    places.insert(at, (None, [chapter.id]))
    write_outline(db, chapter.course_id, places)


def update_chapter(db: Session, chapter: Chapter, data: ChapterUpdate) -> Chapter:
    patch = data.model_dump(exclude_unset=True)
    # Whether this patch moves the lesson to another group (or out of
    # one). Read before the patch is applied, because after it the old
    # grouping is gone. ``module_id`` is checked against the course by
    # the route; nothing here can change which course a chapter is in.
    regrouped = "module_id" in patch and patch["module_id"] != chapter.module_id
    leaving_module = chapter.module_id if regrouped and patch["module_id"] is None else None
    for field, value in patch.items():
        setattr(chapter, field, value)
    if regrouped and "order_index" not in patch:
        if leaving_module is not None:
            # Out of a module, the lesson stays where it was: right after
            # the module it leaves, not at the far end of the course.
            _seat_after_module(db, chapter, leaving_module)
        else:
            # Into a module: at that module's tail. Keeping the number it
            # had could collide with a lesson already there, and two
            # lessons sharing a number read in whichever order the query
            # plan felt like.
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


def restore_chapter(db: Session, chapter: Chapter) -> Chapter:
    """Bring a deleted lesson back — the "Undo" after a delete.

    Deleting only ever stamped ``deleted_at``; the lesson, its blocks, its
    quiz and every translation stayed where they were, so nothing needs
    rebuilding. The progress resync runs again for the same reason it runs
    on delete: the course's gradable chapters just changed.
    """
    chapter.deleted_at = None
    # A binned lesson keeps the module it was binned under (``delete_module``
    # frees only live lessons). If that module has since been deleted, the
    # lesson would come back into a module nobody can see, so it comes back
    # into the course instead, at its tail.
    if chapter.module_id is not None:
        home = db.get(Module, chapter.module_id)
        if home is None or home.deleted_at is not None:
            chapter.module_id = None
            chapter.order_index = _next_chapter_order(db, chapter.course_id)
    # Its number may have been given away meanwhile: delete the last lesson,
    # add a new one (it takes the freed tail number), then Undo — and two
    # lessons shared one place. Then it goes to the tail instead.
    taken = (
        db.query(Chapter.id)
        .filter(
            Chapter.course_id == chapter.course_id,
            Chapter.deleted_at.is_(None),
            Chapter.id != chapter.id,
            Chapter.order_index == chapter.order_index,
        )
        .first()
    )
    if taken is None and chapter.module_id is None:
        # A loose lesson shares its numbers with the modules, too.
        taken = (
            db.query(Module.id)
            .filter(
                Module.course_id == chapter.course_id,
                Module.deleted_at.is_(None),
                Module.order_index == chapter.order_index,
            )
            .first()
        )
    if taken is not None:
        chapter.order_index = _next_chapter_order(db, chapter.course_id)
    db.commit()
    db.refresh(chapter)
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
