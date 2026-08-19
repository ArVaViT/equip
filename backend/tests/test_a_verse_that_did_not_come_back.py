"""A citation with nothing behind it is worse than a rough translation.

The provider swaps a quoted verse for a ``VERSE_`` placeholder before
sending, and puts the canonical target-language text back afterwards.
When the model drops the placeholder there is nothing to restore into,
and the verse is simply gone — with the reference still sitting there,
so the result reads as complete.

Production had exactly that: an answer option whose source read
``Matthew 5:9 ('Blessed are the peacemakers, for they shall be called
sons of God.')`` came back as ``Matthäus 5,9``. Reference kept,
Scripture deleted, in the one place a student is being asked to
recognise the verse.

Structural validation could not see it. It compares the text *before*
substitution with the text *after* restoration, and neither of those
contains a marker — so as far as the checker was concerned nothing was
missing. Only the length heuristic noticed, and only because the string
was short enough for the ratio to look wrong.

So the provider reports it, and the executor treats it as blocking.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.services.translation.executor import TranslationTask, _ask
from app.services.translation.protocol import TranslationRequest, TranslationResult


class _Provider:
    """Answers once, and records what it was asked."""

    def __init__(self, *, lost_first: bool, lost_second: bool = False) -> None:
        self.requests: list[TranslationRequest] = []
        self._lost = [lost_first, lost_second]

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.requests.append(request)
        lost = self._lost[min(len(self.requests) - 1, len(self._lost) - 1)]
        return TranslationResult(
            text="Matthäus 5,9" if lost else "Matthäus 5,9 („Selig sind die Friedfertigen…“)",
            model="fake",
            lost_scripture=lost,
        )


@pytest.fixture
def task() -> TranslationTask:
    return TranslationTask(
        entity_type="quiz_option",
        entity_id="opt-1",
        field="option_text",
        source_locale="en",
        target_locale="de",
        text="Matthew 5:9 ('Blessed are the peacemakers, for they shall be called sons of God.')",
        content_kind="quiz_option",
        source_hash="hash-1",
    )


class TestADroppedVerseIsNotServed:
    def test_it_is_parked_for_review(self, task: TranslationTask) -> None:
        answer = _ask(task, _Provider(lost_first=True, lost_second=True))
        assert answer.issues_summary is not None
        assert "scripture_dropped" in answer.issues_summary

    def test_the_model_is_told_what_it_left_out(self, task: TranslationTask) -> None:
        provider = _Provider(lost_first=True, lost_second=True)
        _ask(task, provider)
        assert len(provider.requests) == 2, "a blocking defect earns one correcting pass"
        assert provider.requests[1].rewrite_notes, "the second ask must say what was wrong"
        assert any("VERSE_" in note for note in provider.requests[1].rewrite_notes)

    def test_a_corrected_second_answer_is_taken(self, task: TranslationTask) -> None:
        answer = _ask(task, _Provider(lost_first=True, lost_second=False))
        assert answer.issues_summary is None
        assert "Friedfertigen" in (answer.text or "")

    def test_a_verse_that_survives_is_left_alone(self, task: TranslationTask) -> None:
        provider = _Provider(lost_first=False)
        answer = _ask(task, provider)
        assert answer.issues_summary is None
        assert len(provider.requests) == 1, "nothing to correct, nothing to pay for"


class TestTheProviderReportsIt:
    def test_a_result_says_so_by_default_it_did_not_happen(self) -> None:
        assert TranslationResult(text="x", model="m").lost_scripture is False

    def test_the_flag_survives_being_copied(self) -> None:
        # The provider rebuilds the result after restoring verses; the
        # flag has to come through that rebuild.
        original = TranslationResult(text="x", model="m", lost_scripture=True)
        assert replace(original, text="y").lost_scripture is True
