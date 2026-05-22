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
from app.models.cohort import Cohort
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

    # Bulk-fetch every quiz + assignment in this course tree, both via
    # the chapter_id FK (the live production shape) and via the
    # block.{quiz,assignment}_id links (the aspirational shape).
    # Previously the block walk issued one SELECT per block with a
    # quiz_id and the chapter-bound query re-fetched them all — a
    # 50-chapter course with 30 quizzes paid O(30) extra reloads on
    # every publish. One ``OR`` query covers both paths with the same
    # selectinload for questions + options.
    block_quiz_ids = [b.quiz_id for b in blocks if b.quiz_id]
    block_assignment_ids = [b.assignment_id for b in blocks if b.assignment_id]

    all_quizzes = (
        db.query(Quiz)
        .options(selectinload(Quiz.questions).selectinload(QuizQuestion.options))
        .filter((Quiz.chapter_id.in_(chapter_ids)) | (Quiz.id.in_(block_quiz_ids) if block_quiz_ids else False))
        .all()
    )
    quizzes_by_id: dict[str, Quiz] = {str(q.id): q for q in all_quizzes}

    all_assignments = (
        db.query(Assignment)
        .filter(
            (Assignment.chapter_id.in_(chapter_ids))
            | (Assignment.id.in_(block_assignment_ids) if block_assignment_ids else False)
        )
        .all()
    )
    assignments_by_id: dict[str, Assignment] = {str(a.id): a for a in all_assignments}

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
            quiz = quizzes_by_id.get(qid)
            if quiz:
                total = merge_orchestrator_reports(
                    total,
                    _walk_quiz_tree(db, quiz, provider=provider),
                )

        aid = str(block.assignment_id) if block.assignment_id else ""
        if aid and aid not in seen_assignment:
            seen_assignment.add(aid)
            assignment = assignments_by_id.get(aid)
            if assignment:
                total = merge_orchestrator_reports(
                    total,
                    reconcile_entity(db, "assignment", assignment, provider=provider),
                )

    # Production teacher flow attaches quizzes + assignments via the
    # ``chapter_id`` FK directly; the chapter-block-mediated walk above
    # is an aspirational shape that the create flows have never
    # populated. Pick up anything the block walk missed by iterating
    # over the bulk fetch and reconciling rows that ``seen_*`` hasn't
    # already covered.
    #
    # This is what makes the pipeline actually translate quiz text in
    # production. See 2026-05-16 audit; without this pass, every course
    # in prod had zero ``content_translations`` rows for ``quiz`` /
    # ``quiz_question`` / ``quiz_option`` / ``assignment``.
    for quiz in all_quizzes:
        qid = str(quiz.id)
        if qid in seen_quiz:
            continue
        seen_quiz.add(qid)
        total = merge_orchestrator_reports(
            total,
            _walk_quiz_tree(db, quiz, provider=provider),
        )

    for assignment in all_assignments:
        aid = str(assignment.id)
        if aid in seen_assignment:
            continue
        seen_assignment.add(aid)
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
    # Cohorts now live independently of courses (ADR-010) and attach via
    # the ``cohort_courses`` junction. Reconcile every cohort that
    # currently includes this course — each course-locale pair gets its
    # own translation overlay row for the cohort name.
    from app.models.cohort import CohortCourse

    for co in (
        db.query(Cohort)
        .join(CohortCourse, Cohort.id == CohortCourse.cohort_id)
        .filter(CohortCourse.course_id == course.id)
        .all()
    ):
        total = merge_orchestrator_reports(
            total,
            reconcile_entity(db, "cohort", co, provider=provider),
        )
    return total


__all__ = ["merge_orchestrator_reports", "translate_course_content"]
