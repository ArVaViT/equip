"""Course-level write operations (create, update, soft/hard delete, restore)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.course import Chapter, Course, Module
from app.services.content_versions import record_human_version
from app.services.language_detection import detect_locale

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from app.schemas.course import CourseCreate, CourseUpdate


_TRANSLATABLE_COURSE_FIELDS = ("title", "description")


def _dual_write_course_content(
    db: Session,
    course: Course,
    *,
    authored_by: str | UUID | None,
    course_fallback: str | None,
    only_fields: set[str] | None = None,
) -> None:
    """Write a ``content_versions`` row for every translatable field
    on ``course`` that the caller wrote.

    Each field's locale is detected from its own text (so a course
    with an English title and Russian description gets two rows with
    different ``locale`` values). Detection falls back to the course
    source locale when the field's text is too short or has no
    language signal.

    ``only_fields`` is the set of fields the caller actually wrote;
    ``None`` means "every translatable field" (used on create).
    Filtering is important on PATCH so a description-only update
    doesn't supersede the title row.

    ``authored_by`` is the user id the route layer attributes the
    write to (course owner on create, owner on update). Stored on
    the row so the future preacher-style audit UI can show who
    wrote what.
    """
    fields: tuple[str, ...]
    if only_fields is None:
        fields = _TRANSLATABLE_COURSE_FIELDS
    else:
        fields = tuple(f for f in _TRANSLATABLE_COURSE_FIELDS if f in only_fields)
    author_uuid: UUID | None = None
    if authored_by is not None:
        author_uuid = authored_by if isinstance(authored_by, uuid.UUID) else uuid.UUID(str(authored_by))
    for field in fields:
        text = getattr(course, field, None)
        if not text or not str(text).strip():
            continue
        detected = detect_locale(str(text))
        locale = detected or course_fallback
        if locale is None:
            # No signal AND no course-level fallback — skip. Dual-write
            # without a locale would be nonsensical and the field will
            # come back through this path the next time the entity is
            # saved with enough context.
            continue
        record_human_version(
            db,
            entity_type="course",
            entity_id=str(course.id),
            field=field,
            locale=locale,
            text=str(text),
            authored_by=author_uuid,
        )


def _resolve_source_locale(
    *,
    title: str | None,
    description: str | None,
    fallback: str | None,
) -> str | None:
    """Detect the actual content language from the title + description,
    falling back to the teacher's UI locale only when there's no signal.

    Previously the API used ``teacher.preferred_locale`` unconditionally,
    which silently miscategorised every course a teacher authored in a
    language different from their UI (Vadym-with-EN-UI writing a
    Russian course → ``source_locale='en'`` → translation pipeline
    refused to translate ``en→ru`` → Russian students saw Russian text
    labelled as English while English students saw it un-translated).

    The detector returns ``None`` for empty / too-short / non-letter
    input; those callers get the original fallback behaviour so no
    existing fixture or PATCH-without-title flow regresses.
    """
    combined = " ".join(part for part in (title, description) if part)
    detected = detect_locale(combined) if combined else None
    if detected is not None:
        return detected
    return fallback


def create_course(
    db: Session,
    data: CourseCreate,
    user_id: str | UUID,
    *,
    source_locale: str | None = None,
) -> Course:
    """Create a new course owned by ``user_id``.

    ``source_locale`` is the caller-supplied UI-locale fallback (the
    route layer passes ``teacher.preferred_locale``); this function
    runs the language detector on the actual title + description first
    and only uses the fallback when detection has no signal.
    """
    resolved_locale = _resolve_source_locale(
        title=data.title,
        description=data.description,
        fallback=source_locale,
    )
    course = Course(
        id=str(uuid.uuid4()),
        title=data.title,
        description=data.description,
        image_url=data.image_url,
        created_by=user_id,
    )
    if resolved_locale is not None:
        course.source_locale = resolved_locale
    db.add(course)
    db.flush()
    _dual_write_course_content(db, course, authored_by=user_id, course_fallback=resolved_locale)
    db.commit()
    db.refresh(course)
    return course


def update_course(db: Session, course: Course, data: CourseUpdate) -> Course:
    patch = data.model_dump(exclude_unset=True)
    previous_source_locale = course.source_locale
    for field, value in patch.items():
        setattr(course, field, value)
    # Re-detect the source locale ONLY when the patch actually touched
    # title or description. A PATCH that just changes the cover image
    # or the weights must not rewrite ``source_locale`` — the existing
    # value is authoritative until the teacher rewrites the text.
    if "title" in patch or "description" in patch:
        detected = _resolve_source_locale(
            title=course.title,
            description=course.description,
            fallback=None,
        )
        if detected is not None:
            course.source_locale = detected
    db.flush()
    # Dual-write to content_versions only for fields the caller actually
    # touched — a PATCH that didn't include ``description`` mustn't
    # supersede the existing description row.
    _dual_write_course_content(
        db,
        course,
        authored_by=course.created_by,
        course_fallback=course.source_locale,
        only_fields={f for f in ("title", "description") if f in patch},
    )
    db.commit()
    db.refresh(course)
    # When the source locale flips, every existing ``content_translations``
    # row tied to entities under this course is now stale: it was
    # generated against the OLD source language, and the resolve path
    # would incorrectly prefer those rows over the new authoritative
    # base text. Purge them so the next translation pipeline run
    # (triggered downstream by the publish hook) repopulates the tree
    # in the new direction. Cheap when no rows exist; safe to run on
    # every locale flip.
    #
    # Imported inside the function to avoid a module-load cycle
    # (translation.course_pipeline already imports from app.models.course).
    if course.source_locale != previous_source_locale:
        from app.services.translation.course_pipeline import purge_course_translations

        purge_course_translations(db, course)
    return course


def delete_course(db: Session, course: Course) -> None:
    """Soft-delete: tombstone the course and cascade to modules/chapters.

    Uses bulk UPDATEs so a course with hundreds of chapters still completes in
    three round trips (course + modules + chapters) instead of one per row.
    Enrollments / progress / quiz attempts are intentionally left untouched
    so a restore is lossless.
    """
    now = datetime.now(UTC)
    course.deleted_at = now
    db.query(Module).filter(
        Module.course_id == course.id,
        Module.deleted_at.is_(None),
    ).update({Module.deleted_at: now}, synchronize_session=False)
    module_ids = select(Module.id).where(Module.course_id == course.id).scalar_subquery()
    db.query(Chapter).filter(
        Chapter.module_id.in_(module_ids),
        Chapter.deleted_at.is_(None),
    ).update({Chapter.deleted_at: now}, synchronize_session=False)
    db.commit()


def restore_course(db: Session, course: Course) -> Course:
    """Undelete a soft-deleted course tree via bulk UPDATEs.

    Symmetric to ``delete_course``: we only flip cascaded rows back to
    live, NOT rows that were independently soft-deleted before the
    course tombstone. ``delete_course`` stamps the cascade with a single
    ``now`` timestamp, so matching ``Module.deleted_at == course.deleted_at``
    (captured before we null it) restores exactly the cascade set —
    rows with an earlier ``deleted_at`` (independently deleted by a
    teacher before the course was trashed) stay deleted.

    Direct UPDATE statements rather than walking ``course.modules``
    because the eager loader in ``_COURSE_TREE`` filters out the very
    rows we need to flip.
    """
    tombstone = course.deleted_at
    course.deleted_at = None
    if tombstone is not None:
        db.query(Module).filter(
            Module.course_id == course.id,
            Module.deleted_at == tombstone,
        ).update({Module.deleted_at: None}, synchronize_session=False)
        module_ids = select(Module.id).where(Module.course_id == course.id).scalar_subquery()
        db.query(Chapter).filter(
            Chapter.module_id.in_(module_ids),
            Chapter.deleted_at == tombstone,
        ).update({Chapter.deleted_at: None}, synchronize_session=False)
    db.commit()
    db.refresh(course)
    return course


def permanently_delete_course(db: Session, course: Course) -> None:
    db.delete(course)
    db.commit()
