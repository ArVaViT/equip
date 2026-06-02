"""Seed a "fat" test course for pre-pilot regression testing.

Pilot schools plan to deploy 5+ courses with 30+ modules each; the
two real courses on prod (Деяния + Библия как историч. док) are
nowhere near that shape, so the catalog / dashboard / progress
surfaces have never been stress-tested at realistic pilot scale.

This script provisions one big course (default 35 modules, 5
chapters per module, 175 total chapters) with mixed chapter types
(reading + quiz + assignment), one block per chapter, and one quiz
per quiz-typed chapter. Designed to be idempotent: re-runs with the
same ``--course-id`` upsert the structure rather than duplicating
it.

Run against any environment (SQLite test, Postgres dev, Supabase
staging — never prod). The course is marked ``draft`` so a stray
run against prod doesn't surface to users; promote to ``published``
manually after eyeballing the dashboard render.

Usage:

    python -m scripts.seed_fat_test_course --course-id fat-test \\
        --teacher-email teacher@example.com \\
        --modules 35 --chapters-per-module 5

The teacher must already exist in the ``profiles`` table; we look up
by email and abort if missing rather than auto-create (auto-creating
admin users from a script would be too easy to fat-finger).
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from typing import TYPE_CHECKING

from sqlalchemy.orm import sessionmaker

from app.core.database import _get_engine
from app.models.assignment import Assignment
from app.models.chapter_block import ChapterBlock
from app.models.course import Chapter, Course, Module
from app.models.quiz import Quiz, QuizOption, QuizQuestion
from app.models.user import User
from app.services.content_versions.write import record_human_version

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("seed_fat_test_course")


# Cycle types deterministically so the seed is reproducible — every
# 5th chapter is reading / quiz / assignment / reading / quiz, etc.
_CHAPTER_TYPE_CYCLE = ("reading", "quiz", "assignment", "reading", "quiz")


def _cv_text(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    field: str,
    text: str,
    locale: str = "en",
    actor_id: uuid.UUID,
) -> None:
    if text:
        record_human_version(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            locale=locale,
            text=text,
            authored_by=actor_id,
        )


def _ensure_course(db: Session, *, course_id: str, title: str, teacher: User) -> Course:
    course = db.query(Course).filter(Course.id == course_id).first()
    if course is None:
        course = Course(
            id=course_id,
            status="draft",  # NEVER auto-publish from a script
            source_locale="en",
            created_by=teacher.id,
            access_mode="public",
            quiz_weight=40,
            assignment_weight=40,
            participation_weight=20,
        )
        db.add(course)
        db.flush()
        _cv_text(
            db,
            entity_type="course",
            entity_id=course.id,
            field="title",
            text=title,
            actor_id=teacher.id,
        )
        _cv_text(
            db,
            entity_type="course",
            entity_id=course.id,
            field="description",
            text="Synthetic course for pilot-scale regression testing. NOT for student use.",
            actor_id=teacher.id,
        )
        logger.info("Created course %s", course_id)
    else:
        logger.info("Course %s exists; reusing", course_id)
    return course


def _ensure_module(
    db: Session,
    *,
    course_id: str,
    index: int,
    teacher: User,
) -> Module:
    module_id = f"{course_id}-mod-{index:03d}"
    module = db.query(Module).filter(Module.id == module_id).first()
    if module is None:
        module = Module(id=module_id, course_id=course_id, order_index=index)
        db.add(module)
        db.flush()
        _cv_text(
            db,
            entity_type="module",
            entity_id=module.id,
            field="title",
            text=f"Module {index + 1}",
            actor_id=teacher.id,
        )
        _cv_text(
            db,
            entity_type="module",
            entity_id=module.id,
            field="description",
            text=f"Auto-seeded module {index + 1} for fat-course testing.",
            actor_id=teacher.id,
        )
    return module


def _ensure_chapter(
    db: Session,
    *,
    module: Module,
    index: int,
    chapter_type: str,
) -> Chapter:
    chapter_id = f"{module.id}-ch-{index:03d}"
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if chapter is None:
        chapter = Chapter(
            id=chapter_id,
            module_id=module.id,
            title=f"Chapter {index + 1}",
            order_index=index,
            chapter_type=chapter_type,
        )
        db.add(chapter)
        db.flush()
    return chapter


def _ensure_block(db: Session, *, chapter_id: str, teacher: User) -> None:
    """One text block per chapter so the BlockRenderer + DOMPurify
    pipeline gets exercised at this scale."""
    block_marker = db.query(ChapterBlock).filter(ChapterBlock.chapter_id == chapter_id).first()
    if block_marker is not None:
        return
    block = ChapterBlock(
        id=uuid.uuid4(),
        chapter_id=chapter_id,
        block_type="text",
        order_index=0,
    )
    db.add(block)
    db.flush()
    _cv_text(
        db,
        entity_type="chapter_block",
        entity_id=str(block.id),
        field="content",
        text=(
            "<p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Pinned for fat-course regression coverage.</p>"
        ),
        actor_id=teacher.id,
    )


def _ensure_quiz(db: Session, *, chapter_id: str, teacher: User) -> None:
    """One 4-option multiple-choice question per quiz-typed chapter
    so the quiz-attempt flow at scale also gets exercised."""
    existing = db.query(Quiz).filter(Quiz.chapter_id == chapter_id).first()
    if existing is not None:
        return
    quiz = Quiz(
        id=uuid.uuid4(),
        chapter_id=chapter_id,
        quiz_type="quiz",
        passing_score=70,
    )
    db.add(quiz)
    db.flush()
    _cv_text(
        db,
        entity_type="quiz",
        entity_id=str(quiz.id),
        field="title",
        text="Sample Quiz",
        actor_id=teacher.id,
    )

    question = QuizQuestion(
        id=uuid.uuid4(),
        quiz_id=quiz.id,
        question_type="multiple_choice",
        order_index=0,
        points=1,
    )
    db.add(question)
    db.flush()
    _cv_text(
        db,
        entity_type="quiz_question",
        entity_id=str(question.id),
        field="question_text",
        text="2 + 2 = ?",
        actor_id=teacher.id,
    )

    correct_index = 1  # "4"
    for idx, label in enumerate(("3", "4", "5", "6")):
        opt = QuizOption(
            id=uuid.uuid4(),
            question_id=question.id,
            is_correct=(idx == correct_index),
            order_index=idx,
        )
        db.add(opt)
        db.flush()
        _cv_text(
            db,
            entity_type="quiz_option",
            entity_id=str(opt.id),
            field="option_text",
            text=label,
            actor_id=teacher.id,
        )


def _ensure_assignment(db: Session, *, chapter_id: str, teacher: User) -> None:
    existing = db.query(Assignment).filter(Assignment.chapter_id == chapter_id).first()
    if existing is not None:
        return
    assignment = Assignment(
        id=uuid.uuid4(),
        chapter_id=chapter_id,
        max_score=100,
    )
    db.add(assignment)
    db.flush()
    _cv_text(
        db,
        entity_type="assignment",
        entity_id=str(assignment.id),
        field="title",
        text="Sample Assignment",
        actor_id=teacher.id,
    )
    _cv_text(
        db,
        entity_type="assignment",
        entity_id=str(assignment.id),
        field="description",
        text="Write a one-paragraph reflection.",
        actor_id=teacher.id,
    )


def seed(
    db: Session,
    *,
    course_id: str,
    title: str,
    modules: int,
    chapters_per_module: int,
    teacher: User,
) -> dict:
    course = _ensure_course(db, course_id=course_id, title=title, teacher=teacher)

    chapter_total = 0
    quiz_total = 0
    assignment_total = 0
    for m_idx in range(modules):
        module = _ensure_module(db, course_id=course.id, index=m_idx, teacher=teacher)
        for c_idx in range(chapters_per_module):
            chapter_type = _CHAPTER_TYPE_CYCLE[c_idx % len(_CHAPTER_TYPE_CYCLE)]
            chapter = _ensure_chapter(db, module=module, index=c_idx, chapter_type=chapter_type)
            chapter_total += 1
            _ensure_block(db, chapter_id=chapter.id, teacher=teacher)
            if chapter_type == "quiz":
                _ensure_quiz(db, chapter_id=chapter.id, teacher=teacher)
                quiz_total += 1
            elif chapter_type == "assignment":
                _ensure_assignment(db, chapter_id=chapter.id, teacher=teacher)
                assignment_total += 1
        if (m_idx + 1) % 5 == 0:
            db.commit()
            logger.info("Committed through module %s", m_idx + 1)
    db.commit()

    return {
        "course_id": course.id,
        "modules": modules,
        "chapters": chapter_total,
        "quizzes": quiz_total,
        "assignments": assignment_total,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-id", default="fat-test", help="Course id slug")
    parser.add_argument("--title", default="Fat Test Course", help="Display title")
    parser.add_argument("--modules", type=int, default=35, help="Module count")
    parser.add_argument(
        "--chapters-per-module",
        type=int,
        default=5,
        help="Chapters per module (mixed types: reading / quiz / assignment)",
    )
    parser.add_argument(
        "--teacher-email",
        required=True,
        help="Email of the existing User row to set as course owner",
    )
    args = parser.parse_args()

    if args.modules < 1 or args.chapters_per_module < 1:
        logger.error("modules and chapters-per-module must be >= 1")
        return 1

    engine = _get_engine()
    SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with SessionFactory() as db:
        teacher = db.query(User).filter(User.email == args.teacher_email).first()
        if teacher is None:
            logger.error(
                "Teacher %s not found in profiles. Create the user via the app first, then re-run.",
                args.teacher_email,
            )
            return 1

        report = seed(
            db,
            course_id=args.course_id,
            title=args.title,
            modules=args.modules,
            chapters_per_module=args.chapters_per_module,
            teacher=teacher,
        )
        logger.info(
            "Seeded course=%s modules=%d chapters=%d quizzes=%d assignments=%d",
            report["course_id"],
            report["modules"],
            report["chapters"],
            report["quizzes"],
            report["assignments"],
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
