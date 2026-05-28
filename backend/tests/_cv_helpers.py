"""Test helpers for entities whose text columns were moved to ``content_versions``.

Phase 5e dropped source columns on several entities (cohort.name, chapter_block.content,
assignment.title + description, …). Tests that previously did
``Assignment(title=..., description=...)`` need to create the structural row and
then record the text in cv. These helpers keep that one-step.

Default locale is ``"en"``; the read path's three-tier fallback (display → source →
any-locale) means tests don't have to track the parent course's source_locale.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.assignment import Assignment as AssignmentModel
    from app.models.chapter_block import ChapterBlock as ChapterBlockModel


def make_assignment_with_text(
    db: Session,
    *,
    chapter_id: str,
    title: str = "Assignment",
    description: str | None = None,
    max_score: int = 100,
    due_date=None,
    assignment_id: uuid.UUID | None = None,
    locale: str = "en",
) -> AssignmentModel:
    """Phase 5e3: ``assignments.title`` + ``description`` columns dropped.
    Builds the row plus records both texts in cv at ``locale``.
    """
    from app.models.assignment import Assignment
    from app.services.content_versions.write import record_human_version

    assignment = Assignment(
        id=assignment_id or uuid.uuid4(),
        chapter_id=chapter_id,
        max_score=max_score,
        due_date=due_date,
    )
    db.add(assignment)
    db.flush()
    record_human_version(
        db,
        entity_type="assignment",
        entity_id=str(assignment.id),
        field="title",
        locale=locale,
        text=title,
    )
    if description is not None:
        record_human_version(
            db,
            entity_type="assignment",
            entity_id=str(assignment.id),
            field="description",
            locale=locale,
            text=description,
        )
    return assignment


def make_course_event_with_text(
    db: Session,
    *,
    course_id: str,
    title: str = "Event",
    description: str | None = None,
    event_type: str = "other",
    event_date=None,
    created_by,
    event_id: uuid.UUID | None = None,
    locale: str = "en",
):
    """Phase 5e4: ``course_events.title`` + ``description`` columns dropped.
    Builds the row plus records both texts in cv at ``locale``.
    """
    from datetime import UTC, datetime

    from app.models.course_event import CourseEvent
    from app.services.content_versions.write import record_human_version

    event = CourseEvent(
        id=event_id or uuid.uuid4(),
        course_id=course_id,
        event_type=event_type,
        event_date=event_date or datetime.now(UTC),
        created_by=created_by,
    )
    db.add(event)
    db.flush()
    record_human_version(
        db, entity_type="course_event", entity_id=str(event.id), field="title", locale=locale, text=title
    )
    # Empty string ≡ missing for cv purposes — matches the create route
    # which would store the value but the reconcile path skips blanks
    # so we keep the parity here.
    if description:
        record_human_version(
            db,
            entity_type="course_event",
            entity_id=str(event.id),
            field="description",
            locale=locale,
            text=description,
        )
    return event


def make_chapter_block_with_content(
    db: Session,
    *,
    chapter_id: str,
    block_type: str = "text",
    order_index: int = 0,
    content: str | None = None,
    block_id: uuid.UUID | None = None,
    locale: str = "en",
) -> ChapterBlockModel:
    """Phase 5e2: ``chapter_blocks.content`` column dropped. Builds the
    row plus records ``content`` in cv at ``locale`` (skipped if None).
    """
    from app.models.chapter_block import ChapterBlock
    from app.services.content_versions.write import record_human_version

    block = ChapterBlock(
        id=block_id or uuid.uuid4(),
        chapter_id=chapter_id,
        block_type=block_type,
        order_index=order_index,
    )
    db.add(block)
    db.flush()
    if content is not None:
        record_human_version(
            db,
            entity_type="chapter_block",
            entity_id=str(block.id),
            field="content",
            locale=locale,
            text=content,
        )
    return block
