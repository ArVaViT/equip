"""Test helpers for entities whose text columns were moved to ``content_versions``.

Phase 5e-g dropped source columns on ten entities (cohort.name,
chapter_block.content, assignment.title + description, course_event.title
+ description, announcement.title + content, quiz.title + description,
quiz_question.question_text, quiz_option.option_text, course.title +
description, module.title + description). Tests that previously did
``X(title=..., description=...)`` need to create the structural row and
then record the text in cv. These helpers do both.

Default locale is ``"en"``; the read path's three-tier fallback
(display → source → any-locale) means most tests don't have to track
the parent course's source_locale.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.announcement import Announcement
from app.models.assignment import Assignment
from app.models.chapter_block import ChapterBlock
from app.models.course import Course, Module
from app.models.course_event import CourseEvent
from app.models.quiz import Quiz, QuizOption, QuizQuestion
from app.services.content_versions.write import record_human_version

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _seed_text_row(
    db: Session,
    *,
    entity_type: str,
    entity_id,
    field: str,
    locale: str,
    text: str | None,
) -> None:
    """Record an active+ok ``human``-origin cv row when text is non-empty.

    Centralising the ``if text`` guard lets the caller pass ``None`` or
    an empty string for optional fields without sprinkling conditionals
    around each helper.
    """
    if text:
        record_human_version(
            db,
            entity_type=entity_type,
            entity_id=str(entity_id),
            field=field,
            locale=locale,
            text=text,
        )


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
) -> Assignment:
    assignment = Assignment(
        id=assignment_id or uuid.uuid4(),
        chapter_id=chapter_id,
        max_score=max_score,
        due_date=due_date,
    )
    db.add(assignment)
    db.flush()
    _seed_text_row(db, entity_type="assignment", entity_id=assignment.id, field="title", locale=locale, text=title)
    _seed_text_row(
        db, entity_type="assignment", entity_id=assignment.id, field="description", locale=locale, text=description
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
) -> CourseEvent:
    event = CourseEvent(
        id=event_id or uuid.uuid4(),
        course_id=course_id,
        event_type=event_type,
        event_date=event_date or datetime.now(UTC),
        created_by=created_by,
    )
    db.add(event)
    db.flush()
    _seed_text_row(db, entity_type="course_event", entity_id=event.id, field="title", locale=locale, text=title)
    _seed_text_row(
        db, entity_type="course_event", entity_id=event.id, field="description", locale=locale, text=description
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
) -> Announcement:
    ann = Announcement(
        id=announcement_id or uuid.uuid4(),
        course_id=course_id,
        created_by=created_by,
    )
    db.add(ann)
    db.flush()
    _seed_text_row(db, entity_type="announcement", entity_id=ann.id, field="title", locale=locale, text=title)
    _seed_text_row(db, entity_type="announcement", entity_id=ann.id, field="content", locale=locale, text=content)
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
) -> Quiz:
    quiz = Quiz(
        id=quiz_id or uuid.uuid4(),
        chapter_id=chapter_id,
        quiz_type=quiz_type,
        max_attempts=max_attempts,
        passing_score=passing_score,
    )
    db.add(quiz)
    db.flush()
    _seed_text_row(db, entity_type="quiz", entity_id=quiz.id, field="title", locale=locale, text=title)
    _seed_text_row(db, entity_type="quiz", entity_id=quiz.id, field="description", locale=locale, text=description)
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
) -> QuizQuestion:
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
    _seed_text_row(
        db, entity_type="quiz_question", entity_id=question.id, field="question_text", locale=locale, text=question_text
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
) -> QuizOption:
    option = QuizOption(
        id=option_id or uuid.uuid4(),
        question_id=question_id,
        is_correct=is_correct,
        order_index=order_index,
    )
    db.add(option)
    db.flush()
    _seed_text_row(
        db, entity_type="quiz_option", entity_id=option.id, field="option_text", locale=locale, text=option_text
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
) -> Course:
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
    cv_locale = locale or source_locale
    _seed_text_row(db, entity_type="course", entity_id=course.id, field="title", locale=cv_locale, text=title)
    _seed_text_row(
        db, entity_type="course", entity_id=course.id, field="description", locale=cv_locale, text=description
    )
    # Hydrate runtime attrs so tests reading course.title work immediately.
    course.title = title
    course.description = description
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
) -> Module:
    module = Module(
        id=module_id or str(uuid.uuid4()),
        course_id=course_id,
        order_index=order_index,
        due_date=due_date,
    )
    db.add(module)
    db.flush()
    _seed_text_row(db, entity_type="module", entity_id=module.id, field="title", locale=locale, text=title)
    _seed_text_row(db, entity_type="module", entity_id=module.id, field="description", locale=locale, text=description)
    # Hydrate runtime attrs so tests reading module.title work immediately.
    module.title = title
    module.description = description
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
) -> ChapterBlock:
    block = ChapterBlock(
        id=block_id or uuid.uuid4(),
        chapter_id=chapter_id,
        block_type=block_type,
        order_index=order_index,
    )
    db.add(block)
    db.flush()
    _seed_text_row(db, entity_type="chapter_block", entity_id=block.id, field="content", locale=locale, text=content)
    return block
