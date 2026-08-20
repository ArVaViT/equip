"""Two things concurrency quietly took away, and the tests that hold them.

Running the calls in parallel was worth six times the speed, and it
removed two guarantees the serial path had for free. Neither would have
raised an error; both would have shown up as a bill and as two quizzes
disagreeing about the same word.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.services.translation.executor import TranslationTask, execute_plan
from app.services.translation.protocol import TranslationError, TranslationResult
from app.services.translation.service import reset_translation_provider_cache
from app.services.translation.stores import LIVE_STORE

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


class _Counting:
    name = "counting"

    def __init__(self) -> None:
        self.texts: list[str] = []

    def translate(self, request):
        self.texts.append(request.text)
        return TranslationResult(text=f"Translated: {request.text}", model="fake")


class _Answering(_Counting):
    """A provider that answers in the target language, so the language
    check has nothing to object to and every call in ``texts`` is a
    question actually asked rather than a correction of a bad answer."""

    def __init__(self, answer: str) -> None:
        super().__init__()
        self._answer = answer

    def translate(self, request):
        self.texts.append(request.text)
        return TranslationResult(text=self._answer, model="fake")


def _task(
    entity_id: str,
    *,
    text: str,
    source_hash: str,
    context: str | None = None,
    content_kind: str = "quiz_option",
) -> TranslationTask:
    return TranslationTask(
        entity_type="quiz_option",
        entity_id=entity_id,
        field="option_text",
        source_locale="ru",
        target_locale="de",
        text=text,
        content_kind=content_kind,  # type: ignore[arg-type]
        source_hash=source_hash,
        context=context,
    )


def test_the_same_text_is_asked_for_once_however_many_rows_want_it(db: Session):
    """27% of the corpus is duplicate source text — answer options like
    "True" and "Yes" repeat across quizzes. Serially the first row was
    written and the twin lookup answered the rest for free. Run them
    concurrently and none of them is written yet, so the same string
    goes to the provider once per row: paid for repeatedly, and — since
    temperature 0 is not determinism — possibly worded differently each
    time, which is two quizzes disagreeing about the same word.
    """
    provider = _Counting()
    tasks = [_task(str(uuid.uuid4()), text="Верно", source_hash="same-hash") for _ in range(5)]

    result = execute_plan(db, tasks, provider=provider, store=LIVE_STORE)

    assert provider.texts == ["Верно"], "one call for five identical rows"
    assert result.translated == 5, "and every row still gets its translation"


def test_different_texts_are_still_asked_for_separately(db: Session):
    """The dedupe keys on the source hash, not on convenience."""
    provider = _Counting()
    tasks = [
        _task(str(uuid.uuid4()), text="Верно", source_hash="hash-a"),
        _task(str(uuid.uuid4()), text="Неверно", source_hash="hash-b"),
    ]

    execute_plan(db, tasks, provider=provider, store=LIVE_STORE)

    assert sorted(provider.texts) == ["Верно", "Неверно"]


def test_a_repeated_heading_is_one_string_however_different_its_surroundings(db: Session):
    """The defect this file exists to catch, in the form it actually took.

    «Проверьте себя» closes 23 lessons. It is its own field, so its
    context is the paragraph above it — and that paragraph is different
    in every lesson. With the context in the dedupe key, 23 identical
    strings became 23 groups, went to the provider 23 times, and came
    back as four different German headings. Nothing downstream objected,
    because each answer was individually correct.

    The recorded pipeline was never context-sensitive: ``_load_twins``
    reuses last week's heading by ``(source_hash, target_locale)``
    whatever stands above it today. One string, one translation — in
    flight as well as in the table.
    """
    # Answering in real German matters here: a fake answer that still
    # reads as Russian is caught by the language check and sent back for
    # correction, and the correcting call would be counted as a second
    # ask when it is nothing of the kind.
    provider = _Answering("Prüfe dich selbst")
    tasks = [
        _task(
            str(uuid.uuid4()),
            text="Проверьте себя",
            source_hash="heading-hash",
            context=f"Follows: lesson {i} said something entirely its own.",
        )
        for i in range(6)
    ]

    result = execute_plan(db, tasks, provider=provider, store=LIVE_STORE)

    assert provider.texts == ["Проверьте себя"], "asked once, not once per neighbour"
    assert result.translated == 6, "and all six headings are written"


def test_the_same_words_under_two_kinds_are_still_two_questions(db: Session):
    """Dropping the context from the key must not drop the content kind
    with it. A sentence sent as ``html`` is told to keep its markup; the
    same sentence sent as ``quiz_option`` is told not to grow into a
    paragraph. They are different questions and validation checks the
    answer under different rules, so they stay separate calls."""
    provider = _Answering("Richtig")
    tasks = [
        _task(str(uuid.uuid4()), text="Верно", source_hash="same-hash", content_kind="quiz_option"),
        _task(str(uuid.uuid4()), text="Верно", source_hash="same-hash", content_kind="title"),
    ]

    execute_plan(db, tasks, provider=provider, store=LIVE_STORE)

    assert provider.texts == ["Верно", "Верно"], "one call per kind, not one call in total"


def test_one_failing_row_does_not_take_the_plan_down(db: Session):
    """A provider error arrives on a worker thread now. If it escaped as
    something the caller does not catch, it would surface out of the
    pool and abandon every other row in the batch — a whole course
    stopped by one bad string."""

    class _OneBadApple:
        name = "flaky"

        def translate(self, request):
            if "плохой" in request.text:
                raise TranslationError("upstream said no")
            return TranslationResult(text=f"Translated: {request.text}", model="fake")

    tasks = [
        _task(str(uuid.uuid4()), text="хороший текст", source_hash="h1"),
        _task(str(uuid.uuid4()), text="плохой текст", source_hash="h2"),
        _task(str(uuid.uuid4()), text="ещё один хороший", source_hash="h3"),
    ]

    result = execute_plan(db, tasks, provider=_OneBadApple(), store=LIVE_STORE)

    # The plan returned at all — that is the property. The one bad row is
    # recorded as failed rather than raised out of the worker thread, and
    # the other two were both processed (the fake answers in English, so
    # the validator parks one of them; that is the validator working, not
    # the pool breaking).
    assert result.failed == 1, "the bad row is recorded, not raised"
    assert result.translated + result.needs_review == 2, "the other rows were still processed"
