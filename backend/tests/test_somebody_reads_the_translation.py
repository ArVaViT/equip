"""The pipeline finally reads what it wrote.

Every check in `validation.py` asks whether the shape survived: markup,
placeholders, numbers, length, language. None of them reads the
sentence, which is how a passage calling the Ethiopian eunuch of Acts 8
a Pentecostal sat in production marked ok — nothing was malformed.

So a second model reads the source and the answer together and objects
the way an editor would, and its notes go back through the correction
loop the structural checks already use. Bounded on purpose: one review,
one correction, one re-review, then a person. A loop that runs until a
reviewer is satisfied spends the budget arguing about synonyms.

The rule that matters most is the last class below: a reviewer that
cannot be reached, cannot be parsed, or rejects without saying why has
NO OPINION, and no opinion changes nothing. This layer can only raise
the floor. It must never become a new way for the pipeline to fail.
"""

from __future__ import annotations

import pytest

from app.services.translation.executor import TranslationTask, _ask
from app.services.translation.protocol import TranslationRequest, TranslationResult
from app.services.translation.reviewer import ReviewVerdict, parse_review


class _Provider:
    """Translates predictably; reviews however the test says."""

    def __init__(self, *, verdicts: list[ReviewVerdict], answers: list[str] | None = None) -> None:
        self.requests: list[TranslationRequest] = []
        self.reviewed: list[str] = []
        self._verdicts = verdicts
        self._answers = answers or []

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.requests.append(request)
        index = len(self.requests) - 1
        text = self._answers[index] if index < len(self._answers) else "Er kam früh am Morgen"
        return TranslationResult(text=text, model="fake")

    def review(self, *, source, translation, source_locale, target_locale, content_kind, context=None):
        self.reviewed.append(translation)
        index = len(self.reviewed) - 1
        return self._verdicts[min(index, len(self._verdicts) - 1)]


@pytest.fixture
def task() -> TranslationTask:
    return TranslationTask(
        entity_type="chapter_block",
        entity_id="b1",
        field="content",
        source_locale="ru",
        target_locale="de",
        # No glossary term in the source, so these tests measure the
        # reviewer and nothing else. The register no longer stands in
        # front of it either — see TestANoteTheModelHasAlreadyHeard.
        text="Он пришёл рано утром",
        content_kind="plain",
        source_hash="h",
    )


class TestAnAcceptedTranslationCostsNothingExtra:
    def test_no_correction_is_asked_for(self, task: TranslationTask) -> None:
        provider = _Provider(verdicts=[ReviewVerdict()])
        answer = _ask(task, provider)
        assert answer.issues_summary is None
        assert len(provider.requests) == 1, "one translation, no rewrite"
        assert len(provider.reviewed) == 1, "one review, no second opinion"


class TestAnObjectionBecomesACorrection:
    def test_the_notes_are_sent_back(self, task: TranslationTask) -> None:
        provider = _Provider(
            verdicts=[ReviewVerdict(acceptable=False, notes=("Too formal for this register.",)), ReviewVerdict()],
            answers=["Er kam am frühen Morgen", "Er kam früh am Morgen"],
        )
        answer = _ask(task, provider)
        assert len(provider.requests) == 2
        assert provider.requests[1].rewrite_notes == ("Too formal for this register.",)
        assert answer.text == "Er kam früh am Morgen"
        assert answer.issues_summary is None

    def test_a_correction_the_reviewer_still_rejects_is_still_served(self, task: TranslationTask) -> None:
        # An editor's second thoughts are not worth a blank page to a
        # student. The corrected text goes out, the objection is logged
        # under a stable code so the rate is countable, and the row is
        # NOT parked: a reviewer is an opinion, not a structural fact,
        # and parking on opinion would put the catalogue in front of a
        # person — which is the situation this pipeline exists to end.
        objection = ReviewVerdict(acceptable=False, notes=("Still reads as a translation.",))
        provider = _Provider(
            verdicts=[objection, objection], answers=["Er kam am frühen Morgen", "Er kam sehr früh am Morgen"]
        )
        answer = _ask(task, provider)
        assert answer.text == "Er kam sehr früh am Morgen", "the corrected answer is served"
        assert answer.issues_summary is None, "an opinion does not park a row"
        assert len(provider.reviewed) == 2, "read, corrected, read again — and no further"

    def test_review_objections_never_block_publication(self, task: TranslationTask) -> None:
        objection = ReviewVerdict(acceptable=False, notes=("Register is a little formal.",))
        provider = _Provider(verdicts=[objection, objection])
        answer = _ask(task, provider)
        # Recorded as a note, not as a reason to withhold the page.
        assert answer.failed is False
        assert answer.text is not None


class TestSilenceIsNotAnOpinion:
    def test_a_provider_that_cannot_review_is_left_alone(self, task: TranslationTask) -> None:
        class _NoReviewer:
            def __init__(self) -> None:
                self.calls = 0

            def translate(self, request: TranslationRequest) -> TranslationResult:
                self.calls += 1
                return TranslationResult(text="Er kam früh am Morgen", model="fake")

        provider = _NoReviewer()
        answer = _ask(task, provider)
        assert answer.issues_summary is None
        assert provider.calls == 1

    @pytest.mark.parametrize(
        "reply",
        [
            "",
            "   ",
            "I am sorry, I cannot help with that.",
            '{"acceptable": false}',  # rejected without saying why
            '{"acceptable": false, "problems": []}',
            "{broken json",
            "[]",
        ],
    )
    def test_an_unusable_reply_means_no_opinion(self, reply: str) -> None:
        assert parse_review(reply).has_objections is False

    def test_a_plain_acceptance_is_read(self) -> None:
        assert parse_review('{"acceptable": true}').acceptable is True

    def test_json_wrapped_in_prose_or_fences_is_read(self) -> None:
        fenced = '```json\n{"acceptable": false, "problems": ["Wrong case."]}\n```'
        assert parse_review(fenced).notes == ("Wrong case.",)
        chatty = 'Here is my review: {"acceptable": false, "problems": ["Wrong case."]} Hope that helps!'
        assert parse_review(chatty).notes == ("Wrong case.",)

    def test_a_flood_of_objections_is_trimmed(self) -> None:
        # A correction naming a dozen problems is a rewrite request, and
        # the model treats it as one — it starts over instead of fixing
        # what was named.
        many = '{"acceptable": false, "problems": ["a","b","c","d","e","f"]}'
        assert len(parse_review(many).notes) == 4


class TestStructureIsSettledFirst:
    def test_a_malformed_answer_is_not_sent_for_review(self, task: TranslationTask) -> None:
        # Paying for an opinion on the register of a reply that lost its
        # markup is paying twice for the same rejection.
        provider = _Provider(verdicts=[ReviewVerdict()], answers=["<p>tags</p>"])
        html_task = TranslationTask(
            entity_type="chapter_block",
            entity_id="b2",
            field="content",
            source_locale="ru",
            target_locale="de",
            text="<p>Текст</p><p>Второй абзац</p><p>Третий</p>",
            content_kind="html",
            source_hash="h2",
        )
        _ask(html_task, provider)
        assert provider.reviewed == [], "structural failure short-circuits the review"


class TestANoteTheModelHasAlreadyHeard:
    """The register names a word; it does not argue for one.

    `glossary_term_missing` used to go back to the model wrapped in
    "your previous attempt at this exact text had these problems".
    Nothing in that second ask was new — the pair was in the first
    prompt and the model read it and chose otherwise — so the only thing
    the retry added was pressure, and the keep-the-better-answer rule
    then preferred whichever answer gave in. On a Bible course that is
    usually right. On "a 30-day grace period" it buys *Gnade*.

    Worse, the note stood in front of the editorial reader below: a row
    was skipped for review because the register had an opinion about a
    word, and the reader is the only part of this pipeline that could
    have said whether the opinion applied.
    """

    @pytest.fixture
    def task_with_a_term(self) -> TranslationTask:
        return TranslationTask(
            entity_type="chapter_block",
            entity_id="b2",
            field="content",
            source_locale="ru",
            target_locale="de",
            text="Он пришёл рано утром на собрание",
            content_kind="plain",
            source_hash="h2",
        )

    def test_a_register_note_does_not_spend_a_second_call(self, task_with_a_term: TranslationTask) -> None:
        provider = _Provider(verdicts=[ReviewVerdict()], answers=["Er kam früh am Morgen zur Sitzung"])
        answer = _ask(task_with_a_term, provider)
        assert answer.text == "Er kam früh am Morgen zur Sitzung"
        assert len(provider.requests) == 1, "the register was already in the first prompt"

    def test_a_register_note_does_not_keep_the_row_from_the_reader(self, task_with_a_term: TranslationTask) -> None:
        provider = _Provider(verdicts=[ReviewVerdict()], answers=["Er kam früh am Morgen zur Sitzung"])
        _ask(task_with_a_term, provider)
        assert provider.reviewed == ["Er kam früh am Morgen zur Sitzung"], (
            "an advisory note must not be the reason a row skips review"
        )

    def test_the_register_still_says_what_it_saw(self, task_with_a_term: TranslationTask) -> None:
        # Advisory is not silent. The row is served, the objection is
        # logged under its stable code, and the rate stays a number.
        provider = _Provider(verdicts=[ReviewVerdict()], answers=["Er kam früh am Morgen zur Sitzung"])
        answer = _ask(task_with_a_term, provider)
        assert answer.failed is False
        assert answer.issues_summary is None, "an advisory note does not park a row"
