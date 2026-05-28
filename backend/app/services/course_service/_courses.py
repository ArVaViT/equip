"""Course-level write operations (create, update, soft/hard delete, restore)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.course import Chapter, Course, Module
from app.services.content_versions import dual_write_entity_content
from app.services.language_detection import detect_locale

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from app.schemas.course import CourseCreate, CourseUpdate


_TRANSLATABLE_COURSE_FIELDS = ("title", "description")


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
    # Phase 5g: title + description columns dropped. Structural row only;
    # texts go through dual_write via the explicit ``texts={...}`` dict.
    course = Course(
        id=str(uuid.uuid4()),
        image_url=data.image_url,
        created_by=user_id,
    )
    if resolved_locale is not None:
        course.source_locale = resolved_locale
    db.add(course)
    db.flush()
    dual_write_entity_content(
        db,
        entity_type="course",
        entity_id=str(course.id),
        fields=_TRANSLATABLE_COURSE_FIELDS,
        fallback_locale=resolved_locale,
        authored_by=user_id,
        texts={"title": data.title, "description": data.description},
    )
    db.commit()
    db.refresh(course)
    # Hydrate runtime attrs so the caller's response serialization works.
    course.title = data.title
    course.description = data.description
    return course


def update_course(db: Session, course: Course, data: CourseUpdate) -> Course:
    patch = data.model_dump(exclude_unset=True)
    previous_source_locale = course.source_locale
    # Phase 5g: title + description live in cv. Pop them off the patch
    # so they don't try to setattr on the (now-text-less) ORM row.
    text_patch: dict[str, str | None] = {}
    if "title" in patch:
        text_patch["title"] = patch.pop("title")
    if "description" in patch:
        text_patch["description"] = patch.pop("description")
    for field, value in patch.items():
        setattr(course, field, value)
    # Re-detect the source locale ONLY when the patch actually touched
    # title or description.
    if text_patch:
        detected = _resolve_source_locale(
            title=text_patch.get("title"),
            description=text_patch.get("description"),
            fallback=None,
        )
        if detected is not None:
            course.source_locale = detected
    db.flush()
    if text_patch:
        dual_write_entity_content(
            db,
            entity_type="course",
            entity_id=str(course.id),
            fields=_TRANSLATABLE_COURSE_FIELDS,
            fallback_locale=course.source_locale,
            authored_by=course.created_by,
            only_fields=set(text_patch.keys()),
            texts=text_patch,
        )
    db.commit()
    db.refresh(course)
    # Hydrate runtime attrs from cv after the write so the caller's
    # response serialization sees the new texts.
    from app.services.translation.resolve_for_display import populate_spine_texts

    populate_spine_texts(db, [course])
    _ = previous_source_locale  # kept for future locale-flip telemetry
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
