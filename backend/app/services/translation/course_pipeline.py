"""Translate all teacher-authored text under a course (metadata + tree).

Invoked after publish and after edits while the course stays published. The
orchestrator short-circuits unchanged sources via ``source_hash``, so idle
hooks cost zero LLM calls.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session, selectinload

from app.models.announcement import Announcement
from app.models.assignment import Assignment
from app.models.chapter_block import ChapterBlock
from app.models.course import Course  # noqa: TC001
from app.models.course_event import CourseEvent
from app.models.quiz import Quiz, QuizQuestion
from app.schemas.locale import LOCALE_CODES, LocaleCode
from app.services.translation.orchestrator import (
    OrchestratorReport,
    TranslationFieldSpec,
    translate_course_metadata,
    translate_entity_fields,
)
from app.services.translation.protocol import TranslationProvider  # noqa: TC001
from app.services.translation.service import is_translation_enabled

logger = logging.getLogger(__name__)


def _course_source_locale(course: Course) -> LocaleCode:
    for code in LOCALE_CODES:
        if course.source_locale == code:
            return code
    return "ru"


def merge_orchestrator_reports(*parts: OrchestratorReport) -> OrchestratorReport:
    return OrchestratorReport(
        translated=sum(p.translated for p in parts),
        skipped=sum(p.skipped for p in parts),
        failed=sum(p.failed for p in parts),
    )


def _translate_quiz_tree(
    db: Session,
    quiz: Quiz,
    *,
    source_locale: LocaleCode,
    course_title: str,
    provider: TranslationProvider | None,
) -> OrchestratorReport:
    total = translate_entity_fields(
        db,
        entity_type="quiz",
        entity_id=str(quiz.id),
        source_locale=source_locale,
        fields=[
            TranslationFieldSpec(field="title", text=quiz.title, content_kind="title"),
            TranslationFieldSpec(field="description", text=quiz.description, content_kind="plain"),
        ],
        context=f"Quiz in course: {course_title}",
        provider=provider,
    )
    for q in quiz.questions:
        r = translate_entity_fields(
            db,
            entity_type="quiz_question",
            entity_id=str(q.id),
            source_locale=source_locale,
            fields=[
                TranslationFieldSpec(field="question_text", text=q.question_text, content_kind="quiz_question"),
            ],
            context=f"Quiz: {quiz.title}",
            provider=provider,
        )
        total = merge_orchestrator_reports(total, r)
        for opt in q.options:
            o = translate_entity_fields(
                db,
                entity_type="quiz_option",
                entity_id=str(opt.id),
                source_locale=source_locale,
                fields=[TranslationFieldSpec(field="option_text", text=opt.option_text, content_kind="quiz_option")],
                context="Answer option for a Bible-school quiz question.",
                provider=provider,
            )
            total = merge_orchestrator_reports(total, o)
    return total


def translate_course_content(
    db: Session,
    course: Course,
    *,
    provider: TranslationProvider | None = None,
) -> OrchestratorReport:
    """Translate metadata, modules, chapters, blocks, quizzes, and assignments."""
    if not is_translation_enabled():
        return OrchestratorReport()

    total = translate_course_metadata(db, course, provider=provider)
    source_locale = _course_source_locale(course)

    for module in course.modules:
        r = translate_entity_fields(
            db,
            entity_type="module",
            entity_id=str(module.id),
            source_locale=source_locale,
            fields=[
                TranslationFieldSpec(field="title", text=module.title, content_kind="title"),
                TranslationFieldSpec(field="description", text=module.description, content_kind="plain"),
            ],
            context=f"Course module in «{course.title}»",
            provider=provider,
        )
        total = merge_orchestrator_reports(total, r)

    for module in course.modules:
        for chapter in module.chapters:
            r = translate_entity_fields(
                db,
                entity_type="chapter",
                entity_id=str(chapter.id),
                source_locale=source_locale,
                fields=[TranslationFieldSpec(field="title", text=chapter.title, content_kind="title")],
                context=f"Chapter in course «{course.title}»",
                provider=provider,
            )
            total = merge_orchestrator_reports(total, r)

    chapter_ids = [ch.id for mod in course.modules for ch in mod.chapters]
    if not chapter_ids:
        return total

    blocks = (
        db.query(ChapterBlock)
        .filter(ChapterBlock.chapter_id.in_(chapter_ids))
        .order_by(ChapterBlock.chapter_id, ChapterBlock.order_index)
        .all()
    )

    seen_quiz: set[str] = set()
    seen_assignment: set[str] = set()

    for block in blocks:
        if block.content and block.content.strip():
            r = translate_entity_fields(
                db,
                entity_type="chapter_block",
                entity_id=str(block.id),
                source_locale=source_locale,
                fields=[TranslationFieldSpec(field="content", text=block.content, content_kind="html")],
                context=f"HTML fragment from course «{course.title}»",
                provider=provider,
            )
            total = merge_orchestrator_reports(total, r)

        qid = str(block.quiz_id) if block.quiz_id else ""
        if qid and qid not in seen_quiz:
            seen_quiz.add(qid)
            quiz = (
                db.query(Quiz)
                .options(selectinload(Quiz.questions).selectinload(QuizQuestion.options))
                .filter(Quiz.id == block.quiz_id)
                .first()
            )
            if quiz:
                total = merge_orchestrator_reports(
                    total,
                    _translate_quiz_tree(
                        db,
                        quiz,
                        source_locale=source_locale,
                        course_title=course.title,
                        provider=provider,
                    ),
                )

        aid = str(block.assignment_id) if block.assignment_id else ""
        if aid and aid not in seen_assignment:
            seen_assignment.add(aid)
            assignment = db.query(Assignment).filter(Assignment.id == block.assignment_id).first()
            if assignment:
                r = translate_entity_fields(
                    db,
                    entity_type="assignment",
                    entity_id=str(assignment.id),
                    source_locale=source_locale,
                    fields=[
                        TranslationFieldSpec(field="title", text=assignment.title, content_kind="title"),
                        TranslationFieldSpec(field="description", text=assignment.description, content_kind="plain"),
                    ],
                    context=f"Assignment in course «{course.title}»",
                    provider=provider,
                )
                total = merge_orchestrator_reports(total, r)

    # Announcements live alongside the course (course_id FK) and are
    # surfaced to students in the announcements feed; they're not on the
    # chapter-tree walk above. Translate every announcement bound to this
    # course on every publish so a student in EN sees the EN copy.
    announcements = db.query(Announcement).filter(Announcement.course_id == course.id).all()
    for ann in announcements:
        r = translate_entity_fields(
            db,
            entity_type="announcement",
            entity_id=str(ann.id),
            source_locale=source_locale,
            fields=[
                TranslationFieldSpec(field="title", text=ann.title, content_kind="title"),
                TranslationFieldSpec(field="content", text=ann.content, content_kind="plain"),
            ],
            context=f"Announcement in course «{course.title}»",
            provider=provider,
        )
        total = merge_orchestrator_reports(total, r)

    # Same shape for calendar events bound to the course.
    events = db.query(CourseEvent).filter(CourseEvent.course_id == course.id).all()
    for ev in events:
        fields = [TranslationFieldSpec(field="title", text=ev.title, content_kind="title")]
        if ev.description:
            fields.append(TranslationFieldSpec(field="description", text=ev.description, content_kind="plain"))
        r = translate_entity_fields(
            db,
            entity_type="course_event",
            entity_id=str(ev.id),
            source_locale=source_locale,
            fields=fields,
            context=f"Calendar event in course «{course.title}»",
            provider=provider,
        )
        total = merge_orchestrator_reports(total, r)

    return total


__all__ = ["merge_orchestrator_reports", "translate_course_content"]
