"""A translator we cannot reach has said nothing about the text.

``CONTENT_VERSION_MAX_ATTEMPTS`` is a giving-up rule: five times the
model has been shown this sentence and five times what came back could
not be stored, so stop asking and stop paying. ``failed_permanent`` is
the state that stops it, and nothing in the pipeline retries a row in
it — only an admin resetting ``attempts`` by hand.

On 2026-08-20 the Gemini prepayment ran out in the middle of a
full-catalogue rebuild. Every call began returning 429. Eight minutes
later 174 rows had spent all five attempts and sat at
``failed_permanent`` — the pipeline's formal statement that those
sentences defeat translation. Nothing was wrong with any of them; the
credit card was.

So the pipeline now distinguishes the two things a failure can mean:

* **The provider could not answer.** 429, 5xx, a read timeout, a
  connection reset, an exhausted balance. ``TranslationUnavailable``.
  The failure is recorded — the row has to stay in front of the retry
  queue — and the attempt is not counted. No number of these reaches
  ``failed_permanent``.
* **The provider answered and the answer is unusable.** No candidates,
  a malformed candidate, an empty string, a refusal, a request the API
  rejected outright. ``TranslationError``, exactly as before: the
  attempt counts and the fifth one is terminal.

And a pass that has asked three times running without an answer stops
asking for the rest of the tick, rather than walking a whole catalogue
into the same wall once a minute.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import httpx
import pytest

from app.models.content_version import CONTENT_VERSION_MAX_ATTEMPTS, ContentVersion
from app.models.course import Course, CourseStatus
from app.models.staged_content_version import StagedContentVersion
from app.models.user import User
from app.services.translation.completeness import UNACTIONABLE_GAP_REASONS, completeness_of
from app.services.translation.executor import (
    _OUTAGE_STREAK_LIMIT,
    TranslationTask,
    execute_plan,
)
from app.services.translation.gemini import GeminiTranslationProvider
from app.services.translation.hash import compute_source_hash
from app.services.translation.protocol import (
    TranslationError,
    TranslationRequest,
    TranslationResult,
    TranslationUnavailable,
)
from app.services.translation.stores import LIVE_STORE, StagedStore

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

TEACHER_ID = uuid.UUID("00000000-0000-0000-0000-0000000004a9")


# --------------------------------------------------------------------
# What the provider says about itself
# --------------------------------------------------------------------


def _provider(client: httpx.Client) -> GeminiTranslationProvider:
    return GeminiTranslationProvider(
        api_key="k",
        model="gemini-flash-latest",
        timeout_seconds=1.0,
        max_output_tokens=256,
        max_retries=0,
        client=client,
    )


def _ask(provider: GeminiTranslationProvider) -> TranslationResult:
    return provider.translate(
        TranslationRequest(
            text="Etwa vier Jahrhunderte",
            source_locale="de",
            target_locale="ru",
            content_kind="plain",
        )
    )


class TestTheProviderSaysWhichKindOfFailureItIs:
    """Classification happens at the wire, because that is the only
    place that still knows. By the time a failure reaches the code that
    counts attempts it is one exception among thousands, and the status
    code is long gone."""

    @pytest.mark.parametrize("status_code", [408, 429, 500, 502, 503, 504, 599])
    def test_a_service_that_could_not_answer_is_not_a_text_that_cannot_be_translated(self, status_code: int) -> None:
        """429 is the one that emptied the balance in production; the
        rest are the same statement in other words. 599 is there on
        purpose: an unknown 5xx has to fall on the "service" side, never
        on the "content" side."""
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = httpx.Response(status_code=status_code, text="quota exhausted")
        with pytest.raises(TranslationUnavailable):
            _ask(_provider(client))

    @pytest.mark.parametrize("status_code", [401, 403, 404])
    def test_a_door_shut_on_our_account_is_not_the_texts_fault_either(self, status_code: int) -> None:
        """A rejected key, a disabled project, a model id that no longer
        exists. Every one is an operator's problem, and reading none of
        them as "this sentence defeats translation" is the point."""
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = httpx.Response(status_code=status_code, text="permission denied")
        with pytest.raises(TranslationUnavailable):
            _ask(_provider(client))

    def test_a_call_that_never_reached_gemini_is_not_the_texts_fault_either(self) -> None:
        """No status at all — a timeout, a reset, DNS. The failure the
        dashboard sees as ``status_code=0``."""
        client = MagicMock(spec=httpx.Client)
        client.post.side_effect = httpx.ConnectTimeout("no route")
        with pytest.raises(TranslationUnavailable):
            _ask(_provider(client))

    @pytest.mark.parametrize("status_code", [400, 413])
    def test_a_request_the_api_examined_and_rejected_is_about_the_request(self, status_code: int) -> None:
        """The other side of the line, and the reason the line is not
        simply "any non-200". A 400 or a 413 is the API having looked at
        this payload — a block past the token ceiling — and refusing it.
        That recurs on every retry, which is exactly what the attempt cap
        is for."""
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = httpx.Response(status_code=status_code, text="request too large")
        with pytest.raises(TranslationError) as raised:
            _ask(_provider(client))
        assert not isinstance(raised.value, TranslationUnavailable)

    def test_an_answer_that_came_back_unusable_is_the_texts_own_failure(self) -> None:
        """A 200 with nothing in it. The model was shown the text and
        produced something we cannot store — that is a real attempt and
        it must still be counted."""
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = httpx.Response(status_code=200, json={"candidates": []})
        with pytest.raises(TranslationError) as raised:
            _ask(_provider(client))
        assert not isinstance(raised.value, TranslationUnavailable)


# --------------------------------------------------------------------
# What a pass records, and what it declines to count
# --------------------------------------------------------------------


class _Unavailable:
    """The provider during the outage: never answers, always the same."""

    name = "unavailable"

    def __init__(self) -> None:
        self.calls = 0

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.calls += 1
        raise TranslationUnavailable("Gemini returned 429: RESOURCE_EXHAUSTED")


class _Unusable:
    """The provider answering badly: it is up, and what it says about
    this text cannot be stored."""

    name = "unusable"

    def __init__(self) -> None:
        self.calls = 0

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.calls += 1
        raise TranslationError("Gemini returned an empty translation")


def _task(entity_id: str, *, text: str = "Etwa vier Jahrhunderte") -> TranslationTask:
    return TranslationTask(
        entity_type="quiz_option",
        entity_id=entity_id,
        field="option_text",
        source_locale="de",
        target_locale="ru",
        text=text,
        content_kind="quiz_option",
        source_hash=compute_source_hash(text, locale="de"),
    )


def _row(db: Session, entity_id: str) -> ContentVersion:
    return (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_id == entity_id,
            ContentVersion.locale == "ru",
            ContentVersion.superseded_by.is_(None),
        )
        .one()
    )


class TestAnOutageDoesNotSpendTheRetryBudget:
    def test_an_outage_does_not_consume_the_retry_budget(self, db: Session) -> None:
        """One pass, one unreachable provider. The row exists — the
        retry queue reads rows, and a failure that left no trace would
        leave a first-ever translation with nothing to come back for —
        and the counter has not moved, because nothing was asked."""
        entity_id = str(uuid.uuid4())
        provider = _Unavailable()

        result = execute_plan(db, [_task(entity_id)], provider=provider, store=LIVE_STORE, max_workers=1)
        db.commit()

        assert provider.calls == 1
        assert result.failed == 1, "for every counter it is a field that did not get its text"
        row = _row(db, entity_id)
        assert row.status == "failed"
        assert row.attempts == 0, "the model was never shown the text, so nothing was attempted"

    def test_an_outage_never_produces_failed_permanent(self, db: Session) -> None:
        """Twice the cap, and then some. Five ticks of a hard 429 is
        what production actually did — eight minutes, 174 rows — and
        every one of them landed in a state only a person could undo."""
        entity_id = str(uuid.uuid4())
        provider = _Unavailable()

        for _ in range(CONTENT_VERSION_MAX_ATTEMPTS * 2):
            execute_plan(db, [_task(entity_id)], provider=provider, store=LIVE_STORE, max_workers=1)
            db.commit()

        row = _row(db, entity_id)
        assert row.status == "failed", "however long the outage, the row is still one the pipeline will retry"
        assert row.attempts == 0
        assert row.status != "failed_permanent"

    def test_an_answer_nobody_can_use_still_spends_an_attempt_and_still_becomes_permanent(self, db: Session) -> None:
        """The behaviour being protected, not removed. A text the model
        keeps answering badly is what the cap was written for, and it
        still arrives at the same place after the same five tries."""
        entity_id = str(uuid.uuid4())
        provider = _Unusable()

        for pass_number in range(1, CONTENT_VERSION_MAX_ATTEMPTS + 1):
            execute_plan(db, [_task(entity_id)], provider=provider, store=LIVE_STORE, max_workers=1)
            db.commit()
            assert _row(db, entity_id).attempts == pass_number

        row = _row(db, entity_id)
        assert row.attempts == CONTENT_VERSION_MAX_ATTEMPTS
        assert row.status == "failed_permanent"

    def test_the_retry_queue_still_finds_a_row_after_a_transient_failure(self, db: Session) -> None:
        """The thing that had to stay true.

        Not recording the failure at all would have been the tidy fix,
        and it is the one that makes a course quietly stop being
        translated. What the sweep reads is the row: it must be there,
        it must count as a gap, and the gap must be one the sweep will
        act on rather than one it steps over as waiting for a person.
        """
        entity_id = str(uuid.uuid4())
        execute_plan(db, [_task(entity_id)], provider=_Unavailable(), store=LIVE_STORE, max_workers=1)
        db.commit()

        completeness = completeness_of(db, {("quiz_option", entity_id, "option_text"): {"ru"}})
        assert not completeness.is_complete
        gap = completeness.gaps[0]
        # Which label the gap carries is not the point and is allowed to
        # move — after an outage the row is simply behind the pipeline in
        # force, so it reads as `stale`. What must hold is that the sweep
        # will act on it rather than step over it as something waiting
        # for a person.
        assert gap.reason not in UNACTIONABLE_GAP_REASONS, "a worker tick is exactly what closes this one"

    def test_the_very_next_pass_asks_again_once_the_provider_is_back(self, db: Session) -> None:
        """And it is asked again with a clean slate, so a service that
        was down for a day has cost the text none of its five tries."""
        entity_id = str(uuid.uuid4())
        execute_plan(db, [_task(entity_id)], provider=_Unavailable(), store=LIVE_STORE, max_workers=1)
        db.commit()

        class _Back:
            name = "back"

            def translate(self, request: TranslationRequest) -> TranslationResult:
                return TranslationResult(text="Около четырёх столетий", model="fake")

        result = execute_plan(db, [_task(entity_id)], provider=_Back(), store=LIVE_STORE, max_workers=1)
        db.commit()

        assert result.translated == 1
        row = _row(db, entity_id)
        assert row.status == "ok"
        assert row.text == "Около четырёх столетий"


class TestAnEditHeldForReleaseIsNotDefectiveEither:
    """The staged table counts attempts too, and a held edit whose
    locales all reach ``failed_permanent`` never releases at all."""

    def test_an_outage_does_not_spend_a_held_edits_attempts(self, db: Session) -> None:
        if db.get(User, TEACHER_ID) is None:
            db.add(User(id=TEACHER_ID, email="outage@example.com", full_name="T", role="teacher"))
            db.commit()
        course = Course(
            id=f"course-{uuid.uuid4().hex[:8]}",
            status=CourseStatus.PUBLISHED,
            source_locale="de",
            created_by=TEACHER_ID,
        )
        db.add(course)
        db.commit()

        entity_id = str(uuid.uuid4())
        store = StagedStore(str(course.id))
        for _ in range(CONTENT_VERSION_MAX_ATTEMPTS * 2):
            store.record_failure(
                db,
                entity_type="chapter_block",
                entity_id=entity_id,
                field="content",
                locale="ru",
                source_locale="de",
                source_hash="h1",
                transient=True,
            )
            db.commit()

        staged = (
            db.query(StagedContentVersion)
            .filter(
                StagedContentVersion.entity_id == entity_id,
                StagedContentVersion.locale == "ru",
            )
            .one()
        )
        assert staged.attempts == 0
        assert staged.status == "failed"

    def test_a_held_edit_the_model_keeps_failing_still_reaches_the_cap(self, db: Session) -> None:
        if db.get(User, TEACHER_ID) is None:
            db.add(User(id=TEACHER_ID, email="outage@example.com", full_name="T", role="teacher"))
            db.commit()
        course = Course(
            id=f"course-{uuid.uuid4().hex[:8]}",
            status=CourseStatus.PUBLISHED,
            source_locale="de",
            created_by=TEACHER_ID,
        )
        db.add(course)
        db.commit()

        entity_id = str(uuid.uuid4())
        store = StagedStore(str(course.id))
        for _ in range(CONTENT_VERSION_MAX_ATTEMPTS):
            store.record_failure(
                db,
                entity_type="chapter_block",
                entity_id=entity_id,
                field="content",
                locale="ru",
                source_locale="de",
                source_hash="h1",
            )
            db.commit()

        staged = (
            db.query(StagedContentVersion)
            .filter(
                StagedContentVersion.entity_id == entity_id,
                StagedContentVersion.locale == "ru",
            )
            .one()
        )
        assert staged.attempts == CONTENT_VERSION_MAX_ATTEMPTS
        assert staged.status == "failed_permanent"


# --------------------------------------------------------------------
# Not hammering a service that is down
# --------------------------------------------------------------------


class TestAPassStopsAskingWhenNobodyIsAnswering:
    def test_a_pass_stops_asking_once_the_provider_has_stopped_answering(self, db: Session) -> None:
        """The worker fires every minute and a full-catalogue plan is
        thousands of calls. Yesterday it sent all of them into a hard
        429, for hours. Three unanswered calls in a row is enough to
        conclude nobody is there — and the pass says so by coming back
        incomplete, which puts the job back in the queue for a fresh try
        in a minute rather than marking the course done with a hole in
        it."""
        tasks = [_task(str(uuid.uuid4()), text=f"Frage {n}") for n in range(30)]
        provider = _Unavailable()

        result = execute_plan(db, tasks, provider=provider, store=LIVE_STORE, max_workers=1)
        db.commit()

        assert provider.calls == _OUTAGE_STREAK_LIMIT, f"stopped asking after {provider.calls} unanswered calls"
        assert result.incomplete, "the pass did not finish; the job goes back to queued"
        assert result.failed == _OUTAGE_STREAK_LIMIT, "and only the rows it actually tried were touched"

    def test_a_provider_that_is_answering_badly_is_not_an_outage(self, db: Session) -> None:
        """The streak is about silence, not about failure. A model that
        keeps producing unusable text is up, is being paid, and is the
        case the attempt cap handles one row at a time — stopping the
        whole pass for it would leave the rest of the catalogue
        untranslated because of three bad sentences."""
        tasks = [_task(str(uuid.uuid4()), text=f"Frage {n}") for n in range(10)]
        provider = _Unusable()

        result = execute_plan(db, tasks, provider=provider, store=LIVE_STORE, max_workers=1)
        db.commit()

        assert provider.calls == 10
        assert not result.incomplete
        assert result.failed == 10

    def test_one_answer_in_between_means_the_service_is_still_there(self, db: Session) -> None:
        """A stray 429 under load is not an outage. The streak resets on
        any answer at all, so a pass through a flaky hour keeps
        working."""
        tasks = [_task(str(uuid.uuid4()), text=f"Frage {n}") for n in range(9)]

        class _Flaky:
            name = "flaky"

            def __init__(self) -> None:
                self.calls = 0

            def translate(self, request: TranslationRequest) -> TranslationResult:
                self.calls += 1
                if self.calls % 3:
                    raise TranslationUnavailable("Gemini returned 429: RESOURCE_EXHAUSTED")
                return TranslationResult(text="Ответ", model="fake")

        provider = _Flaky()
        result = execute_plan(db, tasks, provider=provider, store=LIVE_STORE, max_workers=1)
        db.commit()

        assert provider.calls == 9, "never two unanswered in a row for long enough to look like an outage"
        assert not result.incomplete
        assert result.translated == 3
