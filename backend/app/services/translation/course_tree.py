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
    """
    yield "course", course

    for module in course.modules:
        yield "module", module

    for module in course.modules:
        for chapter in module.chapters:
            yield "chapter", chapter

    chapter_ids = [ch.id for mod in course.modules for ch in mod.chapters]
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
