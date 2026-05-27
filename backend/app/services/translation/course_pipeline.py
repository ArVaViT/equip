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
from app.models.content_translation import ContentTranslation
from app.models.course import Chapter, Module
from app.models.course_event import CourseEvent
from app.models.quiz import Quiz, QuizOption, QuizQuestion
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


def _collect_course_entity_ids(db: Session, course: Course) -> dict[str, list[str]]:
    """Return ``{entity_type: [entity_id, ...]}`` for every translatable
    entity under ``course``.

    Used by ``purge_course_translations`` when the course's
    ``source_locale`` flips and every translation row tied to the tree
    becomes suspect (the resolve path treats any ``status='ok'`` row
    as canonical and would serve stale machine translations of the
    OLD source over the new authoritative base text).

    The walk mirrors ``translate_course_content``'s shape so additions
    to the tree get covered both for writing AND for clearing: a
    teacher who adds a new block type without extending both functions
    will trigger CI-level regression (purge tests assert deletion counts).
    """
    ids: dict[str, list[str]] = {
        "course": [course.id],
        "module": [],
        "chapter": [],
        "chapter_block": [],
        "quiz": [],
        "quiz_question": [],
        "quiz_option": [],
        "assignment": [],
        "announcement": [],
        "course_event": [],
        "cohort": [],
    }

    module_rows = db.query(Module.id).filter(Module.course_id == course.id).all()
    module_ids = [str(m_id) for (m_id,) in module_rows]
    ids["module"] = module_ids

    if module_ids:
        chapter_rows = db.query(Chapter.id).filter(Chapter.module_id.in_(module_ids)).all()
        chapter_ids = [str(c_id) for (c_id,) in chapter_rows]
        ids["chapter"] = chapter_ids

        if chapter_ids:
            block_rows = (
                db.query(ChapterBlock.id, ChapterBlock.quiz_id, ChapterBlock.assignment_id)
                .filter(ChapterBlock.chapter_id.in_(chapter_ids))
                .all()
            )
            ids["chapter_block"] = [str(b_id) for (b_id, _, _) in block_rows]
            block_quiz_ids = {str(qid) for (_, qid, _) in block_rows if qid}
            block_assignment_ids = {str(aid) for (_, _, aid) in block_rows if aid}

            # Quizzes / assignments attach to either ``chapter_id`` (the live
            # production shape) or ``block.{quiz,assignment}_id`` (aspirational
            # shape) — collect via two separate queries instead of a single
            # ORed expression so the empty-block-set case doesn't pass a
            # placeholder UUID through SQLAlchemy's type processor.
            quiz_id_set: set[str] = set()
            for (q_id,) in db.query(Quiz.id).filter(Quiz.chapter_id.in_(chapter_ids)).all():
                quiz_id_set.add(str(q_id))
            if block_quiz_ids:
                for (q_id,) in db.query(Quiz.id).filter(Quiz.id.in_(block_quiz_ids)).all():
                    quiz_id_set.add(str(q_id))
            quiz_ids = sorted(quiz_id_set)
            ids["quiz"] = quiz_ids

            if quiz_ids:
                question_rows = db.query(QuizQuestion.id).filter(QuizQuestion.quiz_id.in_(quiz_ids)).all()
                question_ids = [str(q_id) for (q_id,) in question_rows]
                ids["quiz_question"] = question_ids
                if question_ids:
                    option_rows = db.query(QuizOption.id).filter(QuizOption.question_id.in_(question_ids)).all()
                    ids["quiz_option"] = [str(o_id) for (o_id,) in option_rows]

            assignment_id_set: set[str] = set()
            for (a_id,) in db.query(Assignment.id).filter(Assignment.chapter_id.in_(chapter_ids)).all():
                assignment_id_set.add(str(a_id))
            if block_assignment_ids:
                for (a_id,) in db.query(Assignment.id).filter(Assignment.id.in_(block_assignment_ids)).all():
                    assignment_id_set.add(str(a_id))
            ids["assignment"] = sorted(assignment_id_set)

    # Side entities.
    ann_rows = db.query(Announcement.id).filter(Announcement.course_id == course.id).all()
    ids["announcement"] = [str(a_id) for (a_id,) in ann_rows]

    ev_rows = db.query(CourseEvent.id).filter(CourseEvent.course_id == course.id).all()
    ids["course_event"] = [str(e_id) for (e_id,) in ev_rows]

    # Cohorts live independently (ADR-010); skip them in the per-course
    # purge — a cohort translation is shared across every course in the
    # cohort and isn't invalidated when one course's source language
    # changes.

    return ids


def purge_course_translations(db: Session, course: Course) -> int:
    """Delete every ``content_translations`` row tied to an entity under
    ``course``. Returns the number of rows deleted.

    Called from ``update_course`` when the course's ``source_locale``
    flips: every existing row is now suspect because it was generated
    against the OLD source language, and the resolve path would
    incorrectly prefer those stale rows over the new authoritative
    base text. The pipeline's subsequent run re-creates rows in the
    new direction (new source → new "other locales") from scratch.

    Cohort translations are intentionally NOT purged — cohorts are
    course-independent (ADR-010) and their text isn't affected when
    one of the cohort's courses changes language.
    """
    entity_ids_by_type = _collect_course_entity_ids(db, course)
    deleted = 0
    for entity_type, entity_ids in entity_ids_by_type.items():
        if not entity_ids:
            continue
        deleted += (
            db.query(ContentTranslation)
            .filter(
                ContentTranslation.entity_type == entity_type,
                ContentTranslation.entity_id.in_(entity_ids),
            )
            .delete(synchronize_session=False)
        )
    db.commit()
    return deleted


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
