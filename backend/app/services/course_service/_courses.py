"""Course-level write operations (create, update, soft/hard delete, restore)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.models.certificate import Certificate
from app.models.course import Chapter, Course, Module
from app.services.content_versions import (
    delete_entity_cv_rows,
    dual_write_entity_content,
    fetch_cv_entity_texts_with_fallback,
)
from app.services.language_detection import detect_locale
from app.services.translation.resolve_for_display import populate_spine_texts

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from app.schemas.course import CourseCreate, CourseUpdate


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
    organization_id: UUID,
    source_locale: str | None = None,
) -> Course:
    """Create a new course owned by ``user_id``, inside ``organization_id``.

    The organization is a required keyword argument rather than something
    read from the author here: a course belongs to an organization, the
    route knows which one the caller is in, and a function that guesses
    would be the only place in the tree entitled to be wrong about it.

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
    # Title + description columns dropped. Structural row only;
    # texts go through dual_write via the explicit ``texts={...}`` dict.
    course = Course(
        id=str(uuid.uuid4()),
        image_url=data.image_url,
        created_by=user_id,
        organization_id=organization_id,
    )
    if resolved_locale is not None:
        course.source_locale = resolved_locale
    db.add(course)
    db.flush()
    dual_write_entity_content(
        db,
        entity_type="course",
        entity_id=str(course.id),
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
    """Patch course fields. Title + description are split off the patch
    and routed through cv via dual_write; structural fields setattr as
    before. Re-detects source_locale when title/description changed so a
    teacher who rewrites Russian text in an English course flips the
    course's authoring direction automatically.
    """
    patch = data.model_dump(exclude_unset=True)
    text_patch: dict[str, str | None] = {}
    if "title" in patch:
        text_patch["title"] = patch.pop("title")
    if "description" in patch:
        text_patch["description"] = patch.pop("description")
    for field, value in patch.items():
        setattr(course, field, value)
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
            fallback_locale=course.source_locale,
            authored_by=course.created_by,
            only_fields=set(text_patch.keys()),
            texts=text_patch,
        )
    db.commit()
    db.refresh(course)
    populate_spine_texts(db, [course])
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
    # Dropping the title column removed the ``snapshot_certificate_course_title`` Postgres
    # trigger along with ``courses.title``. Stamp the title onto every
    # certificate that still points at this course before the FK
    # ``ON DELETE SET NULL`` nulls ``course_id`` and the title becomes
    # unrecoverable. Mirrors the trigger's `WHERE archived_course_title
    # IS NULL` clause so re-deletes don't overwrite an earlier snapshot.
    #
    # Read the title from content_versions instead of the
    # ``course.title`` runtime attribute. Callers that didn't go through
    # ``populate_spine_texts`` (admin permanent-delete from a list view)
    # otherwise stamp ``None`` and the certificate loses its title for
    # good once the FK nulls.
    cv_texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="course",
        entity_ids=[course.id],
        fields=["title"],
        display_locale=course.source_locale or "en",
        source_locale=course.source_locale or "en",
        prefer_human=True,
    )
    archived_title = cv_texts.get((course.id, "title")) or ""
    db.query(Certificate).filter(
        Certificate.course_id == course.id,
        Certificate.archived_course_title.is_(None),
    ).update(
        {Certificate.archived_course_title: archived_title},
        synchronize_session=False,
    )
    # content_versions has no FK back to entity tables
    # (polymorphic entity_id), so the entity-table CASCADE that takes
    # out modules / chapters / blocks / quizzes / assignments /
    # announcements / events when the course row goes will NOT touch
    # cv. Walk the tree and drop cv rows for every translatable entity
    # before the entity row is deleted. Bulk-DELETE per entity_type so
    # the sweep stays O(few queries) regardless of course size.
    from app.models.announcement import Announcement
    from app.models.assignment import Assignment
    from app.models.chapter_block import ChapterBlock
    from app.models.content_version import ContentVersion
    from app.models.course_event import CourseEvent
    from app.models.quiz import Quiz, QuizOption, QuizQuestion

    # Ids are carried in their own type and only turned into text at the
    # ``content_versions`` boundary, where ``entity_id`` is a text column.
    # Stringifying earlier and then querying a uuid column with the
    # result is what this walk used to do, and SQLAlchemy answers that
    # with ``'str' object has no attribute 'hex'`` — a 503 on the
    # delete, and, where a driver was more forgiving, a lookup that
    # quietly matched nothing and left the translations behind.
    # Read the tree from the database rather than from ``course.modules``.
    #
    # Loading a course eager-loads its tree through ``_COURSE_TREE``,
    # which filters out soft-deleted modules and chapters — right for
    # every screen, and exactly wrong here. A course reaches this
    # function *through the bin*, and ``delete_course`` tombstones every
    # module and chapter on the way in. So the collection this walk used
    # to read was empty for every course that got here the ordinary way,
    # and everything hanging off a chapter — its blocks, quizzes,
    # assignments and their translations — was skipped. One deleted
    # course left three orphaned rows behind; production had 787.
    module_keys = [mid for (mid,) in db.query(Module.id).filter(Module.course_id == course.id)]
    chapter_keys = (
        [cid for (cid,) in db.query(Chapter.id).filter(Chapter.module_id.in_(module_keys))] if module_keys else []
    )

    blocks: list[Any] = []
    quizzes: list[Any] = []
    questions: list[Any] = []
    options: list[Any] = []
    assignments: list[Any] = []
    if chapter_keys:
        blocks = [bid for (bid,) in db.query(ChapterBlock.id).filter(ChapterBlock.chapter_id.in_(chapter_keys))]
        quizzes = [qid for (qid,) in db.query(Quiz.id).filter(Quiz.chapter_id.in_(chapter_keys))]
        assignments = [aid for (aid,) in db.query(Assignment.id).filter(Assignment.chapter_id.in_(chapter_keys))]
        if quizzes:
            questions = [qid for (qid,) in db.query(QuizQuestion.id).filter(QuizQuestion.quiz_id.in_(quizzes))]
            if questions:
                options = [oid for (oid,) in db.query(QuizOption.id).filter(QuizOption.question_id.in_(questions))]

    announcements = [aid for (aid,) in db.query(Announcement.id).filter(Announcement.course_id == course.id)]
    events = [eid for (eid,) in db.query(CourseEvent.id).filter(CourseEvent.course_id == course.id)]

    chapter_ids = [str(cid) for cid in chapter_keys]
    module_ids = [str(mid) for mid in module_keys]
    block_ids = [str(bid) for bid in blocks]
    quiz_ids = [str(qid) for qid in quizzes]
    question_ids = [str(qid) for qid in questions]
    option_ids = [str(oid) for oid in options]
    assignment_ids = [str(aid) for aid in assignments]
    announcement_ids = [str(aid) for aid in announcements]
    event_ids = [str(eid) for eid in events]

    def _sweep(entity_type: str, ids: list[str]) -> None:
        if not ids:
            return
        db.query(ContentVersion).filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id.in_(ids),
        ).delete(synchronize_session=False)

    _sweep("course", [course.id])
    _sweep("module", module_ids)
    _sweep("chapter", chapter_ids)
    _sweep("chapter_block", block_ids)
    _sweep("quiz", quiz_ids)
    _sweep("quiz_question", question_ids)
    _sweep("quiz_option", option_ids)
    _sweep("assignment", assignment_ids)
    _sweep("announcement", announcement_ids)
    _sweep("course_event", event_ids)
    # Silence the unused-import warning when the explicit helper isn't
    # invoked above — the bulk _sweep path is the actual hot path.
    _ = delete_entity_cv_rows

    db.delete(course)
    db.commit()
