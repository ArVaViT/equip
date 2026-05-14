"""Deep clone of a course tree (modules, chapters, blocks, quizzes, assignments)."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import TYPE_CHECKING

from app.models.assignment import Assignment
from app.models.chapter_block import ChapterBlock
from app.models.course import Chapter, Course, CourseStatus, Module
from app.models.quiz import Quiz, QuizOption, QuizQuestion

from ._queries import _COURSE_TREE

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def clone_course(db: Session, course_id: str, teacher_id: str | uuid.UUID) -> Course | None:
    """Deep-clone a course and all nested content. Returns the new Course.

    Copies: Course -> Modules -> Chapters -> ChapterBlocks, Quizzes
    (with questions + options), Assignments.
    ChapterBlock.quiz_id / assignment_id are remapped to the cloned entities.
    Enrollments, progress, grades, submissions, and certificates are NOT copied.
    """
    # Only clone live courses. Attempting to clone a trashed course should
    # 404 (mirrors the API-level visibility rules in get_course()).
    original = (
        db.query(Course).options(*_COURSE_TREE).filter(Course.id == course_id, Course.deleted_at.is_(None)).first()
    )
    if original is None:
        return None

    all_chapter_ids = [ch.id for mod in original.modules for ch in mod.chapters]
    if not all_chapter_ids:
        all_quizzes: list[Quiz] = []
        all_questions: list[QuizQuestion] = []
        all_options: list[QuizOption] = []
        all_assignments: list[Assignment] = []
        all_blocks: list[ChapterBlock] = []
    else:
        all_quizzes = db.query(Quiz).filter(Quiz.chapter_id.in_(all_chapter_ids)).all()
        all_quiz_ids = [q.id for q in all_quizzes]

        all_questions = (
            db.query(QuizQuestion).filter(QuizQuestion.quiz_id.in_(all_quiz_ids)).all() if all_quiz_ids else []
        )
        all_question_ids = [q.id for q in all_questions]

        all_options = (
            db.query(QuizOption).filter(QuizOption.question_id.in_(all_question_ids)).all() if all_question_ids else []
        )

        all_assignments = db.query(Assignment).filter(Assignment.chapter_id.in_(all_chapter_ids)).all()
        all_blocks = db.query(ChapterBlock).filter(ChapterBlock.chapter_id.in_(all_chapter_ids)).all()

    quizzes_by_chapter: dict[str, list[Quiz]] = defaultdict(list)
    for q in all_quizzes:
        quizzes_by_chapter[q.chapter_id].append(q)

    questions_by_quiz: dict[str, list[QuizQuestion]] = defaultdict(list)
    for qq in all_questions:
        questions_by_quiz[str(qq.quiz_id)].append(qq)

    options_by_question: dict[str, list[QuizOption]] = defaultdict(list)
    for o in all_options:
        options_by_question[str(o.question_id)].append(o)

    assignments_by_chapter: dict[str, list[Assignment]] = defaultdict(list)
    for a in all_assignments:
        assignments_by_chapter[a.chapter_id].append(a)

    blocks_by_chapter: dict[str, list[ChapterBlock]] = defaultdict(list)
    for b in all_blocks:
        blocks_by_chapter[b.chapter_id].append(b)

    new_course_id = str(uuid.uuid4())
    new_course = Course(
        id=new_course_id,
        title=f"{original.title} (Copy)",
        description=original.description,
        image_url=original.image_url,
        status=CourseStatus.DRAFT,
        created_by=uuid.UUID(teacher_id) if isinstance(teacher_id, str) else teacher_id,
        enrollment_start=None,
        enrollment_end=None,
    )
    db.add(new_course)

    for module in sorted(original.modules, key=lambda m: m.order_index):
        new_module_id = str(uuid.uuid4())
        new_module = Module(
            id=new_module_id,
            course_id=new_course_id,
            title=module.title,
            description=module.description,
            order_index=module.order_index,
            due_date=module.due_date,
        )
        db.add(new_module)

        for chapter in sorted(module.chapters, key=lambda c: c.order_index):
            new_chapter_id = str(uuid.uuid4())
            new_chapter = Chapter(
                id=new_chapter_id,
                module_id=new_module_id,
                title=chapter.title,
                order_index=chapter.order_index,
                chapter_type=chapter.chapter_type,
                requires_completion=chapter.requires_completion,
                is_locked=chapter.is_locked,
            )
            db.add(new_chapter)
            # Postgres' unit-of-work topological sort handles the chapter →
            # block ordering correctly; SQLite (PRAGMA foreign_keys=ON, used
            # by tests) does not because ``ChapterBlock.chapter_id`` is a
            # plain String FK without a relationship wired through. Gate the
            # flush to the SQLite path so prod clones don't take N
            # round-trips for a cosmetic test-only safety net.
            if db.bind is not None and db.bind.dialect.name == "sqlite":
                db.flush()

            quiz_id_map: dict[str, uuid.UUID] = {}
            assignment_id_map: dict[str, uuid.UUID] = {}

            for quiz in quizzes_by_chapter.get(chapter.id, []):
                new_quiz_id = uuid.uuid4()
                quiz_id_map[str(quiz.id)] = new_quiz_id
                db.add(
                    Quiz(
                        id=new_quiz_id,
                        chapter_id=new_chapter_id,
                        title=quiz.title,
                        description=quiz.description,
                        quiz_type=quiz.quiz_type or "quiz",
                        max_attempts=quiz.max_attempts,
                        passing_score=quiz.passing_score,
                    )
                )

                for question in sorted(
                    questions_by_quiz.get(str(quiz.id), []),
                    key=lambda q: q.order_index,
                ):
                    new_question_id = uuid.uuid4()
                    db.add(
                        QuizQuestion(
                            id=new_question_id,
                            quiz_id=new_quiz_id,
                            question_text=question.question_text,
                            question_type=question.question_type,
                            order_index=question.order_index,
                            points=question.points,
                            min_words=question.min_words,
                        )
                    )

                    for option in sorted(
                        options_by_question.get(str(question.id), []),
                        key=lambda o: o.order_index,
                    ):
                        db.add(
                            QuizOption(
                                id=uuid.uuid4(),
                                question_id=new_question_id,
                                option_text=option.option_text,
                                is_correct=option.is_correct,
                                order_index=option.order_index,
                            )
                        )

            for assignment in assignments_by_chapter.get(chapter.id, []):
                new_assignment_id = uuid.uuid4()
                assignment_id_map[str(assignment.id)] = new_assignment_id
                db.add(
                    Assignment(
                        id=new_assignment_id,
                        chapter_id=new_chapter_id,
                        title=assignment.title,
                        description=assignment.description,
                        max_score=assignment.max_score,
                        due_date=None,
                    )
                )

            for block in sorted(blocks_by_chapter.get(chapter.id, []), key=lambda b: b.order_index):
                db.add(
                    ChapterBlock(
                        id=uuid.uuid4(),
                        chapter_id=new_chapter_id,
                        block_type=block.block_type,
                        order_index=block.order_index,
                        content=block.content,
                        quiz_id=quiz_id_map.get(str(block.quiz_id)) if block.quiz_id else None,
                        assignment_id=assignment_id_map.get(str(block.assignment_id)) if block.assignment_id else None,
                        file_bucket=block.file_bucket,
                        file_path=block.file_path,
                        file_name=block.file_name,
                    )
                )

    db.commit()

    return db.query(Course).options(*_COURSE_TREE).filter(Course.id == new_course_id).first()
