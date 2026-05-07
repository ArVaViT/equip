"""Translate all teacher-authored text under a course (metadata + tree).

Invoked after publish and after edits while the course stays published.
Idempotent via the orchestrator's ``source_hash`` short-circuit, so a
re-run on an unchanged course costs zero LLM calls.

Per-entity field specs (which fields, which content_kind) live in
``registry.REGISTRY``; this module only encodes the *shape of the tree*
— how to walk modules → chapters → blocks → quiz/assignment, plus the
side entities (announcements, calendar events) bound by ``course_id``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import selectinload

from app.models.announcement import Announcement
from app.models.assignment import Assignment
from app.models.chapter_block import ChapterBlock
from app.models.course_event import CourseEvent
from app.models.quiz import Quiz, QuizQuestion
from app.services.translation.orchestrator import OrchestratorReport
from app.services.translation.registry import reconcile_entity
from app.services.translation.service import is_translation_enabled

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.course import Course
    from app.services.translation.protocol import TranslationProvider

logger = logging.getLogger(__name__)


def merge_orchestrator_reports(*parts: OrchestratorReport) -> OrchestratorReport:
    return OrchestratorReport(
        translated=sum(p.translated for p in parts),
        skipped=sum(p.skipped for p in parts),
        failed=sum(p.failed for p in parts),
    )


def _walk_quiz_tree(
    db: Session,
    quiz: Quiz,
    *,
    provider: TranslationProvider | None,
) -> OrchestratorReport:
    """Reconcile quiz + every nested question + every nested option."""
    total = reconcile_entity(db, "quiz", quiz, provider=provider)
    for question in quiz.questions:
        total = merge_orchestrator_reports(
            total,
            reconcile_entity(db, "quiz_question", question, provider=provider),
        )
        for opt in question.options:
            total = merge_orchestrator_reports(
                total,
                reconcile_entity(db, "quiz_option", opt, provider=provider),
            )
    return total


def translate_course_content(
    db: Session,
    course: Course,
    *,
    provider: TranslationProvider | None = None,
) -> OrchestratorReport:
    """Translate everything teacher-authored under ``course`` into every
    locale that's not the course's source locale.

    Iteration order: course metadata → modules → chapters → chapter
    blocks (following block→quiz / block→assignment links) → side
    entities (announcements, calendar events). Each per-entity step
    delegates to ``reconcile_entity`` which reads the field spec from
    ``REGISTRY``.
    """
    if not is_translation_enabled():
        return OrchestratorReport()

    total = reconcile_entity(db, "course", course, provider=provider)

    for module in course.modules:
        total = merge_orchestrator_reports(
            total,
            reconcile_entity(db, "module", module, provider=provider),
        )

    for module in course.modules:
        for chapter in module.chapters:
            total = merge_orchestrator_reports(
                total,
                reconcile_entity(db, "chapter", chapter, provider=provider),
            )

    chapter_ids = [ch.id for mod in course.modules for ch in mod.chapters]
    if not chapter_ids:
        # Empty course tree — still process side entities below.
        side = _translate_course_side_entities(db, course, provider=provider)
        return merge_orchestrator_reports(total, side)

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
            total = merge_orchestrator_reports(
                total,
                reconcile_entity(db, "chapter_block", block, provider=provider),
            )

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
                    _walk_quiz_tree(db, quiz, provider=provider),
                )

        aid = str(block.assignment_id) if block.assignment_id else ""
        if aid and aid not in seen_assignment:
            seen_assignment.add(aid)
            assignment = db.query(Assignment).filter(Assignment.id == block.assignment_id).first()
            if assignment:
                total = merge_orchestrator_reports(
                    total,
                    reconcile_entity(db, "assignment", assignment, provider=provider),
                )

    side = _translate_course_side_entities(db, course, provider=provider)
    return merge_orchestrator_reports(total, side)


def _translate_course_side_entities(
    db: Session,
    course: Course,
    *,
    provider: TranslationProvider | None,
) -> OrchestratorReport:
    """Reconcile course-bound entities that are NOT in the chapter tree:
    teacher-authored announcements + calendar events tied to this
    course's ``course_id``.
    """
    total = OrchestratorReport()
    for ann in db.query(Announcement).filter(Announcement.course_id == course.id).all():
        total = merge_orchestrator_reports(
            total,
            reconcile_entity(db, "announcement", ann, provider=provider),
        )
    for ev in db.query(CourseEvent).filter(CourseEvent.course_id == course.id).all():
        total = merge_orchestrator_reports(
            total,
            reconcile_entity(db, "course_event", ev, provider=provider),
        )
    return total


__all__ = ["merge_orchestrator_reports", "translate_course_content"]
