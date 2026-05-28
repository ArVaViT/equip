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


def make_announcement_with_text(
    db: Session,
    *,
    title: str = "Announcement",
    content: str = "Body",
    course_id: str | None = None,
    created_by,
    announcement_id: uuid.UUID | None = None,
    locale: str = "en",
):
    """Phase 5e5: ``announcements.title`` + ``content`` columns dropped.
    Builds the row plus records both texts in cv at ``locale``.
    """
    from app.models.announcement import Announcement
    from app.services.content_versions.write import record_human_version

    ann = Announcement(
        id=announcement_id or uuid.uuid4(),
        course_id=course_id,
        created_by=created_by,
    )
    db.add(ann)
    db.flush()
    record_human_version(
        db, entity_type="announcement", entity_id=str(ann.id), field="title", locale=locale, text=title
    )
    if content:
        record_human_version(
            db, entity_type="announcement", entity_id=str(ann.id), field="content", locale=locale, text=content
        )
    return ann


def make_quiz_with_text(
    db: Session,
    *,
    chapter_id: str,
    title: str = "Quiz",
    description: str | None = None,
    quiz_type: str = "quiz",
    max_attempts: int | None = None,
    passing_score: int = 70,
    quiz_id: uuid.UUID | None = None,
    locale: str = "en",
):
    """Phase 5f: ``quizzes.title`` + ``description`` columns dropped."""
    from app.models.quiz import Quiz
    from app.services.content_versions.write import record_human_version

    quiz = Quiz(
        id=quiz_id or uuid.uuid4(),
        chapter_id=chapter_id,
        quiz_type=quiz_type,
        max_attempts=max_attempts,
        passing_score=passing_score,
    )
    db.add(quiz)
    db.flush()
    record_human_version(db, entity_type="quiz", entity_id=str(quiz.id), field="title", locale=locale, text=title)
    if description:
        record_human_version(
            db,
            entity_type="quiz",
            entity_id=str(quiz.id),
            field="description",
            locale=locale,
            text=description,
        )
    return quiz


def make_quiz_question_with_text(
    db: Session,
    *,
    quiz_id,
    question_text: str = "Q?",
    question_type: str = "multiple_choice",
    order_index: int = 0,
    points: int = 1,
    min_words: int | None = None,
    question_id: uuid.UUID | None = None,
    locale: str = "en",
):
    """Phase 5f: ``quiz_questions.question_text`` column dropped."""
    from app.models.quiz import QuizQuestion
    from app.services.content_versions.write import record_human_version

    question = QuizQuestion(
        id=question_id or uuid.uuid4(),
        quiz_id=quiz_id,
        question_type=question_type,
        order_index=order_index,
        points=points,
        min_words=min_words,
    )
    db.add(question)
    db.flush()
    record_human_version(
        db,
        entity_type="quiz_question",
        entity_id=str(question.id),
        field="question_text",
        locale=locale,
        text=question_text,
    )
    return question


def make_quiz_option_with_text(
    db: Session,
    *,
    question_id,
    option_text: str = "A",
    is_correct: bool = False,
    order_index: int = 0,
    option_id: uuid.UUID | None = None,
    locale: str = "en",
):
    """Phase 5f: ``quiz_options.option_text`` column dropped."""
    from app.models.quiz import QuizOption
    from app.services.content_versions.write import record_human_version

    option = QuizOption(
        id=option_id or uuid.uuid4(),
        question_id=question_id,
        is_correct=is_correct,
        order_index=order_index,
    )
    db.add(option)
    db.flush()
    record_human_version(
        db,
        entity_type="quiz_option",
        entity_id=str(option.id),
        field="option_text",
        locale=locale,
        text=option_text,
    )
    return option


def make_course_with_text(
    db: Session,
    *,
    course_id: str | None = None,
    title: str = "Course",
    description: str | None = None,
    image_url: str | None = None,
    status: str = "draft",
    source_locale: str = "en",
    created_by=None,
    access_mode: str = "public",
    enrollment_start=None,
    enrollment_end=None,
    quiz_weight: int | None = None,
    assignment_weight: int | None = None,
    participation_weight: int | None = None,
    locale: str | None = None,
):
    """Phase 5g: ``courses.title`` + ``courses.description`` columns dropped."""
    from app.models.course import Course
    from app.services.content_versions.write import record_human_version

    extra: dict = {}
    if quiz_weight is not None:
        extra["quiz_weight"] = quiz_weight
    if assignment_weight is not None:
        extra["assignment_weight"] = assignment_weight
    if participation_weight is not None:
        extra["participation_weight"] = participation_weight

    course = Course(
        id=course_id or str(uuid.uuid4()),
        image_url=image_url,
        status=status,
        source_locale=source_locale,
        created_by=created_by,
        access_mode=access_mode,
        enrollment_start=enrollment_start,
        enrollment_end=enrollment_end,
        **extra,
    )
    db.add(course)
    db.flush()
    record_human_version(
        db,
        entity_type="course",
        entity_id=course.id,
        field="title",
        locale=locale or source_locale,
        text=title,
    )
    if description:
        record_human_version(
            db,
            entity_type="course",
            entity_id=course.id,
            field="description",
            locale=locale or source_locale,
            text=description,
        )
    # Hydrate runtime attrs so tests reading course.title work immediately.
    course.title = title  # type: ignore[assignment]
    course.description = description  # type: ignore[assignment]
    return course


def make_module_with_text(
    db: Session,
    *,
    module_id: str | None = None,
    course_id: str,
    title: str = "Module",
    description: str | None = None,
    order_index: int = 0,
    due_date=None,
    locale: str = "en",
):
    """Phase 5g: ``modules.title`` + ``modules.description`` columns dropped."""
    from app.models.course import Module
    from app.services.content_versions.write import record_human_version

    module = Module(
        id=module_id or str(uuid.uuid4()),
        course_id=course_id,
        order_index=order_index,
        due_date=due_date,
    )
    db.add(module)
    db.flush()
    record_human_version(
        db,
        entity_type="module",
        entity_id=str(module.id),
        field="title",
        locale=locale,
        text=title,
    )
    if description:
        record_human_version(
            db,
            entity_type="module",
            entity_id=str(module.id),
            field="description",
            locale=locale,
            text=description,
        )
    # Hydrate runtime attrs so tests reading module.title work immediately.
    module.title = title  # type: ignore[assignment]
    module.description = description  # type: ignore[assignment]
    return module


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
