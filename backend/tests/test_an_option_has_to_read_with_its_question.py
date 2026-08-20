"""An answer option is a fragment, and fragments have to agree.

A quiz stem that ends in a colon governs what follows it: "Псалтирь
состоит из:" wants the genitive, "basiert auf:" wants the dative, "is
associated with:" wants no preposition of its own. The Russian author
writes all four options at once and keeps the case in every one.

The pipeline translated each option alone, with the context line
"Answer option for a Bible-study quiz question." — which says nothing
about the sentence it has to continue. So the model produced dictionary
forms, and an editor counting one course found eight German options that
do not read with their stem, nine English, four Ukrainian. The most
damaging kind: often it was the correct answer that stood out, which
turns a grammar defect into a hint.

The question now travels with the option, and the model is told to agree
with it rather than translate it.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from app.models.chapter_block import ChapterBlock
from app.models.course import Chapter, Course, CourseStatus, Module
from app.models.quiz import Quiz, QuizOption, QuizQuestion
from app.models.user import User
from app.services.content_versions import record_human_version
from app.services.translation.registry import REGISTRY

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

TEACHER_ID = uuid.UUID("00000000-0000-0000-0000-00000000bd11")
STEM = "Псалтирь состоит из:"


@pytest.fixture
def an_option(db: Session) -> QuizOption:
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="stem@example.com", full_name="T", role="teacher"))
        db.commit()
    course = Course(
        id=f"course-{uuid.uuid4().hex[:8]}",
        status=CourseStatus.PUBLISHED,
        source_locale="ru",
        created_by=TEACHER_ID,
    )
    db.add(course)
    db.flush()
    module = Module(id=f"mod-{uuid.uuid4().hex[:8]}", course_id=course.id, title="Модуль", order_index=0)
    db.add(module)
    db.flush()
    chapter = Chapter(id=f"ch-{uuid.uuid4().hex[:8]}", module_id=module.id, title="Глава", order_index=0)
    db.add(chapter)
    db.flush()
    quiz = Quiz(id=uuid.uuid4(), chapter_id=chapter.id)
    db.add(quiz)
    db.flush()
    question = QuizQuestion(id=uuid.uuid4(), quiz_id=quiz.id, order_index=0, question_type="multiple_choice")
    db.add(question)
    db.flush()
    option = QuizOption(id=uuid.uuid4(), question_id=question.id, order_index=0, is_correct=True)
    db.add(option)
    db.commit()

    record_human_version(
        db,
        entity_type="quiz_question",
        entity_id=str(question.id),
        field="question_text",
        locale="ru",
        text=STEM,
    )
    record_human_version(
        db,
        entity_type="quiz_option",
        entity_id=str(option.id),
        field="option_text",
        locale="ru",
        text="Пяти частей",
    )
    db.commit()
    return option


class TestTheQuestionTravelsWithTheOption:
    def test_the_stem_is_in_the_context(self, db: Session, an_option: QuizOption) -> None:
        context = REGISTRY["quiz_option"].build_context_with_db(db, an_option, None)
        assert STEM in context

    def test_the_model_is_told_to_agree_not_translate(self, db: Session, an_option: QuizOption) -> None:
        context = REGISTRY["quiz_option"].build_context_with_db(db, an_option, None)
        assert "Do not translate the question" in context
        assert "GRAMMAR ONLY" in context

    def test_and_told_twice_that_a_wrong_answer_stays_wrong(self, db: Session, an_option: QuizOption) -> None:
        # Given the question and nothing else, the model repairs the
        # distractors: 18 question-and-language pairs came back with a
        # wrong option rewritten into a copy of the right one, which
        # makes the question unanswerable. The Russian source has no
        # duplicate options in 128 questions — every one was introduced
        # in translation.
        context = REGISTRY["quiz_option"].build_context_with_db(db, an_option, None)
        assert "wrong answers on purpose" in context
        assert "never let it drift towards the right answer" in context

    def test_an_orphan_option_still_gets_something(self, db: Session) -> None:
        # A question that has lost its text must not take the option's
        # translation down with it.
        orphan = QuizOption(id=uuid.uuid4(), question_id=uuid.uuid4(), order_index=0, is_correct=False)
        context = REGISTRY["quiz_option"].build_context_with_db(db, orphan, None)
        assert context
        assert "Answer option" in context


class TestTheSameHoldsForTheDailyChallenge:
    def test_it_asks_for_the_question(self, db: Session) -> None:
        from app.models.daily_challenge import DailyChallengeOption, DailyChallengeQuestion

        question = DailyChallengeQuestion(
            id=uuid.uuid4(),
            question_type="multiple_choice",
            status="published",
            bible_book="Acts",
            bible_chapter=2,
            category="passage_exegesis",
            source_locale="en",
            created_by=TEACHER_ID,
        )
        if db.get(User, TEACHER_ID) is None:
            db.add(User(id=TEACHER_ID, email="stem@example.com", full_name="T", role="teacher"))
            db.commit()
        db.add(question)
        db.flush()
        option = DailyChallengeOption(id=uuid.uuid4(), question_id=question.id, order_index=0, is_correct=True)
        db.add(option)
        db.commit()
        record_human_version(
            db,
            entity_type="daily_challenge_question",
            entity_id=str(question.id),
            field="question_text",
            locale="en",
            text="What happened at Pentecost?",
        )
        db.commit()

        context = REGISTRY["daily_challenge_option"].build_context_with_db(db, option, None)
        assert "What happened at Pentecost?" in context


class TestNothingElseChanged:
    def test_a_course_keeps_the_simple_context_it_had(self, db: Session, an_option: QuizOption) -> None:
        # Only the entities that need a neighbour to be judged by gained a
        # database-backed context. A course title is judged on its own.
        assert REGISTRY["course"].build_context_with_db is None
        assert REGISTRY["course"].build_context is not None
        assert ChapterBlock is not None


class TestABlockIsJudgedBesideItsNeighbour:
    """A paragraph translated alone cannot be checked alone.

    A lesson block was described to the model as "HTML fragment from
    course X" — enough to translate the words, not enough to judge the
    result. Production shows both halves of that gap: the teaching point
    "usage determines meaning" came back as its own opposite in German
    (English and Ukrainian got it right, and the sentence that settles it
    is in the next block), and the Sanhedrin is three different German
    words across one course because each occurrence was decided alone.
    """

    def test_the_previous_paragraph_travels_with_it(self, db: Session) -> None:
        from app.models.chapter_block import ChapterBlock as Block
        from app.models.course import Chapter as Ch
        from app.models.course import Course as C
        from app.models.course import CourseStatus as CS
        from app.models.course import Module as M

        if db.get(User, TEACHER_ID) is None:
            db.add(User(id=TEACHER_ID, email="stem@example.com", full_name="T", role="teacher"))
            db.commit()
        course = C(
            id=f"course-{uuid.uuid4().hex[:8]}",
            status=CS.PUBLISHED,
            source_locale="ru",
            created_by=TEACHER_ID,
        )
        db.add(course)
        db.flush()
        module = M(id=f"mod-{uuid.uuid4().hex[:8]}", course_id=course.id, title="Модуль", order_index=0)
        db.add(module)
        db.flush()
        chapter = Ch(id=f"ch-{uuid.uuid4().hex[:8]}", module_id=module.id, title="Глава", order_index=0)
        db.add(chapter)
        db.flush()
        first = Block(id=uuid.uuid4(), chapter_id=chapter.id, block_type="text", order_index=0)
        second = Block(id=uuid.uuid4(), chapter_id=chapter.id, block_type="text", order_index=1)
        db.add_all([first, second])
        db.commit()

        record_human_version(
            db,
            entity_type="chapter_block",
            entity_id=str(first.id),
            field="content",
            locale="ru",
            text="<p>Словарь показывает диапазон значений слова.</p>",
        )
        db.commit()

        context = REGISTRY["chapter_block"].build_context_with_db(db, second, course)
        assert "Словарь показывает диапазон" in context
        assert "<p>" not in context, "the neighbour is quoted as prose, not as markup to copy"

    def test_the_first_block_of_a_chapter_manages_without_one(self, db: Session) -> None:
        from app.models.chapter_block import ChapterBlock as Block

        orphan = Block(id=uuid.uuid4(), chapter_id="ch-nothing", block_type="text", order_index=0)
        context = REGISTRY["chapter_block"].build_context_with_db(db, orphan, None)
        assert context
        assert "Lesson block" in context
