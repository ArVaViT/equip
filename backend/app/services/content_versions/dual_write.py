"""Shared per-field write helper used by every translatable entity.

Reads each field's text from a caller-supplied dict, detects the
language (or falls back to a caller-supplied locale when the detector
has no signal), and records a human ``content_versions`` row per field.

Centralising it here keeps every call site to a 4-line invocation and
funnels future detection / fallback edits through one function.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.content_version import ContentVersion
from app.services.content_versions.write import record_human_version
from app.services.language_detection import detect_locale

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def dual_write_entity_content(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    texts: dict[str, str | None],
    fallback_locale: str | None,
    authored_by: str | uuid.UUID | None = None,
    only_fields: set[str] | None = None,
) -> None:
    """Record a human-authored ``content_versions`` row per field in ``texts``.

    Per-field detection: each field's locale is decided from its own
    text. Two fields on the same entity can land in different locales
    (an EN title and a RU description are normal). Detection falls back
    to ``fallback_locale`` when the field text is too short to classify
    or has no language signal — when there's no fallback either, the
    field is silently skipped (it will retry on the next save with more
    context).

    ``only_fields`` filters to the fields the caller actually wrote
    (used on UPDATE so a description-only PATCH doesn't supersede the
    title row). ``None`` means every field in ``texts`` is written.

    ``authored_by`` is stored on the row when known.
    """
    target = {f: t for f, t in texts.items() if only_fields is None or f in only_fields}
    if not target:
        return

    author_uuid = _coerce_uuid(authored_by)

    # An edit to a course students are reading right now does not go
    # live on its own — it waits in the staging table for its
    # translations, so all four languages change in one step. Every
    # other case (a draft, a course still on its way out, an entity
    # with no course at all) writes straight through as before.
    #
    # Decided once per save rather than per field: one indexed lookup
    # for the course, not one per field of the entity.
    from app.models.course import CourseStatus
    from app.services.staged_edits import course_of_entity, stage_human_edit

    course = course_of_entity(db, entity_type, entity_id)
    stage_edits = course is not None and course.status == CourseStatus.PUBLISHED
    # The course's declared language: an edit written in another one
    # replaces the field's source rather than sitting beside it as a
    # translation (``record_human_version``). A staged edit does the same
    # when it is released (``staged_edits.promote``).
    course_locale = course.source_locale if course is not None else None

    for field, raw in target.items():
        if not raw or not str(raw).strip():
            continue
        text_str = str(raw)
        locale = (
            detect_locale(text_str) or _locale_of_existing_text(db, entity_type, entity_id, field) or fallback_locale
        )
        if locale is None:
            continue
        if stage_edits and course is not None:
            stage_human_edit(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                course_id=str(course.id),
                field=field,
                locale=locale,
                text=text_str,
                authored_by=author_uuid,
            )
            continue
        record_human_version(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            locale=locale,
            text=text_str,
            authored_by=author_uuid,
            course_locale=course_locale,
        )


def _locale_of_existing_text(db: Session, entity_type: str, entity_id: str, field: str) -> str | None:
    """The locale this field is already written in, if a person wrote it.

    Editing a field is editing a language version of it. When the
    detector has no signal — a short heading, a proper noun, anything
    ambiguous between two languages of one script — the honest answer is
    "the same language as before", not "the language of the course".

    Without this, a teacher rewording an English heading in a Russian
    course would file the new text as Russian, leaving the previous
    English text active and served: the edit would appear to have done
    nothing. That could not happen while the platform served one
    language per script; it can now.
    """
    # The newest: a field can hold a person's text in two locales (a hand
    # translation, or an edit filed in another language before such an
    # edit replaced the source), and ``.scalar()`` raised on two rows —
    # a 500 on the next save of a heading too short to classify.
    return (
        db.query(ContentVersion.locale)
        .filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == entity_id,
            ContentVersion.field == field,
            ContentVersion.origin == "human",
            ContentVersion.superseded_by.is_(None),
        )
        .order_by(ContentVersion.created_at.desc())
        .limit(1)
        .scalar()
    )


def _coerce_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))
