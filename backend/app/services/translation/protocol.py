"""Provider-agnostic types for the translation pipeline.

The public contract is intentionally small: ask for one (or many)
text → text translations, get either a result or a typed error. Anything
provider-specific (model id, prompt, retry policy) lives behind the
``TranslationProvider`` implementation.

``ContentKind`` and ``EntityType`` mirror the CHECK-constrained
vocabularies in ``content_translations`` — keeping the literals here (and
re-exporting from ``content_translation`` model) means the same string
set is enforced statically across the API edge, the orchestrator, the
prompt builder, and the ORM column.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode

# ``ContentKind`` selects prompt nuances: "plain" for prose, "html" for
# TipTap/HTML chapter blocks, "title" for short headings, "quiz_question"
# / "quiz_option" so the model knows not to expand a single-sentence
# answer into a paragraph. Static checking catches typos at the call site
# rather than letting them silently fall through to the default branch.
ContentKind = Literal[
    "plain",
    "html",
    "title",
    "quiz_question",
    "quiz_option",
]

# Mirrors ``TranslationEntityType`` in ``app.models.content_translation``;
# we re-declare it here (instead of re-exporting) because protocol.py is
# the lower-level module — importing the model here would invert the
# dependency direction. The two literals MUST stay in lockstep with the
# CHECK constraint in ``supabase/migrations/*_content_translations.sql``.
EntityType = Literal[
    "chapter_block",
    "course",
    "module",
    "chapter",
    "quiz",
    "quiz_question",
    "quiz_option",
    "assignment",
    "announcement",
    "course_event",
    "cohort",
    "daily_challenge_question",
    "daily_challenge_option",
    "rubric",
    "rubric_criterion",
    "rubric_level",
]


@dataclass(frozen=True, slots=True)
class TranslationRequest:
    """A single unit of work for the translator.

    ``text`` may be plain prose or sanitized HTML — the prompt instructs the
    model to preserve markup verbatim. ``content_kind`` lets us specialize
    handling for known shapes (e.g. quiz options should never expand into
    multiple sentences) without leaking that hint into the database column.
    """

    text: str
    source_locale: LocaleCode
    target_locale: LocaleCode
    content_kind: ContentKind = "plain"
    # Optional contextual hint surfaced to the model as a system note.
    # E.g. "course on the Acts of the Apostles" — improves accuracy on
    # ambiguous theological terms without bloating every row.
    context: str | None = None
    # What was wrong with the previous answer to this same request, in
    # the model's own output. Empty on a first ask. A retry is another
    # roll of the dice; this is a correction — the model is shown the
    # words it chose and told to choose differently. Used where the
    # defect is stable rather than random: the model does not stumble
    # into "зобов'язуюча", it prefers it, and asking again the same way
    # gets the same answer.
    rewrite_notes: tuple[str, ...] = ()
    # Names this course has already been given in ``target_locale``, as
    # ``(the form this text uses, the form the course used)``. A
    # preference, never an instruction — see
    # ``translation/term_memory.py`` for why it is worded the way it is
    # and for how a pair gets here at all. Empty for every caller that
    # has no course around it, which is every synchronous path and every
    # test that does not care.
    term_memory: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class TranslationResult:
    """Successful translation + telemetry."""

    text: str
    # Tokens reported by the provider (``None`` when unavailable).
    input_tokens: int | None = None
    output_tokens: int | None = None
    # Tokens the model spent thinking before answering. Billed as output
    # and invisible in the reply, which is exactly why they are recorded
    # separately: on 2026-08-17 production was running a thinking model
    # that spent ~840 of these per translated string — six times the
    # output it actually produced — and no metric would have shown it.
    # A cost we cannot see is a cost nobody stops.
    thinking_tokens: int | None = None
    # A quoted verse left for the model as a ``VERSE_`` placeholder and
    # did not come back. The verse is then simply gone: the placeholder
    # is what the canonical target-language text is restored into, and
    # with no placeholder there is nothing to restore into. Structural
    # validation cannot see this — it compares the text *before*
    # substitution with the text *after* restoration, and neither of
    # those contains a marker — so the provider has to say so itself.
    lost_scripture: bool = False
    # A quoted verse whose canonical text could not be had for the target
    # language *this time*, so the reader was given the author's own
    # quotation — in the author's language. An English verse inside
    # German prose, stored as a good translation.
    #
    # Only the transient kind is reported. A verse this edition will
    # never carry is the case the fallback was written for and is left
    # alone; ``bible.api_source.absence_is_remembered`` draws the line,
    # off the cache, without asking a service that is already refusing.
    #
    # Like ``lost_scripture``, invisible to structural validation: the
    # text we sent and the text we got back both look complete, and the
    # only difference is which language two sentences of it are in. On
    # 2026-08-22 sixteen live rows carried this and eleven others were
    # caught only because their English run happened to be long enough
    # for ``untranslated_run``. The provider knows; this is how it says so.
    scripture_in_source_language: bool = False
    # Provider-specific model id actually used (so logs can pin a row to a
    # version of the upstream service).
    model: str | None = None


class TranslationError(RuntimeError):
    """Raised when the provider answered and the answer is unusable.

    Substantive, in other words: the model was asked about *this text*
    and what came back cannot be stored — no candidates, a malformed
    candidate, an empty string, a refusal, a request the API rejected
    outright. Asking again may help (sampling is not quite
    deterministic) but there is no reason to think the next answer will
    differ, so each of these spends one of the row's five attempts and
    the fifth is terminal.

    Transient failures (network, 5xx) are retried inside the provider
    first; when those retries are also exhausted the provider raises
    ``TranslationUnavailable`` below, NOT this.
    """


class TranslationUnavailable(TranslationError):
    """Raised when the provider could not answer at all.

    A 429, a 503, a read timeout, a connection reset, a prepaid balance
    that ran out mid-run. None of these is a fact about the text: the
    same string sent an hour later translates perfectly.

    ``CONTENT_VERSION_MAX_ATTEMPTS`` exists to stop asking about a text
    that defeats translation, and on 2026-08-20 an eight-minute outage
    spent all five attempts on 174 rows that had nothing wrong with
    them, promoting every one to ``failed_permanent`` — terminal, and
    reachable only through the admin reset surface. The service being
    down is not the content being bad, and the two must not share a
    counter.

    A subclass of ``TranslationError`` on purpose. Every existing
    ``except TranslationError`` in the pipeline still catches an
    outage — a caller that does not care about the difference keeps
    behaving exactly as it did — and only the one place that counts
    attempts has to look closer. Making it a sibling would have meant
    auditing every handler to add it, and the handler that got missed
    would let an outage escape as an unhandled exception out of a
    worker thread.
    """


class TranslationPaused(RuntimeError):
    """Raised when the pass ran out of time part-way through a document.

    Deliberately *not* a ``TranslationError``: nothing is wrong with the
    text and nothing is wrong with the provider. A long HTML block is
    translated in several calls (see ``translation/html_split``), and if
    the clock runs out between them the half we have is not an answer —
    concatenating translated pieces with untranslated ones would ship a
    lesson in two languages.

    The caller must record nothing for the row and report the pass
    incomplete, which sends the job back to ``queued``. The next tick
    starts the document again with a fresh budget, and everything else
    the pass finished is already committed. Recording a failure instead
    would spend a retry on a clock, and ``failed_permanent`` is terminal.
    """


@runtime_checkable
class CallBudget(Protocol):
    """The one thing a provider needs to know about the pass's clock.

    Structural, so ``translation.budget.TranslationBudget`` satisfies it
    without importing anything from here — ``budget`` sits above
    ``protocol`` in the import order and must stay there.
    """

    def can_afford_one_call(self) -> bool: ...


@runtime_checkable
class TranslationProvider(Protocol):
    """Minimal surface every concrete provider must implement."""

    name: str

    def translate(self, request: TranslationRequest) -> TranslationResult:
        """Synchronously translate one request. Must be thread-safe."""


@runtime_checkable
class BudgetedTranslator(Protocol):
    """A provider that may spend more than one call on a single request.

    Kept as its own capability rather than a keyword on ``translate``
    for the same reason ``TranslationReviewer`` is: a ``runtime_checkable``
    Protocol only asks whether the method *name* is there, so widening
    ``translate`` would make every fake provider in the suite claim a
    signature it does not have. A distinct name is a claim that can be
    checked.

    Callers with a clock pass it here; callers without one (a teacher
    saving a block, a test) keep calling ``translate`` and nothing
    changes for them.
    """

    def translate_within(
        self,
        request: TranslationRequest,
        *,
        budget: CallBudget | None = None,
    ) -> TranslationResult:
        """Translate, asking ``budget`` before every call after the first.

        Raises ``TranslationPaused`` when the allowance runs out with the
        document part-translated.
        """
