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


def _next_chapter_order(db: Session, module_id: str) -> int:
    """Return the tail ``order_index`` for a new chapter on this module."""
    current_max = (
        db.query(func.max(Chapter.order_index))
        .filter(Chapter.module_id == module_id, Chapter.deleted_at.is_(None))
        .scalar()
    )
    return 0 if current_max is None else current_max + 1


def _course_id_for_module(db: Session, module_id: str) -> str | None:
    """The course a module belongs to — the second parent a new chapter carries.

    ``None`` only when the module does not exist, and then the NOT NULL on
    ``chapters.course_id`` refuses the row exactly as the module FK always
    did; the route checks the module first, so it never gets that far.
    """
    return db.query(Module.course_id).filter(Module.id == module_id).scalar()


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


def create_chapter(db: Session, module_id: str, data: ChapterCreate) -> Chapter:
    # Mirrors ``create_module``: default order_index (0) appends at the tail
    # when the module already has chapters.
    order_index = data.order_index if data.order_index else _next_chapter_order(db, module_id)
    chapter = Chapter(
        id=str(uuid.uuid4()),
        module_id=module_id,
        course_id=_course_id_for_module(db, module_id),
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
    for field, value in patch.items():
        setattr(chapter, field, value)
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
