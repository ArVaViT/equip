"""The shape of a course's translatable tree, walked once.

``course_pipeline`` knew how to walk modules → chapters → blocks →
quizzes/assignments → side entities in order to *translate* each node.
Publication now needs the same walk in order to *check* each node —
whether every locale already has an accepted translation — and a second
copy of the walk would be a copy that drifts. So the walk lives here,
yields ``(entity_type, entity)`` pairs, and both callers consume it.

Order is preserved from the original pipeline: course metadata, then
modules, then chapters, then blocks (following block→quiz and
block→assignment links), then any quiz or assignment attached straight
to a chapter, then the side entities bound by ``course_id``.

That last group is not decorative. Production attaches quizzes and
assignments via the ``chapter_id`` FK; the block-mediated links are an
aspirational shape the create flows never populated. Before the
chapter-bound pass existed, every course in production had zero
translation rows for quizzes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.orm import selectinload

from app.models.announcement import Announcement
from app.models.assignment import Assignment
from app.models.chapter_block import ChapterBlock
from app.models.cohort import Cohort, CohortCourse
from app.models.course_event import CourseEvent
from app.models.quiz import Quiz, QuizQuestion
from app.models.rubric import Rubric, RubricCriterion, RubricLevel

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

    from app.models.course import Course
    from app.services.translation.protocol import EntityType


def _iter_quiz_tree(quiz: Quiz) -> Iterator[tuple[EntityType, object]]:
    yield "quiz", quiz
    for question in quiz.questions:
        yield "quiz_question", question
        for option in question.options:
            yield "quiz_option", option


def iter_course_entities(db: Session, course: Course) -> Iterator[tuple[EntityType, object]]:
    """Yield every translatable entity under ``course``, in walk order.

    One pass, bulk-fetched: blocks in one query, every quiz and
    assignment in one query each (both the chapter-bound and the
    block-linked shape), questions and options eagerly loaded.

    Binned modules and chapters are skipped here rather than left to the
    caller's loader, and that is load-bearing. ``get_course`` filters
    them out through its relationship options; a plain ``db.get`` does
    not. The pipeline used both — the worker planned through
    ``get_course`` and the completeness check walked a course fetched by
    the sweep's own query — so the two disagreed about how large the
    course was. The result was a gap nothing could ever close: the check
    demanded translations for chapters in the bin, the plan never
    produced them, and the sweep re-queued the course every tick for a
    job that had nothing to do. It cost nothing while every course was
    complete, and became a permanent spin the moment anything counted as
    missing.

    A binned chapter has no readers, so it needs no translations. One
    walk, one answer, whichever way the course arrived.
    """
    yield "course", course

    modules = [module for module in course.modules if module.deleted_at is None]
    for module in modules:
        yield "module", module

    for module in modules:
        for chapter in module.chapters:
            if chapter.deleted_at is None:
                yield "chapter", chapter

    chapter_ids = [ch.id for mod in modules for ch in mod.chapters if ch.deleted_at is None]
    if chapter_ids:
        blocks = (
            db.query(ChapterBlock)
            .filter(ChapterBlock.chapter_id.in_(chapter_ids))
            .order_by(ChapterBlock.chapter_id, ChapterBlock.order_index)
            .all()
        )
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
            yield "chapter_block", block

            qid = str(block.quiz_id) if block.quiz_id else ""
            if qid and qid not in seen_quiz:
                seen_quiz.add(qid)
                quiz = quizzes_by_id.get(qid)
                if quiz:
                    yield from _iter_quiz_tree(quiz)

            aid = str(block.assignment_id) if block.assignment_id else ""
            if aid and aid not in seen_assignment:
                seen_assignment.add(aid)
                assignment = assignments_by_id.get(aid)
                if assignment:
                    yield "assignment", assignment

        for quiz in all_quizzes:
            qid = str(quiz.id)
            if qid in seen_quiz:
                continue
            seen_quiz.add(qid)
            yield from _iter_quiz_tree(quiz)

        for assignment in all_assignments:
            aid = str(assignment.id)
            if aid in seen_assignment:
                continue
            seen_assignment.add(aid)
            yield "assignment", assignment

    yield from _iter_course_side_entities(db, course)


def _iter_course_side_entities(db: Session, course: Course) -> Iterator[tuple[EntityType, object]]:
    """Course-bound entities outside the chapter tree: announcements,
    calendar events, and the cohorts this course is attached to."""
    # A rubric is course-scoped and lives outside the chapter tree, like
    # the announcements below it. It reached this walk last of all the
    # reader-facing text on the platform: until it did, a student's mark
    # was explained to them in whatever language the teacher wrote in.
    for rubric in db.query(Rubric).filter(Rubric.course_id == course.id, Rubric.archived_at.is_(None)).all():
        yield "rubric", rubric
        criteria = (
            db.query(RubricCriterion)
            .filter(RubricCriterion.rubric_id == rubric.id, RubricCriterion.archived_at.is_(None))
            .order_by(RubricCriterion.order_index)
            .all()
        )
        for criterion in criteria:
            yield "rubric_criterion", criterion
            levels = (
                db.query(RubricLevel)
                .filter(RubricLevel.criterion_id == criterion.id, RubricLevel.archived_at.is_(None))
                .order_by(RubricLevel.order_index)
                .all()
            )
            for level in levels:
                yield "rubric_level", level

    for ann in db.query(Announcement).filter(Announcement.course_id == course.id).all():
        yield "announcement", ann
    for ev in db.query(CourseEvent).filter(CourseEvent.course_id == course.id).all():
        yield "course_event", ev
    # Cohorts live independently of courses (ADR-010) and attach via the
    # ``cohort_courses`` junction.
    for cohort in (
        db.query(Cohort)
        .join(CohortCourse, Cohort.id == CohortCourse.cohort_id)
        .filter(CohortCourse.course_id == course.id)
        .all()
    ):
        yield "cohort", cohort


__all__ = ["iter_course_entities"]
