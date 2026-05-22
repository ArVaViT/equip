"""Course-level write operations (create, update, soft/hard delete, restore)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.course import Chapter, Course, Module

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from app.schemas.course import CourseCreate, CourseUpdate


def create_course(
    db: Session,
    data: CourseCreate,
    user_id: str | UUID,
    *,
    source_locale: str | None = None,
) -> Course:
    """Create a new course owned by ``user_id``.

    ``source_locale`` is the language the teacher is authoring in. The API
    layer derives it from the teacher's ``preferred_locale`` profile
    setting so the teacher never sees a "what language are you writing in?"
    prompt — the system already knows from their UI choice. Passing
    ``None`` (legacy callers, scripts) falls back to the column's DB
    default (``'ru'``) to keep migrations / fixtures working unchanged.
    """
    course = Course(
        id=str(uuid.uuid4()),
        title=data.title,
        description=data.description,
        image_url=data.image_url,
        created_by=user_id,
    )
    if source_locale is not None:
        course.source_locale = source_locale
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def update_course(db: Session, course: Course, data: CourseUpdate) -> Course:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(course, field, value)
    db.commit()
    db.refresh(course)
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
