"""Two options that say the same thing make a question unanswerable.

Nothing is wrong with either string. Both are fluent, both are correctly
punctuated, both say something true — and between them they destroy the
question, because a student choosing "Malta" from four options that all
read "Malta" cannot be right or wrong.

It was introduced by an improvement. Telling the model what question an
option answers fixed the grammar (options that did not read with their
stem) and broke the content: helpfully, it repaired the wrong answers.
Measured across the corpus, 22 questions came back with duplicated
options — four English options reading "Malta", three reading "John",
a German set where three of four were the same city. The Russian source
has no duplicate options anywhere in 128 questions, so every collision
was made in translation.

The prompt now says twice that a wrong answer is wrong on purpose, and
that held in every case re-measured. This file pins the check behind the
instruction, because an instruction is a hope.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from app.models.course import Chapter, Course, CourseStatus, Module
from app.models.quiz import Quiz, QuizOption, QuizQuestion
from app.models.user import User
from app.services.content_versions import record_human_version, record_mt_version
from app.services.translation.executor import TranslationTask, _colliding_sibling
from app.services.translation.hash import compute_source_hash

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

TEACHER_ID = uuid.UUID("00000000-0000-0000-0000-00000000ce22")


@pytest.fixture
def two_options(db: Session) -> tuple[QuizOption, QuizOption]:
    """One question, two options, the first already translated."""
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="quiz@example.com", full_name="T", role="teacher"))
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
    right = QuizOption(id=uuid.uuid4(), question_id=question.id, order_index=0, is_correct=True)
    wrong = QuizOption(id=uuid.uuid4(), question_id=question.id, order_index=1, is_correct=False)
    db.add_all([right, wrong])
    db.commit()

    for option, text in ((right, "Мальта"), (wrong, "Крит")):
        record_human_version(
            db,
            entity_type="quiz_option",
            entity_id=str(option.id),
            field="option_text",
            locale="ru",
            text=text,
        )
    record_mt_version(
        db,
        entity_type="quiz_option",
        entity_id=str(right.id),
        field="option_text",
        locale="en",
        text="Malta",
        source_locale="ru",
        source_hash=compute_source_hash("Мальта", locale="ru"),
    )
    db.commit()
    return right, wrong


def _task(option: QuizOption) -> TranslationTask:
    return TranslationTask(
        entity_type="quiz_option",
        entity_id=str(option.id),
        field="option_text",
        source_locale="ru",
        target_locale="en",
        text="Крит",
        content_kind="quiz_option",
        source_hash="h",
    )


class TestAnOptionThatBecameItsNeighbour:
    def test_a_collision_is_caught(self, db: Session, two_options) -> None:
        _right, wrong = two_options
        assert _colliding_sibling(db, _task(wrong), "Malta") is not None

    def test_case_and_spacing_do_not_hide_it(self, db: Session, two_options) -> None:
        # "malta" and "Malta " are the same answer to a student.
        _right, wrong = two_options
        assert _colliding_sibling(db, _task(wrong), "  malta ") is not None

    def test_a_genuinely_different_option_passes(self, db: Session, two_options) -> None:
        _right, wrong = two_options
        assert _colliding_sibling(db, _task(wrong), "Crete") is None

    def test_another_language_is_not_a_collision(self, db: Session, two_options) -> None:
        # The German set is judged against German, not against English.
        _right, wrong = two_options
        german = _task(wrong)
        german = (
            TranslationTask(**{**german._asdict(), "target_locale": "de"}) if hasattr(german, "_asdict") else german
        )
        from dataclasses import replace

        assert _colliding_sibling(db, replace(_task(wrong), target_locale="de"), "Malta") is None

    def test_a_lone_option_has_nothing_to_collide_with(self, db: Session) -> None:
        orphan = QuizOption(id=uuid.uuid4(), question_id=uuid.uuid4(), order_index=0, is_correct=True)
        assert _colliding_sibling(db, _task(orphan), "Malta") is None

    def test_nothing_but_options_is_checked(self, db: Session, two_options) -> None:
        # A lesson block repeating a sentence from another block is
        # ordinary prose, not a broken question.
        from dataclasses import replace

        _right, wrong = two_options
        block = replace(_task(wrong), entity_type="chapter_block", field="content")
        assert _colliding_sibling(db, block, "Malta") is None


class TestARebuildDoesNotFightItself:
    """Half-new, half-old is the state a rebuild spends its time in.

    Options are replaced one at a time, so for a while a question's set
    is part new and part last generation — and last generation's half is
    exactly the broken one this check was written to catch. Comparing
    against it parks the correct new translation for matching a wrong old
    one. Thirteen good German options were held back that way during the
    generation-8 rebuild, which is the check turning on the fix.

    That was first expressed as "only siblings made by the pipeline now
    in force", and it held for about a week — for exactly as long as the
    corpus was behind the constant. A sibling written by an earlier pass
    at the *same* generation passes that test, and a pass that is about
    to rewrite it parks a correct translation against it anyway; nine
    rows in production are parked that way. So the question is no longer
    about generations at all. It is "is this sibling settled, or is this
    same pass about to replace it?", which the pass can answer exactly,
    out of its own plan.
    """

    def test_a_sibling_this_pass_is_about_to_rewrite_is_not_a_collision(self, db: Session, two_options) -> None:
        right, wrong = two_options

        assert (
            _colliding_sibling(
                db,
                _task(wrong),
                "Malta",
                unsettled={("quiz_option", str(right.id), "option_text", "en")},
            )
            is None
        )

    def test_a_sibling_the_pass_has_already_rewritten_still_is(self, db: Session, two_options) -> None:
        # It left the pending set when its row was written, so it is
        # what a reader sees — and a duplicate of it is unanswerable.
        _right, wrong = two_options

        assert _colliding_sibling(db, _task(wrong), "Malta", unsettled=set()) is not None

    def test_a_sibling_no_pass_is_holding_counts_however_old_it_is(self, db: Session, two_options) -> None:
        """Generation does not decide this any more, and should not.

        An option translated three generations ago that nobody is
        rebuilding right now is still the text on the page. A new option
        that comes back word for word identical to it makes the question
        unanswerable today, whatever pipeline wrote the other one.
        """
        from app.models.content_version import ContentVersion
        from app.services.translation.version import TRANSLATOR_VERSION

        right, wrong = two_options
        db.query(ContentVersion).filter(
            ContentVersion.entity_id == str(right.id),
            ContentVersion.origin == "mt",
        ).update({"translator_version": TRANSLATOR_VERSION - 3})
        db.commit()

        assert _colliding_sibling(db, _task(wrong), "Malta") is not None

    def test_a_hand_translation_counts_whatever_its_version(self, db: Session, two_options) -> None:
        # Nothing rewrites a human row, so it is never in a plan and
        # never pending — it counts without needing a rule of its own.
        from app.models.content_version import ContentVersion
        from app.services.translation.version import TRANSLATOR_VERSION

        right, wrong = two_options
        db.query(ContentVersion).filter(
            ContentVersion.entity_id == str(right.id),
            ContentVersion.origin == "mt",
        ).update({"origin": "human", "translator_version": TRANSLATOR_VERSION - 3})
        db.commit()

        assert _colliding_sibling(db, _task(wrong), "Malta") is not None
