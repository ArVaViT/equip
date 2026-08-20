# ruff: noqa: RUF001, RUF002
# Every string under test is a Cyrillic name next to another spelling of
# itself. That is the subject, not a typo.
"""A course should not spell a name four ways.

An editor read the whole current generation — 2,452 rows across de, en
and uk — and every terminology problem left in it was at a seam. One
Ukrainian lesson said «у Филиппах» in its objectives, «у Филипах» in the
heading below, «Филиппійська» in the body and «у Пилипах» in the
questions, and the last of those is the name of the apostle Philip
rather than of the city. «Коринф» ×7 stood against «Коринт-» ×8, once in
a single line.

None of it is a mistranslation. It is a pipeline in which every call is
the first call: the glossary holds forty school terms and can never hold
every proper noun in every course, and twin reuse only ever fires on
strings that are byte-for-byte identical, which «Филиппы» and «в
Филиппах» are not.

So the pass now carries a memory of what this course has already called
things (``translation/term_memory.py``). These are the properties that
make it worth having and the ones that make it safe to have.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import event

from app.models.course import Chapter, Course, CourseStatus, Module
from app.models.user import User
from app.services.content_versions.write import record_mt_version
from app.services.translation.course_pipeline import plan_course_tasks
from app.services.translation.executor import TranslationTask, _seed_memory, execute_plan
from app.services.translation.gemini import GeminiTranslationProvider
from app.services.translation.hash import compute_source_hash
from app.services.translation.prompt import build_user_prompt
from app.services.translation.protocol import TranslationRequest, TranslationResult
from app.services.translation.service import reset_translation_provider_cache
from app.services.translation.stores import LIVE_STORE, ActiveRow
from app.services.translation.term_memory import TermMemory, pair_names
from app.services.translation.version import TRANSLATOR_VERSION
from tests._cv_helpers import make_chapter_block_with_content

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

TEACHER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000c1")

# A paragraph that names the city twice over, and its Ukrainian
# rendering. Both readings of Philippi below are ones production
# actually produced.
RU_FIRST = "<p>Церковь в Филиппах была первой общиной в Европе.</p>"
UK_FIRST = "<p>Церква у Филіппах була першою громадою в Європі.</p>"
UK_FIRST_OTHER_WAY = "<p>Церква у Филипах була першою громадою в Європі.</p>"

# A different sentence, naming the same city. Not a twin of the first —
# a different string entirely, which is exactly why twin reuse cannot
# help and why the four spellings happened.
RU_SECOND = "<p>Обсудите, что произошло в Филиппах и почему это важно.</p>"


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


class _Recording:
    """Answers in Ukrainian and keeps every request it was handed."""

    name = "recording"

    def __init__(self, reply: str = "<p>Питання про місто та його громаду.</p>") -> None:
        self.seen: list[TranslationRequest] = []
        self._reply = reply

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.seen.append(request)
        return TranslationResult(text=self._reply, model="fake")

    def offered(self, text: str) -> tuple[tuple[str, str], ...]:
        """What the call translating ``text`` was told about names."""
        for request in self.seen:
            if request.text == text:
                return request.term_memory
        raise AssertionError(f"nothing was asked about {text!r}")


def _task(entity_id: str, *, text: str, target: str = "uk") -> TranslationTask:
    return TranslationTask(
        entity_type="chapter_block",
        entity_id=entity_id,
        field="content",
        source_locale="ru",
        target_locale=target,  # type: ignore[arg-type]
        text=text,
        content_kind="html",
        source_hash=compute_source_hash(text, locale="ru"),
    )


def _already_translated(db: Session, entity_id: str, *, source: str, into: str, locale: str = "uk") -> None:
    """Put a finished translation of ``source`` in the database.

    Made by the pipeline in force, because that is the only kind the
    memory is allowed to learn from — an older generation's wording is
    what a re-translation exists to replace.
    """
    record_mt_version(
        db,
        entity_type="chapter_block",
        entity_id=entity_id,
        field="content",
        locale=locale,
        text=into,
        source_locale="ru",
        source_hash=compute_source_hash(source, locale="ru"),
    )
    db.commit()


class TestWhatTheCourseAlreadyDecidedReachesTheNextField:
    def test_a_name_translated_once_is_offered_when_the_next_field_needs_it(self, db: Session) -> None:
        """The whole point. One block has already been rendered; the next
        block names the same city in a different sentence, and the call
        that translates it is told what the first one chose."""
        done, todo = str(uuid.uuid4()), str(uuid.uuid4())
        _already_translated(db, done, source=RU_FIRST, into=UK_FIRST)
        provider = _Recording()

        execute_plan(
            db,
            [_task(done, text=RU_FIRST), _task(todo, text=RU_SECOND)],
            provider=provider,
            store=LIVE_STORE,
        )

        assert [request.text for request in provider.seen] == [RU_SECOND], "the finished block is not re-asked"
        assert ("Филиппах", "Филіппах") in provider.offered(RU_SECOND)

    def test_a_lesson_learns_from_the_field_before_it_within_one_pass(self, db: Session) -> None:
        """Nothing is stored yet, and the second batch still benefits.

        A first-generation course has nothing to seed from, so the memory
        would be useless if it only ever read the database. It also
        learns from the pass's own answers — between batches, on the
        caller's thread, which is where every other write in this
        executor happens.
        """
        first, second = str(uuid.uuid4()), str(uuid.uuid4())
        provider = _Recording(reply=UK_FIRST)

        execute_plan(
            db,
            [_task(first, text=RU_FIRST), _task(second, text=RU_SECOND)],
            provider=provider,
            store=LIVE_STORE,
            max_workers=1,  # one call per batch, so the second can see the first
        )

        assert provider.offered(RU_FIRST) == (), "the first call has nothing to go on"
        assert ("Филиппах", "Филіппах") in provider.offered(RU_SECOND)


class TestACourseNobodyHasTranslatedIsAskedExactlyAsBefore:
    def test_an_empty_memory_offers_nothing(self, db: Session) -> None:
        """The property that makes this safe to ship: a first pass over a
        new course sends the prompt it has always sent."""
        provider = _Recording()

        execute_plan(
            db,
            [_task(str(uuid.uuid4()), text=RU_FIRST), _task(str(uuid.uuid4()), text=RU_SECOND)],
            provider=provider,
            store=LIVE_STORE,
        )

        assert provider.seen, "the plan ran"
        assert all(request.term_memory == () for request in provider.seen)

    def test_a_prompt_with_nothing_to_remember_is_the_prompt_it_always_was(self) -> None:
        without = build_user_prompt(
            text=RU_SECOND,
            content_kind="html",
            context=None,
            source_locale="ru",
            target_locale="uk",
        )
        assert "already used elsewhere in this course" not in without


class TestTheMemoryDoesNotLeak:
    def test_what_one_language_settled_is_not_offered_to_another(self, db: Session) -> None:
        """A Ukrainian reading says nothing about a German one, and a
        memory that mixed them would be handing the model a word in the
        wrong alphabet."""
        done, todo = str(uuid.uuid4()), str(uuid.uuid4())
        _already_translated(db, done, source=RU_FIRST, into=UK_FIRST, locale="uk")
        provider = _Recording()

        execute_plan(
            db,
            [
                _task(done, text=RU_FIRST, target="uk"),
                _task(todo, text=RU_SECOND, target="uk"),
                _task(todo, text=RU_SECOND, target="de"),
            ],
            provider=provider,
            store=LIVE_STORE,
        )

        by_locale = {request.target_locale: request.term_memory for request in provider.seen}
        assert ("Филиппах", "Филіппах") in by_locale["uk"]
        assert by_locale["de"] == ()

    def test_another_courses_wording_never_reaches_this_one(self, db: Session) -> None:
        """Two courses can disagree about a name and both be right — a
        history course and a Bible course need not spell a city the same
        way, and neither of them asked to inherit the other's choices.

        Scope is the plan, and a plan is one course's tree: the keys the
        seed reads come from the tasks themselves, so another course's
        rows are not outranked, they are never looked at.
        """
        elsewhere = _course_with_two_blocks(db, RU_FIRST, RU_SECOND)
        here = _course_with_two_blocks(db, RU_FIRST, RU_SECOND)
        for kind, entity in _blocks_of(db, elsewhere):
            assert kind == "chapter_block"
            _already_translated(db, str(entity.id), source=RU_FIRST, into=UK_FIRST)

        provider = _Recording()
        execute_plan(
            db,
            [task for task in plan_course_tasks(db, here) if task.target_locale == "uk"],
            provider=provider,
            store=LIVE_STORE,
            max_workers=8,
        )

        assert provider.seen, "the second course was translated"
        assert all(request.term_memory == () for request in provider.seen)


class TestAWrongMemoryCannotForceAnything:
    def test_a_course_that_says_it_both_ways_says_neither(self) -> None:
        """The answer to "what if the memory is stale". A reading that has
        been contradicted as often as it has been used is not evidence,
        and a coin toss between two spellings is the defect, not the fix.
        """
        memory = TermMemory()
        memory.learn(RU_FIRST, UK_FIRST, source_locale="ru", target_locale="uk")
        memory.learn(RU_FIRST, UK_FIRST_OTHER_WAY, source_locale="ru", target_locale="uk")

        assert memory.recall(RU_SECOND, target_locale="uk") == ()

    def test_the_reading_the_course_actually_uses_wins_the_argument(self) -> None:
        """Counting, not recency: one stray row does not overturn the rest
        of the course, and it does not need a human to say so."""
        memory = TermMemory()
        memory.learn(RU_FIRST, UK_FIRST, source_locale="ru", target_locale="uk")
        memory.learn(RU_FIRST, UK_FIRST_OTHER_WAY, source_locale="ru", target_locale="uk")
        memory.learn(RU_FIRST, UK_FIRST, source_locale="ru", target_locale="uk")

        assert memory.recall(RU_SECOND, target_locale="uk") == (("Филиппах", "Филіппах"),)

    def test_what_is_offered_says_in_words_that_it_may_be_ignored(self) -> None:
        """A hint that cannot be declined is how "New Testament" became
        "New Covenant" — the register check shipped a note saying "use our
        wording" and the model obeyed it into a wrong translation. So the
        block states the condition and the escape in as many words."""
        prompt = build_user_prompt(
            text=RU_SECOND,
            content_kind="html",
            context=None,
            source_locale="ru",
            target_locale="uk",
            term_memory=(("Филиппах", "Филіппах"),),
        )

        assert "Филиппах → Филіппах" in prompt
        assert "This is not a rule" in prompt
        assert "ignore the line and translate what is in front of you" in prompt

    def test_a_model_that_ignores_the_memory_is_recorded_as_it_answered(self, db: Session) -> None:
        """Nothing downstream rewrites the answer to match the memory. The
        preference is a sentence in a prompt and nowhere else — if it were
        a substitution, a stale entry would be unanswerable."""
        done, todo = str(uuid.uuid4()), str(uuid.uuid4())
        _already_translated(db, done, source=RU_FIRST, into=UK_FIRST)
        defiant = "<p>Питання про Пилипи та їхню громаду.</p>"
        provider = _Recording(reply=defiant)

        execute_plan(
            db,
            [_task(done, text=RU_FIRST), _task(todo, text=RU_SECOND)],
            provider=provider,
            store=LIVE_STORE,
        )

        stored = LIVE_STORE.active_row(db, entity_type="chapter_block", entity_id=todo, field="content", locale="uk")
        assert stored is not None
        assert stored.text == defiant

    def test_a_city_is_not_taught_to_answer_to_a_mans_name(self) -> None:
        """«Пилип» is the apostle Philip. Production translated the city
        of Philippi that way in one lesson's discussion questions, and a
        memory that believed it would have spread a man's name over a map
        for the rest of the course.

        Nothing here knows either name. The pairing refuses because two
        words that begin with different consonants are not inflections of
        each other — a rule about spelling, not about Acts.
        """
        assert pair_names(RU_FIRST, "<p>Церква у Пилипах була першою громадою в Європі.</p>") == [("Европе", "Європі")]


class TestALessonRemembersItsOwnParagraphs:
    """The seam the editor actually found was inside one lesson.

    A long HTML block is asked for a few paragraphs at a time
    (``translation/html_split``), and each piece is its own call — which
    is how a heading and the paragraph beneath it ended up spelling the
    same city differently. The document now carries what its earlier
    pieces settled on.
    """

    def test_the_second_paragraph_is_told_what_the_first_one_chose(self) -> None:
        prompts: list[str] = []
        pieces = [
            "<h2>Церковь в Филиппах</h2>",
            "<p>Обсудите, что произошло в Филиппах и почему это важно.</p>",
        ]
        answers = {
            pieces[0]: "<h2>Церква у Филіппах</h2>",
            pieces[1]: "<p>Обговоріть, що сталося та чому це важливо.</p>",
        }

        def handler(request: httpx.Request) -> httpx.Response:
            prompt = json.loads(request.content.decode())["contents"][0]["parts"][0]["text"]
            prompts.append(prompt)
            match = re.search(r"===BEGIN_[0-9a-f]+===\n(.*)\n===END_[0-9a-f]+===", prompt, re.DOTALL)
            assert match is not None
            return httpx.Response(
                200,
                json={"candidates": [{"content": {"parts": [{"text": answers[match.group(1)]}]}}]},
            )

        provider = GeminiTranslationProvider(
            api_key="fake-key",
            model="gemini-2.5-flash-lite",
            timeout_seconds=5.0,
            max_output_tokens=4096,
            max_retries=0,
            client=httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0),
        )
        request = TranslationRequest(
            text="".join(pieces),
            source_locale="ru",
            target_locale="uk",
            content_kind="html",
        )

        provider._translate_in_pieces(request, pieces, budget=None)

        assert "already used elsewhere in this course" not in prompts[0], "the first piece has nothing to go on"
        assert "Филиппах → Филіппах" in prompts[1]


class TestRememberingIsCheap:
    @pytest.fixture
    def counted(self, db: Session):
        seen: list[str] = []

        def before(conn, cursor, statement, parameters, context, executemany):
            seen.append(statement)

        event.listen(db.get_bind(), "before_cursor_execute", before)
        yield seen
        event.remove(db.get_bind(), "before_cursor_execute", before)

    def test_building_the_memory_asks_the_database_nothing(self, db: Session, counted: list[str]) -> None:
        """The bound, and the reason the design is shaped this way. The
        seed reads rows phase one has already fetched to decide what still
        needs asking, so it scales with the plan in memory and not in
        round trips — at any plan size, zero statements.
        """
        tasks = [_task(str(uuid.uuid4()), text=RU_FIRST) for _ in range(400)]
        existing = LIVE_STORE.active_rows(db, [(t.entity_type, t.entity_id, t.field, t.target_locale) for t in tasks])
        counted.clear()

        _seed_memory(TermMemory(), tasks, existing, generation=TRANSLATOR_VERSION)

        assert counted == []

    def test_carrying_the_text_did_not_turn_one_query_into_four_hundred(self, db: Session, counted: list[str]) -> None:
        """``active_rows`` now selects the translation as well as its
        status. One more column on a query that had to run anyway — the
        statement count is what it was."""
        keys = [("chapter_block", str(uuid.uuid4()), "content", "uk") for _ in range(400)]

        LIVE_STORE.active_rows(db, keys)

        assert len(counted) <= 2, f"{len(counted)} statements for 400 keys"

    def test_one_call_is_never_handed_more_than_a_handful_of_names(self) -> None:
        """Past a handful the block stops being a reminder and starts
        being a wall of vocabulary in front of the rules that matter."""
        memory = TermMemory()
        names = [f"Мариан{index:02d}" for index in range(40)]
        for name in names:
            memory.learn(
                f"Город {name} был важен.",
                f"Місто {name}ополь було важливим.",
                source_locale="ru",
                target_locale="uk",
            )
        crowded = "Города " + ", ".join(names) + " перечислены."

        assert len(memory.recall(crowded, target_locale="uk")) <= 8

    def test_seeding_a_catalogue_sized_plan_reads_a_bounded_sample(self, db: Session) -> None:
        """Reading one finished field costs about a millisecond, and a
        full-catalogue plan holds three thousand of them. Three seconds of
        a 180-second tick spent before the first call goes out is not a
        price worth paying for a course that stopped introducing names in
        module two — so the seed samples, evenly, and stops."""
        learned: list[str] = []

        class _Counting(TermMemory):
            def learn(self, source, translation, **kwargs):  # type: ignore[override]
                learned.append(source)
                super().learn(source, translation, **kwargs)

        memory = _Counting()
        tasks = [_task(str(uuid.uuid4()), text=f"<p>Церковь в Филиппах, дом {n}.</p>") for n in range(3000)]
        existing = {
            (t.entity_type, t.entity_id, t.field, t.target_locale): ActiveRow(
                origin="machine",
                status="ok",
                source_hash=t.source_hash,
                translator_version=TRANSLATOR_VERSION,
                text=UK_FIRST,
            )
            for t in tasks
        }

        _seed_memory(memory, tasks, existing, generation=TRANSLATOR_VERSION)

        assert len(learned) <= 300, f"{len(learned)} fields read to seed a 3,000-task plan"
        assert learned[0] != learned[-1], "the sample is spread across the plan, not taken off the front"

    def test_the_memory_itself_stops_growing(self) -> None:
        """A catalogue-wide pass must not be able to turn this into the
        thing that spends the worker."""
        memory = TermMemory()
        for index in range(900):
            memory.learn(
                f"Город Мариан{index:04d} был важен.",
                f"Місто Мариан{index:04d}ополь було важливим.",
                source_locale="ru",
                target_locale="uk",
            )

        assert memory.known_keys("uk") <= 500


def _course_with_two_blocks(db: Session, first: str, second: str) -> Course:
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="terms@example.com", full_name="T", role="teacher"))
        db.commit()
    course = Course(
        id=f"course-{uuid.uuid4().hex[:8]}",
        status=CourseStatus.PUBLISHED,
        source_locale="ru",
        created_by=TEACHER_ID,
        created_at=datetime.now(UTC),
    )
    db.add(course)
    db.flush()
    module = Module(id=f"mod-{uuid.uuid4().hex[:8]}", course_id=course.id, title="Модуль", order_index=0)
    db.add(module)
    db.flush()
    chapter = Chapter(id=f"ch-{uuid.uuid4().hex[:8]}", module_id=module.id, title="Глава", order_index=0)
    db.add(chapter)
    db.flush()
    for index, content in enumerate((first, second)):
        make_chapter_block_with_content(db, chapter_id=chapter.id, order_index=index, content=content, locale="ru")
    db.commit()
    return course


def _blocks_of(db: Session, course: Course):
    from app.services.translation.course_tree import iter_course_entities

    return [(kind, entity) for kind, entity in iter_course_entities(db, course) if kind == "chapter_block"]
