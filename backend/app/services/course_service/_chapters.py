"""Chapter write operations (create / update / soft-delete)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func

from app.models.course import Chapter, Course, Module
from app.services.content_versions import dual_write_entity_content

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.schemas.course import ChapterCreate, ChapterUpdate


def _next_chapter_order(db: Session, module_id: str) -> int:
    """Return the tail ``order_index`` for a new chapter on this module."""
    current_max = (
        db.query(func.max(Chapter.order_index))
        .filter(Chapter.module_id == module_id, Chapter.deleted_at.is_(None))
        .scalar()
    )
    return 0 if current_max is None else current_max + 1


def _course_source_locale_for_module(db: Session, module_id: str) -> str | None:
    """Walk ``Chapter -> Module -> Course`` to find the parent course's
    source locale. Used as the fallback when a chapter title alone
    can't be classified by the language detector.
    """
    return (
        db.query(Course.source_locale)
        .join(Module, Module.course_id == Course.id)
        .filter(Module.id == module_id)
        .scalar()
    )


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
    course_id = db.query(Module.course_id).filter(Module.id == chapter.module_id).scalar()
    if course_id:
        resync_course_progress(db, course_id)


def create_chapter(db: Session, module_id: str, data: ChapterCreate) -> Chapter:
    # Mirrors ``create_module``: default order_index (0) appends at the tail
    # when the module already has chapters.
    order_index = data.order_index if data.order_index else _next_chapter_order(db, module_id)
    chapter = Chapter(
        id=str(uuid.uuid4()),
        module_id=module_id,
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
        fallback_locale=_course_source_locale_for_module(db, module_id),
    )
    db.commit()
    db.refresh(chapter)
    # Adding a quiz enlarges the denominator for everybody already enrolled.
    _resync_progress_for_chapter(db, chapter)
    return chapter


def update_chapter(db: Session, chapter: Chapter, data: ChapterUpdate) -> Chapter:
    patch = data.model_dump(exclude_unset=True)
    for field, value in patch.items():
        setattr(chapter, field, value)
    db.flush()
    if "title" in patch:
        dual_write_entity_content(
            db,
            entity_type="chapter",
            entity_id=str(chapter.id),
            texts={"title": patch["title"]},
            fallback_locale=_course_source_locale_for_module(db, chapter.module_id),
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
