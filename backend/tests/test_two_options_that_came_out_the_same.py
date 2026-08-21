"""A collision is something the model can fix, if anybody tells it.

The check that catches two options of one question saying the same thing
was right to be written and is right to stay: a student shown the same
answer twice cannot be right or wrong, and that is worse than any clumsy
sentence. What it did next was the gap. It parked the row for a person
and never said a word to the translator — which is the one participant
that could have fixed it, and the pipeline already knows how to talk to
it: ``_review_and_correct`` sends an objection back as ``rewrite_notes``
and asks again.

Measured in production on 2026-08-21, three rows in the whole catalogue,
all at the current generation, all waiting for a human:

    daily_challenge_option, uk:  "Understand it"  -> «Зрозумійте це»
    daily_challenge_option, uk:  "Comprehend it"  -> «Зрозумійте це»
    daily_challenge_option, de:  "Understand it"  -> «Verstehe es»

Ukrainian separates those two English options without difficulty. The
model was never told there was anything to separate — and asked the same
day with the note, it answers «Осягніть це», «Усвідомте це», «Begreife
es», «Erfasse es». Twelve of fourteen live asks came back distinct; two
came back the same string again, and those are the reason nothing here
removes the park.

So the collision now goes back as a note, once. The note names the
constraint — these two are the same string, their sources are not, keep
them apart — and never a word to use: this file cannot translate into
Ukrainian and the model would take a suggestion whether or not it was
the better rendering. One ask, and a collision that survives it parks
exactly as it always did.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.content_version import ContentVersion
from app.models.course import Chapter, Course, CourseStatus, Module
from app.models.daily_challenge import DailyChallengeOption, DailyChallengeQuestion
from app.models.quiz import Quiz, QuizOption, QuizQuestion
from app.models.user import User
from app.services.content_versions import record_human_version
from app.services.translation.executor import TranslationTask, execute_plan
from app.services.translation.hash import compute_source_hash
from app.services.translation.protocol import TranslationResult
from app.services.translation.service import reset_translation_provider_cache
from app.services.translation.stores import LIVE_STORE

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

TEACHER_ID = uuid.UUID("00000000-0000-0000-0000-0000000c0111")


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


class _Translator:
    """Answers from a table, and can answer differently once it is told
    what was wrong with the answer it gave.

    ``corrections`` is keyed the same way as ``answers`` and is used only
    for a request that carries ``rewrite_notes``. A source missing from
    it answers the same thing again, which is what a model at
    temperature 0 does when the question has not changed.
    """

    name = "collision-fake"

    def __init__(self, answers: dict[str, str], corrections: dict[str, str] | None = None) -> None:
        self._answers = answers
        self._corrections = corrections or {}
        self.requests: list[object] = []

    def translate(self, request):
        self.requests.append(request)
        if request.rewrite_notes and request.text in self._corrections:
            return TranslationResult(text=self._corrections[request.text], model="fake")
        return TranslationResult(text=self._answers[request.text], model="fake")

    @property
    def notes(self) -> list[str]:
        return [note for request in self.requests for note in request.rewrite_notes]  # type: ignore[attr-defined]


def _quiz_task(entity_id: str, *, text: str) -> TranslationTask:
    return TranslationTask(
        entity_type="quiz_option",
        entity_id=entity_id,
        field="option_text",
        source_locale="ru",
        target_locale="en",
        text=text,
        content_kind="quiz_option",
        source_hash=compute_source_hash(text, locale="ru"),
    )


def _daily_task(entity_id: str, *, text: str) -> TranslationTask:
    return TranslationTask(
        entity_type="daily_challenge_option",
        entity_id=entity_id,
        field="option_text",
        source_locale="en",
        target_locale="uk",
        text=text,
        content_kind="quiz_option",
        source_hash=compute_source_hash(text, locale="en"),
    )


def _row(db: Session, entity_id: str, locale: str) -> ContentVersion:
    return (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_id == entity_id,
            ContentVersion.locale == locale,
            ContentVersion.superseded_by.is_(None),
        )
        .one()
    )


@pytest.fixture
def two_quiz_options(db: Session):
    """One quiz question, two options, both with their Russian written."""
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="collision@example.com", full_name="T", role="teacher"))
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

    def _write(option: QuizOption, text: str) -> None:
        record_human_version(
            db,
            entity_type="quiz_option",
            entity_id=str(option.id),
            field="option_text",
            locale="ru",
            text=text,
        )

    _write(right, "Мальта")
    _write(wrong, "Крит")
    db.commit()
    return right, wrong


@pytest.fixture
def the_production_pair(db: Session):
    """The daily-challenge question the three parked rows came from.

    Two English options that mean nearly the same thing and are not the
    same option: the source is what a student is asked to tell apart, and
    the translation stopped telling them apart.
    """
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="collision@example.com", full_name="T", role="admin"))
        db.commit()
    question = DailyChallengeQuestion(
        id=uuid.uuid4(),
        question_type="multiple_choice",
        status="published",
        bible_book="Acts",
        bible_chapter=8,
        category="passage_exegesis",
        source_locale="en",
        created_by=TEACHER_ID,
    )
    db.add(question)
    db.flush()
    first = DailyChallengeOption(id=uuid.uuid4(), question_id=question.id, order_index=0, is_correct=True)
    second = DailyChallengeOption(id=uuid.uuid4(), question_id=question.id, order_index=1, is_correct=False)
    db.add_all([first, second])
    db.commit()

    for option, text in ((first, "Understand it"), (second, "Comprehend it")):
        record_human_version(
            db,
            entity_type="daily_challenge_option",
            entity_id=str(option.id),
            field="option_text",
            locale="en",
            text=text,
        )
    db.commit()
    return first, second


class TestTheTranslatorIsToldWhatWentWrong:
    def test_a_collision_is_sent_back_to_the_translator_as_a_note(self, db: Session, two_quiz_options) -> None:
        """The whole of the change, in one assertion.

        Both options come back "Malta". Before, the second was parked
        without anybody being asked anything; now the model is asked
        again, and asked with the reason.
        """
        right, wrong = two_quiz_options
        provider = _Translator({"Мальта": "Malta", "Крит": "Malta"})

        execute_plan(
            db,
            [_quiz_task(str(right.id), text="Мальта"), _quiz_task(str(wrong.id), text="Крит")],
            provider=provider,
            store=LIVE_STORE,
            max_workers=1,
        )
        db.commit()

        assert any("option_collision" in note for note in provider.notes), (
            "the collision must reach the translator, not only the review queue"
        )

    def test_the_note_names_the_two_sources_and_the_wording_to_differ_from(self, db: Session, two_quiz_options) -> None:
        """A note that does not say what to be unlike cannot be acted on.

        Three facts, and no fourth: the string that is now shared, and
        the two sources that are not the same and are the reason the
        renderings must not be either.
        """
        right, wrong = two_quiz_options
        provider = _Translator({"Мальта": "Malta", "Крит": "Malta"})

        execute_plan(
            db,
            [_quiz_task(str(right.id), text="Мальта"), _quiz_task(str(wrong.id), text="Крит")],
            provider=provider,
            store=LIVE_STORE,
            max_workers=1,
        )
        db.commit()

        note = next(note for note in provider.notes if "option_collision" in note)
        assert "Malta" in note, "the wording to differ from"
        assert "Крит" in note, "what this option says"
        assert "Мальта" in note, "what the other option says"


class TestACorrectionThatKeepsTheDistinctionIsKept:
    def test_a_rendering_that_no_longer_collides_is_written(self, db: Session, two_quiz_options) -> None:
        right, wrong = two_quiz_options
        provider = _Translator({"Мальта": "Malta", "Крит": "Malta"}, corrections={"Крит": "Crete"})

        result = execute_plan(
            db,
            [_quiz_task(str(right.id), text="Мальта"), _quiz_task(str(wrong.id), text="Крит")],
            provider=provider,
            store=LIVE_STORE,
            max_workers=1,
        )
        db.commit()

        assert _row(db, str(wrong.id), "en").text == "Crete"
        assert _row(db, str(right.id), "en").text == "Malta", "the option already on the page does not move"
        assert result.needs_review == 0
        assert result.translated == 2

    def test_a_corrected_option_is_served_rather_than_parked(self, db: Session, two_quiz_options) -> None:
        """Nobody is asked to look at a row that came back fixed."""
        right, wrong = two_quiz_options
        provider = _Translator({"Мальта": "Malta", "Крит": "Malta"}, corrections={"Крит": "Crete"})

        execute_plan(
            db,
            [_quiz_task(str(right.id), text="Мальта"), _quiz_task(str(wrong.id), text="Крит")],
            provider=provider,
            store=LIVE_STORE,
            max_workers=1,
        )
        db.commit()

        row = _row(db, str(wrong.id), "en")
        assert row.status == "ok", f"parked for {row.review_reason!r}"
        assert row.review_reason is None


class TestACollisionThatSurvivesStillParks:
    def test_a_correction_that_still_collides_parks_exactly_as_before(self, db: Session, two_quiz_options) -> None:
        """Going quiet would be worse than parking.

        The model was told and gave the same answer again. Two identical
        options in a live quiz is the defect this check exists to catch,
        so the row goes to a person with the reason it always carried.
        """
        right, wrong = two_quiz_options
        provider = _Translator({"Мальта": "Malta", "Крит": "Malta"}, corrections={"Крит": "Malta"})

        result = execute_plan(
            db,
            [_quiz_task(str(right.id), text="Мальта"), _quiz_task(str(wrong.id), text="Крит")],
            provider=provider,
            store=LIVE_STORE,
            max_workers=1,
        )
        db.commit()

        parked = _row(db, str(wrong.id), "en")
        assert parked.status == "needs_review"
        assert "option_collision" in (parked.review_reason or "")
        assert result.needs_review == 1

    def test_an_answer_that_only_looks_different_does_not_replace_the_first(
        self, db: Session, two_quiz_options
    ) -> None:
        """Case and spacing are not a distinction a student can see, so
        the second answer is the same answer and does not win the row."""
        right, wrong = two_quiz_options
        provider = _Translator({"Мальта": "Malta", "Крит": "Malta"}, corrections={"Крит": "  malta "})

        execute_plan(
            db,
            [_quiz_task(str(right.id), text="Мальта"), _quiz_task(str(wrong.id), text="Крит")],
            provider=provider,
            store=LIVE_STORE,
            max_workers=1,
        )
        db.commit()

        parked = _row(db, str(wrong.id), "en")
        assert parked.text == "Malta", "the answer that gave in must not be preferred"
        assert parked.status == "needs_review"

    def test_a_correction_that_stopped_colliding_by_breaking_something_else_loses(
        self, db: Session, two_quiz_options
    ) -> None:
        """An empty option collides with nothing and answers nothing.

        This is the case ``_rank`` decides: the collision is handed to it
        as the blocking issue it is, so an answer that traded it for
        another blocking defect cannot win by having escaped this one.
        """
        right, wrong = two_quiz_options
        provider = _Translator({"Мальта": "Malta", "Крит": "Malta"}, corrections={"Крит": ""})

        execute_plan(
            db,
            [_quiz_task(str(right.id), text="Мальта"), _quiz_task(str(wrong.id), text="Крит")],
            provider=provider,
            store=LIVE_STORE,
            max_workers=1,
        )
        db.commit()

        parked = _row(db, str(wrong.id), "en")
        assert parked.text == "Malta"
        assert parked.status == "needs_review"
        assert "option_collision" in (parked.review_reason or "")


class TestTheAskIsAskedOnce:
    def test_the_translator_is_asked_once_and_then_a_person_is(self, db: Session, two_quiz_options) -> None:
        """The same bound ``_review_and_correct`` keeps, for the same
        reason: a loop that runs until two strings differ can be handed a
        question that will never make them differ."""
        right, wrong = two_quiz_options
        provider = _Translator({"Мальта": "Malta", "Крит": "Malta"}, corrections={"Крит": "Malta"})

        execute_plan(
            db,
            [_quiz_task(str(right.id), text="Мальта"), _quiz_task(str(wrong.id), text="Крит")],
            provider=provider,
            store=LIVE_STORE,
            max_workers=1,
        )
        db.commit()

        collision_asks = [note for note in provider.notes if "option_collision" in note]
        assert len(collision_asks) == 1, f"one correction, not {len(collision_asks)}"
        assert len(provider.requests) == 3, "two options asked, one of them asked again"

    def test_a_source_that_lists_the_same_answer_twice_is_not_argued_with(self, db: Session) -> None:
        """Two options whose Russian is identical are one option twice.

        No rendering can make them differ without saying something the
        source does not say, so the row parks without a call being spent
        on it — and the reason it needs a person is upstream of anything
        a translator could do.
        """
        if db.get(User, TEACHER_ID) is None:
            db.add(User(id=TEACHER_ID, email="collision@example.com", full_name="T", role="teacher"))
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
        first = QuizOption(id=uuid.uuid4(), question_id=question.id, order_index=0, is_correct=True)
        second = QuizOption(id=uuid.uuid4(), question_id=question.id, order_index=1, is_correct=False)
        db.add_all([first, second])
        db.commit()
        for option in (first, second):
            record_human_version(
                db,
                entity_type="quiz_option",
                entity_id=str(option.id),
                field="option_text",
                locale="ru",
                text="Мальта",
            )
        db.commit()

        provider = _Translator({"Мальта": "Malta"})
        result = execute_plan(
            db,
            [_quiz_task(str(first.id), text="Мальта"), _quiz_task(str(second.id), text="Мальта")],
            provider=provider,
            store=LIVE_STORE,
            max_workers=1,
        )
        db.commit()

        assert provider.notes == [], "nothing to say to the translator about a source that repeats itself"
        assert len(provider.requests) == 1, "one distinct source, one call"
        assert result.needs_review == 1
        assert "option_collision" in (_row(db, str(second.id), "en").review_reason or "")

    def test_a_row_already_going_to_a_person_is_not_asked_again(self, db: Session, two_quiz_options) -> None:
        """A row parked for a structural defect is parked either way.

        Both sources carry a placeholder and both answers drop it, so
        both rows fail validation and collide. The validation retry is
        the correction this row gets; spending a second call on the
        collision buys a person nothing.
        """
        right, wrong = two_quiz_options
        for option, text in ((right, "Мальта [[1]]"), (wrong, "Крит [[1]]")):
            record_human_version(
                db,
                entity_type="quiz_option",
                entity_id=str(option.id),
                field="option_text",
                locale="ru",
                text=text,
            )
        db.commit()

        provider = _Translator({"Мальта [[1]]": "Malta", "Крит [[1]]": "Malta"})
        execute_plan(
            db,
            [_quiz_task(str(right.id), text="Мальта [[1]]"), _quiz_task(str(wrong.id), text="Крит [[1]]")],
            provider=provider,
            store=LIVE_STORE,
            max_workers=1,
        )
        db.commit()

        assert not any("option_collision" in note for note in provider.notes)
        assert _row(db, str(wrong.id), "en").status == "needs_review"


class TestTheDailyChallengeIsTheSamePath:
    """The three parked rows are daily-challenge options, and the check
    has always covered both kinds. So does the ask."""

    def test_the_production_pair_is_sent_back_with_a_note(self, db: Session, the_production_pair) -> None:
        first, second = the_production_pair
        provider = _Translator({"Understand it": "Зрозумійте це", "Comprehend it": "Зрозумійте це"})

        execute_plan(
            db,
            [
                _daily_task(str(first.id), text="Understand it"),
                _daily_task(str(second.id), text="Comprehend it"),
            ],
            provider=provider,
            store=LIVE_STORE,
            max_workers=1,
        )
        db.commit()

        note = next(note for note in provider.notes if "option_collision" in note)
        assert "Зрозумійте це" in note
        assert "Comprehend it" in note
        assert "Understand it" in note

    def test_a_daily_challenge_option_that_comes_back_distinct_is_kept(self, db: Session, the_production_pair) -> None:
        first, second = the_production_pair
        provider = _Translator(
            {"Understand it": "Зрозумійте це", "Comprehend it": "Зрозумійте це"},
            corrections={"Comprehend it": "Осягніть це"},
        )

        result = execute_plan(
            db,
            [
                _daily_task(str(first.id), text="Understand it"),
                _daily_task(str(second.id), text="Comprehend it"),
            ],
            provider=provider,
            store=LIVE_STORE,
            max_workers=1,
        )
        db.commit()

        assert _row(db, str(first.id), "uk").text == "Зрозумійте це"
        assert _row(db, str(second.id), "uk").text == "Осягніть це"
        assert result.needs_review == 0
