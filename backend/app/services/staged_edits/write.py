"""Recording an edit without publishing it.

The decision this module makes on every save is small and total: does
this text go live now, or does it wait for its translations?

It waits only when there is somebody to protect — a course whose status
is ``published``, which is exactly the case where students are reading
the old text in four languages right now. A draft has no readers; a
course still in ``publishing`` has none either (every reader treats
that state as unpublished), and holding its edits back would stall the
very pipeline that is trying to complete it.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from app.models.course import Course, CourseStatus
from app.models.staged_content_version import StagedContentVersion
from app.services.translation.stores import _upsert_staged

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def course_of_entity(db: Session, entity_type: str, entity_id: str) -> Course | None:
    """The course this entity belongs to, or ``None``.

    Goes through the translation registry so there is one answer to
    "what course is this?" in the codebase rather than two that drift.
    Entities with no course — a platform-wide Daily Challenge question —
    answer ``None``, and their edits are never staged: there is no
    published course whose readers could be caught mid-change.
    """
    from app.services.translation.registry import ENTITY_MODEL, REGISTRY

    reg = REGISTRY.get(entity_type)  # type: ignore[call-overload]
    model = ENTITY_MODEL.get(entity_type)  # type: ignore[call-overload]
    if reg is None or model is None:
        return None
    pk = _coerce_primary_key(model, entity_id)
    if pk is None:
        return None
    entity = db.get(model, pk)
    if entity is None:
        return None
    course = reg.resolve_course(db, entity)
    return course if isinstance(course, Course) else None


def _coerce_primary_key(model: type, entity_id: str) -> object | None:
    """Turn the string key used across the translation layer back into
    whatever type this table's primary key actually is.

    ``content_versions.entity_id`` is text for every entity, because the
    key is polymorphic. The tables themselves are not so uniform:
    courses, modules and chapters are keyed by ``varchar`` slugs, while
    blocks, quizzes and questions are ``uuid``. Handing a string to
    ``Session.get`` on a uuid column raises inside SQLAlchemy's bind
    processor rather than returning nothing, so the conversion has to
    happen here.

    ``None`` means the id cannot belong to this table — treated as "no
    course", which routes the write down the ordinary path.
    """
    from sqlalchemy import inspect as sa_inspect

    try:
        pk_column: Any = sa_inspect(model).primary_key[0]
        python_type = pk_column.type.python_type
    except (AttributeError, NotImplementedError, IndexError):
        return entity_id
    if python_type is uuid.UUID:
        try:
            return uuid.UUID(str(entity_id))
        except (ValueError, AttributeError, TypeError):
            return None
    return str(entity_id)


def edit_should_be_staged(db: Session, entity_type: str, entity_id: str) -> bool:
    """True when this entity's course is live and being read.

    ``publishing`` deliberately returns False. That state means the
    course has been sent out and is not whole yet; it is invisible to
    students, and its content is what the pipeline is racing to
    complete. Staging edits there would stage the course's own first
    draft against itself.
    """
    course = course_of_entity(db, entity_type, entity_id)
    return course is not None and course.status == CourseStatus.PUBLISHED


def stage_human_edit(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    course_id: str,
    field: str,
    locale: str,
    text: str,
    authored_by: uuid.UUID | None = None,
) -> StagedContentVersion | None:
    """Hold a teacher's new text until its translations catch up.

    Returns the staged row, or ``None`` when nothing needed staging.

    Two cases resolve to ``None``, and both matter:

    * **The text equals what is already live.** A save that changed
      nothing — a teacher re-saving a form, an unrelated field being
      PATCHed — must not put the field into an in-flight state it then
      has to be promoted out of. Any leftover staging for the field is
      cleared: the edit has been reverted, so there is nothing waiting.
    * **The text equals what is already staged.** Same edit, saved
      twice. Keep the row and its translations exactly as they are;
      re-writing it would reset ``source_hash`` and throw away
      translations that are already correct for this text.

    Otherwise the row is written and every staged translation of the
    field is dropped — they translate the previous wording, and a
    translation of text nobody is publishing is not evidence of
    anything. The pipeline will make new ones.
    """
    existing = (
        db.query(StagedContentVersion)
        .filter(
            StagedContentVersion.entity_type == entity_type,
            StagedContentVersion.entity_id == entity_id,
            StagedContentVersion.field == field,
            StagedContentVersion.locale == locale,
            StagedContentVersion.origin == "human",
        )
        .one_or_none()
    )
    if existing is not None and existing.text == text:
        return existing

    if _matches_live_text(db, entity_type=entity_type, entity_id=entity_id, field=field, locale=locale, text=text):
        # Back to where it started. Whatever was in flight is moot.
        cleared = clear_staged_field(db, entity_type=entity_type, entity_id=entity_id, field=field)
        if cleared:
            logger.info(
                "staged_edits: edit reverted, dropped %d staged rows for %s:%s field=%s",
                cleared,
                entity_type,
                entity_id,
                field,
            )
        return None

    # The source changed, so every translation staged against the old
    # source is stale. Drop them rather than leave rows whose
    # ``source_hash`` no longer matches: promotion would ignore them
    # anyway, and keeping them makes "what is waiting?" harder to read.
    dropped = (
        db.query(StagedContentVersion)
        .filter(
            StagedContentVersion.entity_type == entity_type,
            StagedContentVersion.entity_id == entity_id,
            StagedContentVersion.field == field,
            StagedContentVersion.origin == "mt",
        )
        .delete(synchronize_session=False)
    )

    row = _upsert_staged(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        course_id=course_id,
        field=field,
        locale=locale,
        text=text,
        origin="human",
        status="ok",
        review_reason=None,
        source_locale=None,
        source_hash=None,
        attempts=0,
        authored_by=authored_by,
    )
    logger.info(
        "staged_edits: held edit to %s:%s field=%s locale=%s (dropped %d stale translations)",
        entity_type,
        entity_id,
        field,
        locale,
        dropped,
    )
    return row


def _matches_live_text(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    field: str,
    locale: str,
    text: str,
) -> bool:
    """Is this exactly what readers are already being served?"""
    from app.models.content_version import ContentVersion

    live = (
        db.query(ContentVersion.text)
        .filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == entity_id,
            ContentVersion.field == field,
            ContentVersion.locale == locale,
            ContentVersion.superseded_by.is_(None),
        )
        .scalar()
    )
    return live is not None and live == text


def clear_staged_field(db: Session, *, entity_type: str, entity_id: str, field: str) -> int:
    """Drop the whole in-flight edit for one field. Returns rows removed."""
    return (
        db.query(StagedContentVersion)
        .filter(
            StagedContentVersion.entity_type == entity_type,
            StagedContentVersion.entity_id == entity_id,
            StagedContentVersion.field == field,
        )
        .delete(synchronize_session=False)
    )


def clear_staged_entity(db: Session, *, entity_type: str, entity_id: str | uuid.UUID) -> int:
    """Drop every in-flight edit for one entity.

    Called wherever ``delete_entity_cv_rows`` is called: the staging
    table has no FK to the entity tables either (the key is
    polymorphic), so a hard-deleted block would otherwise leave its
    unreleased edit behind forever — invisible, unpromotable, and
    counted by every "what is waiting?" query.
    """
    return (
        db.query(StagedContentVersion)
        .filter(
            StagedContentVersion.entity_type == entity_type,
            StagedContentVersion.entity_id == str(entity_id),
        )
        .delete(synchronize_session=False)
    )


__all__ = [
    "clear_staged_entity",
    "clear_staged_field",
    "course_of_entity",
    "edit_should_be_staged",
    "stage_human_edit",
]
