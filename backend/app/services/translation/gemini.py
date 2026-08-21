"""Gemini-backed implementation of ``TranslationProvider``.

We hit the public ``generativelanguage.googleapis.com`` REST surface
directly with ``httpx``; pulling in ``google-generativeai`` would add a
sizeable transitive dependency tree for one endpoint. The API contract is
documented at https://ai.google.dev/api/rest/v1beta/models/generateContent.

The provider is *only* constructed when ``settings.GEMINI_API_KEY`` is
set. See ``app.services.translation.service.get_translation_provider``.
"""

from __future__ import annotations

import contextlib
import logging
import re
import time
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Final

import httpx

if TYPE_CHECKING:
    from types import TracebackType

    from app.schemas.locale import LocaleCode
    from app.services.bible.substitution import Substitution
    from app.services.translation.protocol import CallBudget, ContentKind

from app.core.metrics import emit, increment
from app.schemas.locale import LOCALE_DISPLAY_NAMES
from app.services.bible.substitution import post_substitute, pre_substitute
from app.services.translation.html_split import markup_correction_note, split_html_for_translation
from app.services.translation.prompt import build_system_prompt, build_user_prompt
from app.services.translation.protocol import (
    TranslationError,
    TranslationPaused,
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
    TranslationUnavailable,
)
from app.services.translation.reviewer import ReviewVerdict, build_review_prompt, parse_review
from app.services.translation.term_memory import TermMemory, merge_pairs
from app.services.translation.typography import normalize_typography
from app.services.translation.validation import tag_names

logger = logging.getLogger(__name__)

#: A markdown code fence, opening (with an optional language tag) or
#: closing. It has to be recognised in two positions, because
#: production has both: on its own line, and welded to the end of a
#: tag — the live row reads `</h2>` immediately followed by the
#: opening fence. Either way the marker must run to the end of its
#: line, which is what keeps a pair of backticks used inline in prose
#: out of it: that is punctuation, and this pass has no business
#: touching it.
_FENCE_MARKER: Final[re.Pattern[str]] = re.compile(
    r"(?:(?<=^)|(?<=>))[ \t]*```[a-zA-Z0-9]*[ \t]*(?=\r?\n|\Z)\r?\n?",
    re.MULTILINE,
)

_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Retry only on transient classes, never on generic 4xx responses.
_RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})

# Statuses that say something about the service or about our account,
# and nothing whatsoever about the text we sent.
#
# The retryable set above plus the three ways the door can be shut on
# us: 401 (key rejected), 403 (key disabled, billing off, project
# suspended) and 404 (the model id no longer exists — a deploy-time
# mistake, not a sentence the model refuses). A row must not spend a
# retry on any of them, because none of them will read differently if
# the text is reworded.
#
# What is deliberately NOT here: 400 and 413. Those are the API looking
# at this particular request and rejecting it — a block past the token
# ceiling, a payload it cannot parse. That is a property of the text,
# it will recur on every retry, and the attempt cap is exactly the
# mechanism meant to stop asking.
_UNAVAILABLE_STATUSES = _RETRYABLE_STATUSES | frozenset({401, 403, 404})


def _is_unavailable(status_code: int) -> bool:
    """Did the provider fail to answer, rather than answer badly?

    Every 5xx counts, not only the four named above: a gateway we have
    not seen before is still a gateway, and the fallback for an unknown
    5xx has to be "the service is down", never "this text cannot be
    translated".
    """
    return status_code in _UNAVAILABLE_STATUSES or 500 <= status_code < 600


# What the ``outcome`` tag on ``equip.gemini.calls_total`` is allowed to
# say, and why the vocabulary is what it is.
#
# The tag has to carry the whole story on its own. ``status_code`` is
# passed on every emit below and it is NOT queryable: the log-based
# metric rule in Datadog groups ``equip.gemini.calls_total`` by ``model``
# and ``outcome`` and nothing else, so every series comes back with
# ``status_code:N/A`` no matter what the code puts in the log line —
# verified against thirty days of production on 2026-08-20, across all
# six live series. (``equip.activity.requests_total`` does carry a real
# ``status_code``, so this is that one rule's group-by list and not the
# log pipeline. ``docs/datadog/README.md`` has the one-line UI fix.)
#
# So the distinction that matters has to live in ``outcome``:
#
# * ``rate_limited`` — a 429, and its own value rather than another
#   ``retry`` because 429 is the money one. A prepaid balance that has
#   run out and a model that is briefly overloaded both used to arrive
#   as ``outcome:retry``, and on 2026-08-19 that count went 0 → 1,685 in
#   an hour with successes collapsing and nothing anywhere saying why.
#   Only two things produce a sustained 429 — our quota, or a runaway
#   loop of ours — and both are bills.
# * ``retry`` — 408 or a 5xx, another attempt follows. Genuinely "the
#   service is having a moment".
# * ``unavailable`` / ``rejected`` — the split that ``protocol.py``
#   already draws between ``TranslationUnavailable`` (the provider could
#   not answer: 401, 403, 404, an unretried 5xx) and ``TranslationError``
#   (it looked at this request and refused it: 400, 413). These replace
#   the old ``fatal``, which merged the two — a disabled key and an
#   oversized block looked identical, and only one of them is fixed by
#   editing the text.
# * ``transport`` — no HTTP status at all; the call never landed.
# * ``review`` / ``review_failed`` — the reviewer's call, kept under its
#   own names so ``sum:…{outcome:success}`` keeps meaning "translations"
#   the way every existing query assumes.


def _failure_outcome(status_code: int, *, will_retry: bool) -> str:
    """The ``outcome`` tag for a Gemini response we cannot use."""
    if status_code == 429:
        return "rate_limited"
    if will_retry:
        return "retry"
    return "unavailable" if _is_unavailable(status_code) else "rejected"


# Where a Bible quotation can plausibly live. ``plain`` covers the
# Daily Challenge explanations, which quote constantly and have no
# markup at all to hang a blockquote on — the case that showed English
# verses to German readers in production.
#
# ``quiz_option`` was left out on the reasoning that an answer option is
# too short to carry a quotation. Production disagreed: options quote
# Acts 8:4 and Acts 10:34 in full, with the reference in brackets, and
# every one of them was going to the model to be re-worded rather than
# to the canonical text. An option that quotes is the case where getting
# it wrong is most visible — the student is being asked to recognise the
# verse.
#
# Nothing is lost by including it. ``pre_substitute`` only acts when it
# finds a reference AND matches the text against the canon at ≥ 0.80; an
# option that merely paraphrases is left exactly as it was.
_KINDS_THAT_CAN_QUOTE_SCRIPTURE: frozenset[str] = frozenset({"html", "plain", "quiz_question", "quiz_option"})


class GeminiTranslationProvider:
    """Synchronous Gemini provider with bounded retries.

    Designed for short-lived FastAPI workers: one ``httpx.Client`` per
    instance, transports reused across calls, no global state.

    Lifecycle: when the caller passes their own ``client``, we never close
    it — that's the caller's responsibility. When we construct the client
    ourselves, ``close()`` (or use as a context manager) releases the
    transport. We deliberately do **not** define ``__del__``: GC ordering
    on shutdown is unreliable, and silently closing a caller-owned client
    in a finalizer is a footgun the test suite has tripped over.
    """

    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
        max_retries: int = 2,
        min_interval_seconds: float = 0.0,
        review_model: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            # Caller responsibility, but assert loudly. Silently swallowing
            # an empty key would leave us calling Gemini unauthenticated.
            raise ValueError("GeminiTranslationProvider requires a non-empty api_key")
        self._api_key = api_key
        self._model = model
        # The model that reads the finished translation. Falls back to the
        # translating model, which is better than no review at all — but
        # measurably worse at it, which is why production names a
        # different one.
        self._review_model = review_model or model
        self._max_output_tokens = max_output_tokens
        self._max_retries = max_retries
        # Min wall-time between two successive ``translate()`` calls on this
        # instance. Set to ``4.5`` (≈13 RPM) when running backfill scripts
        # against the free-tier 15 RPM cap; left at ``0`` in production
        # where natural request spacing keeps us well under the limit.
        self._min_interval_seconds = min_interval_seconds
        self._last_call_monotonic: float = 0.0
        # Split timeout: a slow connect or a stuck pool checkout shouldn't
        # eat the full read budget. Read uses the configured per-call cap
        # (the actual generation latency); connect/write/pool stay short.
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=timeout_seconds, write=10.0, pool=5.0),
        )

    def close(self) -> None:
        """Release the underlying HTTP client when we own it.

        Idempotent; safe to call multiple times. No-op when the caller
        injected the client (they retain ownership).
        """
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> GeminiTranslationProvider:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def translate(self, request: TranslationRequest) -> TranslationResult:
        """Translate with no deadline — the synchronous callers' door.

        A teacher saving a block, an admin retry, a test: nobody is
        holding a stopwatch, so a long document may take as many calls
        as it needs. The worker has a stopwatch and comes in through
        ``translate_within``.
        """
        return self.translate_within(request)

    def translate_within(
        self,
        request: TranslationRequest,
        *,
        budget: CallBudget | None = None,
    ) -> TranslationResult:
        if request.source_locale == request.target_locale or not request.text.strip():
            return TranslationResult(text=request.text, model=self._model)

        # Swap canonical Bible quotes for sentinel markers BEFORE sending
        # to Gemini, then restore them AFTER with the target-locale
        # canonical text. This is what guarantees a quoted verse comes
        # back as KJV / Luther / Kulish verbatim rather than as the
        # model's own rendering — the prompt tells it to leave quoted
        # Scripture untouched, which without this layer means an English
        # verse arriving intact in the middle of German prose.
        #
        # Prose kinds only. A title or an answer option is too short to
        # carry a quotation, and the marker would be most of the string.
        #
        # This happens once, on the whole document, and it has to: a
        # blockquote and the reference that identifies it are often two
        # different nodes, and cutting the document first would separate
        # them and leave the quote unrecognised. Everything below works
        # on the markered text, and ``post_substitute`` at the end works
        # on the reassembled whole — so a marker is restored the same way
        # whether it travelled alone or with five siblings.
        bible_subs: list[Substitution] = []
        request_text = request.text
        if request.content_kind in _KINDS_THAT_CAN_QUOTE_SCRIPTURE:
            request_text, bible_subs = pre_substitute(request_text, request.source_locale)
            if bible_subs:
                # ``replace`` rather than a fresh construction: the old
                # spelling listed the fields by hand and silently dropped
                # ``rewrite_notes``, so a correcting pass on any text
                # containing a quotation was sent as if it were a first
                # ask — the model was never told what it had got wrong.
                request = replace(request, text=request_text)

        pieces = self._pieces_for(request, bible_subs)
        if len(pieces) == 1:
            result = self._generate(request)
        else:
            result = self._translate_in_pieces(request, pieces, budget=budget)

        if bible_subs:
            # A marker that went out and did not come back
            # takes the verse with it: production had a
            # German answer option come back as "Matthäus
            # 5,9" where the source read "Matthew 5:9
            # ('Blessed are the peacemakers…')" — reference
            # kept, Scripture deleted. Only the length check
            # noticed, and only because the string was short.
            lost = [sub.marker for sub in bible_subs if sub.marker not in result.text]
            if lost:
                logger.warning(
                    "scripture_marker_dropped locale=%s markers=%d kind=%s",
                    request.target_locale,
                    len(lost),
                    request.content_kind,
                )
            # Restore Bible quote markers with the canonical
            # target-locale text. Falls back to source if the
            # target-locale lookup misses (see ``post_substitute``).
            result = TranslationResult(
                text=post_substitute(result.text, bible_subs, request.target_locale),
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                thinking_tokens=result.thinking_tokens,
                model=result.model,
                lost_scripture=bool(lost),
            )

        # Last, after the pieces are back together and the canonical
        # verses are back in place, point the whole string the way the
        # target language is written: German commas in references, one
        # apostrophe per language, one shape of quotation mark. The rules
        # are exact, so they are a function rather than a line in the
        # prompt — see ``typography.py`` for the production counts that
        # say how often the prompt alone got it wrong.
        #
        # On the document, not on each piece. A quotation opens in one
        # paragraph and closes in another, and a pass that only ever saw
        # one of them would have to guess.
        #
        # ``content_kind`` goes with it because one rule cannot be read
        # off the text: an English chapter title is title-cased and the
        # identical words in a paragraph are not, and the only thing
        # that knows which this is, is the field it came from.
        # Before pointing it: take out a code fence the model volunteered.
        # It has to happen here rather than in ``_parse_response`` because
        # the decision needs the source — a lesson that genuinely teaches
        # markdown carries the fence in the Russian too, and then it is
        # content.
        unfenced = self._drop_markdown_fence(result.text, request.text)
        if unfenced != result.text:
            logger.warning(
                "gemini: removed a markdown fence the source did not have entity_kind=%s locale=%s",
                request.content_kind,
                request.target_locale,
            )
            result = replace(result, text=unfenced)

        pointed = normalize_typography(result.text, request.target_locale, request.content_kind)
        if pointed != result.text:
            result = replace(result, text=pointed)
        return result

    def _pieces_for(self, request: TranslationRequest, bible_subs: list[Substitution]) -> list[str]:
        """How this document should be asked for: whole, or in pieces.

        Only ``html`` is ever cut. Every other kind is a heading, an
        answer option or a paragraph of prose with no block structure to
        cut along, and none of them is remotely large enough to provoke
        the failure this exists to fix.
        """
        if request.content_kind != "html":
            return [request.text]
        pieces = split_html_for_translation(request.text)
        if len(pieces) == 1:
            return pieces

        # A marker stands in for a verse, and half a marker restores
        # nothing. Cuts fall on ``<`` at the top level and a marker is
        # plain ASCII inside a text node, so one cannot be cut in two —
        # but this is the invariant the whole substitution layer rests
        # on, and an invariant nobody checks is a hope. Counted rather
        # than assumed; if the arithmetic ever disagrees, the document
        # goes in one call and the verses are safe.
        for sub in bible_subs:
            if sum(piece.count(sub.marker) for piece in pieces) != request.text.count(sub.marker):
                logger.error("html_split_would_cut_a_marker kind=%s pieces=%d", request.content_kind, len(pieces))
                return [request.text]
        return pieces

    def _translate_in_pieces(
        self,
        request: TranslationRequest,
        pieces: list[str],
        *,
        budget: CallBudget | None,
    ) -> TranslationResult:
        """Ask for each piece on its own and put the document back together.

        The pieces are a contiguous partition of the source (see
        ``html_split``), so the answer is their concatenation in order —
        nothing is re-wrapped, nothing is re-indented, no separator is
        introduced.

        One thing is checked on each piece, and one on the whole:

        * A piece whose markup came back wrong earns a correcting pass
          *for that piece*. This is the entire point of the exercise —
          the same correction on the full 85-tag block only sometimes
          works, because the model has to hold every other tag in place
          while it fixes one. On a paragraph it is an easy ask.
        * The reassembled document's tags are compared with the source's
          before returning. Nothing is repaired at that point; it is
          logged under a stable code, and ``validation`` parks the row
          exactly as it does today. A document with one mangled
          paragraph fails as a document — half a lesson in the reader's
          language and half in someone else's is not a better outcome
          than the gap.

        The budget is asked before every call *after the first*. The
        first one is the call the executor already authorised when it
        checked ``can_afford_one_call()`` for this batch; the extra ones
        are what splitting introduced, and they have to be paid for out
        of the same allowance.

        The document also remembers itself as it goes. Splitting a lesson
        into paragraphs is what let a name drift *inside one block* — a
        heading and the paragraph under it spelled Philippi two different
        ways because paragraph two was a separate call that had never
        seen paragraph one (``translation/term_memory.py`` has the
        production readings). So each piece is offered whatever the
        pieces before it settled on, on top of whatever the course
        already knew. The memory is local to this call, which is what
        makes it safe on a worker thread: one document, one loop, no
        shared state.
        """
        translated: list[str] = []
        input_tokens = output_tokens = thinking_tokens = 0
        corrected_pieces = 0
        learned = TermMemory()

        for index, piece in enumerate(pieces):
            if not piece.strip():
                translated.append(piece)
                continue
            if index and budget is not None and not budget.can_afford_one_call():
                raise TranslationPaused(
                    f"Budget spent after {index} of {len(pieces)} pieces; "
                    "the document is left untranslated rather than half-translated."
                )
            # The course first, this document second: a wording the rest
            # of the course already uses outranks one this block invented
            # a paragraph ago.
            piece_request = replace(
                request,
                text=piece,
                term_memory=merge_pairs(
                    request.term_memory,
                    learned.recall(piece, target_locale=request.target_locale),
                ),
            )
            part = self._generate(piece_request)
            input_tokens += part.input_tokens or 0
            output_tokens += part.output_tokens or 0
            thinking_tokens += part.thinking_tokens or 0

            note = markup_correction_note(piece, part.text)
            if note is not None and (budget is None or budget.can_afford_one_call()):
                # Not a retry. Sampling is at temperature 0, so asking
                # the identical question again gets the identical answer;
                # what changes here is the question — the model is shown
                # the tags it dropped or invented and asked again.
                try:
                    corrected = self._generate(replace(piece_request, rewrite_notes=(*request.rewrite_notes, note)))
                except TranslationError:
                    corrected = None
                if corrected is not None:
                    input_tokens += corrected.input_tokens or 0
                    output_tokens += corrected.output_tokens or 0
                    thinking_tokens += corrected.thinking_tokens or 0
                    if markup_correction_note(piece, corrected.text) is None:
                        part = corrected
                        corrected_pieces += 1
            learned.learn(
                piece,
                part.text,
                source_locale=request.source_locale,
                target_locale=request.target_locale,
            )
            translated.append(part.text)

        text = "".join(translated)
        expected, got = tag_names(request.text), tag_names(text)
        if expected != got:
            logger.warning(
                "html_split_structure_lost locale=%s pieces=%d source_tags=%d translated_tags=%d",
                request.target_locale,
                len(pieces),
                len(expected),
                len(got),
            )
        logger.info(
            "html_split_translated locale=%s pieces=%d corrected=%d tags=%d",
            request.target_locale,
            len(pieces),
            corrected_pieces,
            len(expected),
        )
        return TranslationResult(
            text=text,
            input_tokens=input_tokens or None,
            output_tokens=output_tokens or None,
            thinking_tokens=thinking_tokens or None,
            model=self._model,
        )

    def _generate(self, request: TranslationRequest) -> TranslationResult:
        """One provider call, with its bounded retries. No substitution,
        no splitting — those belong to the document, this is the wire."""
        payload = self._build_payload(request)
        url = f"{_API_BASE}/models/{self._model}:generateContent"
        headers = {"Content-Type": "application/json", "X-goog-api-key": self._api_key}

        # Enforce the per-instance minimum interval before the first
        # attempt of this call. The gate is per *call*, not per document:
        # a document translated in five pieces is five requests against
        # the free-tier RPM cap, and a backfill script that spaced only
        # the documents would burst straight through it. The bounded
        # internal retry loop below is still not throttled — retries
        # already back off on their own.
        if self._min_interval_seconds > 0:
            elapsed = time.monotonic() - self._last_call_monotonic
            wait = self._min_interval_seconds - elapsed
            if wait > 0:
                time.sleep(wait)
        self._last_call_monotonic = time.monotonic()

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("Gemini transport error attempt=%s err=%s", attempt, exc)
                # A transport-level failure (timeout/connect/DNS) produces no
                # HTTP status, so without this the per-call metric never fires
                # on a full Gemini network outage — the failure mode the cost/
                # budget dashboard most needs to see (same gap the youversion
                # fix closed). status_code=0 = "no response".
                with contextlib.suppress(Exception):
                    increment(
                        "equip.gemini.calls_total",
                        model=self._model,
                        outcome="transport",
                        status_code="0",
                    )
            else:
                if response.status_code == 200:
                    try:
                        body = response.json()
                    except ValueError as exc:
                        # A 200 whose body is not JSON: a proxy error page,
                        # a truncated response, an upstream incident served
                        # as HTML. Rare, and it used to escape as a raw
                        # ValueError — which the caller does not catch,
                        # because everything else here arrives as
                        # TranslationError. Since the pass now runs calls
                        # concurrently, one of those would surface out of a
                        # worker thread and take the whole plan down
                        # instead of failing a single row.
                        raise TranslationError(
                            f"Gemini returned 200 with a non-JSON body ({response.text[:200]!r})"
                        ) from exc
                    result = self._parse_response(body)
                    # Emit Gemini cost metrics on every successful 200.
                    # Tagged with model so a future model migration
                    # (e.g. flash → pro) keeps the curves separable.
                    # Wrapped in try/except — metric failure must NEVER
                    # break the translation pipeline.
                    with contextlib.suppress(Exception):
                        increment(
                            "equip.gemini.calls_total",
                            model=self._model,
                            outcome="success",
                            status_code="200",
                        )
                        self._emit_token_metrics(
                            model=self._model,
                            role="translate",
                            input_tokens=result.input_tokens,
                            output_tokens=result.output_tokens,
                            thinking_tokens=result.thinking_tokens,
                        )
                    return result
                if response.status_code in _RETRYABLE_STATUSES:
                    last_error = TranslationUnavailable(
                        f"Gemini returned {response.status_code}: {response.text[:200]}"
                    )
                    logger.warning(
                        "Gemini transient %s attempt=%s body=%s",
                        response.status_code,
                        attempt,
                        response.text[:200],
                    )
                    with contextlib.suppress(Exception):
                        increment(
                            "equip.gemini.calls_total",
                            model=self._model,
                            outcome=_failure_outcome(response.status_code, will_retry=True),
                            status_code=str(response.status_code),
                        )
                else:
                    with contextlib.suppress(Exception):
                        increment(
                            "equip.gemini.calls_total",
                            model=self._model,
                            outcome=_failure_outcome(response.status_code, will_retry=False),
                            status_code=str(response.status_code),
                        )
                    # A status we do not retry still has to be sorted into
                    # "the service said no to us" and "the service said no
                    # to this text" — see ``_is_unavailable``. Only the
                    # second may ever count against a row's attempts.
                    if _is_unavailable(response.status_code):
                        raise TranslationUnavailable(f"Gemini returned {response.status_code}: {response.text[:200]}")
                    raise TranslationError(f"Gemini returned {response.status_code}: {response.text[:200]}")

            if attempt < self._max_retries:
                # Exponential back-off, but capped so the *total* sleep
                # budget across all retries is ≤ 1.5s. Combined with the
                # per-call read timeout this bounds worst-case time on a
                # bad batch instead of letting one stuck call pile retries
                # on top of a 30s timeout.
                time.sleep(min(0.5, 0.1 * (2**attempt)))

        # Getting here means every attempt either never reached Gemini or
        # came back on a retryable status. Both are the service, not the
        # sentence: the loop only falls out of the bottom on a transport
        # error or a 429/5xx, and every other outcome returned or raised
        # above. So this is always ``TranslationUnavailable``.
        raise TranslationUnavailable(f"Gemini call failed after retries: {last_error!r}")

    @staticmethod
    def _emit_token_metrics(
        *,
        model: str,
        role: str,
        input_tokens: int | None,
        output_tokens: int | None,
        thinking_tokens: int | None,
    ) -> None:
        """What this one call cost, in the units Gemini bills in.

        ``emit`` rather than ``increment`` so the token count IS the
        metric value — Datadog ``sum:`` over the window then gives
        cumulative spend directly.

        ``role`` says which of the two calls this was. ``model`` is what
        separates them in production today, where the reviewer runs a
        different model id, but the provider falls back to the
        translating model when no review model is configured, and in
        that deployment ``model`` alone cannot tell a $0.10-per-million
        translation from a $0.30-per-million review of it. Cheap to
        record now, impossible to recover later. It is not queryable
        until the log-based metric rule groups by it — see
        ``docs/datadog/README.md``.

        The caller wraps this in a suppression: a metric that fails must
        never fail a translation.
        """
        if input_tokens:
            emit("equip.gemini.tokens_input_total", float(input_tokens), model=model, role=role)
        if output_tokens:
            emit("equip.gemini.tokens_output_total", float(output_tokens), model=model, role=role)
        # Billed as output, absent from the reply, and the single largest
        # thing that ever went wrong with this bill. Always emitted —
        # including as zero — so the dashboard shows a flat line at
        # nought rather than no line at all, and a model change that
        # reintroduces thinking is visible the same hour instead of at
        # the end of the month.
        emit("equip.gemini.tokens_thinking_total", float(thinking_tokens or 0), model=model, role=role)

    def review(
        self,
        *,
        source: str,
        translation: str,
        source_locale: LocaleCode,
        target_locale: LocaleCode,
        content_kind: ContentKind,
        context: str | None = None,
    ) -> ReviewVerdict:
        """Read the translation back and say whether it would pass.

        A separate call on purpose. Asking the translator to grade its
        own answer gets agreement, not review — the defects that survive
        are precisely the ones it cannot see in itself. This call knows
        only the two texts.

        Every failure here means "no opinion". A reviewer that cannot be
        reached must not hold up a translation: it exists to raise the
        floor, and the floor without it is what the pipeline shipped
        yesterday.

        It is also the expensive half of the bill, and until 2026-08-20
        none of it was measured. This method counted its own calls and
        stopped there — no ``tokens_input_total``, no
        ``tokens_output_total``, no thinking count — while running a
        model that costs 3x the translator on input and 6.25x on output
        and accounting for roughly 52% of a full rebuild. Thirty days of
        production carried 1,756 review calls and not one token of
        theirs appeared in Datadog. Half a bill that nobody can see is
        half a bill nobody can stop, so the same three metrics come out
        of here now, under the reviewer's own model tag.
        """
        if not source.strip() or not translation.strip():
            return ReviewVerdict()

        prompt = build_review_prompt(
            source=source,
            translation=translation,
            source_language=LOCALE_DISPLAY_NAMES[source_locale],
            target_language=LOCALE_DISPLAY_NAMES[target_locale],
            content_kind=content_kind,
            context=context,
            source_locale=source_locale,
        )
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                # Same reasoning as translation: one answer, the most
                # likely one. A reviewer that disagrees with itself
                # between runs would make the queue a lottery.
                "temperature": 0,
                "maxOutputTokens": 512,
                "responseMimeType": "application/json",
            },
        }
        url = f"{_API_BASE}/models/{self._review_model}:generateContent"
        headers = {"Content-Type": "application/json", "X-goog-api-key": self._api_key}
        try:
            response = self._client.post(url, json=payload, headers=headers)
            if response.status_code != 200:
                logger.info("reviewer: HTTP %s, no opinion", response.status_code)
                # A reviewer that answers nothing and a reviewer that is
                # never called look the same from outside — both are
                # simply an absence of ``outcome:review``. So the refusal
                # gets counted too, with the status that caused it: a
                # review model id that no longer exists (404) would
                # otherwise silently turn every review off and leave the
                # translations shipping unread.
                with contextlib.suppress(Exception):
                    increment(
                        "equip.gemini.calls_total",
                        model=self._review_model,
                        outcome="review_failed",
                        status_code=str(response.status_code),
                    )
                return ReviewVerdict()
            body = response.json()
            candidates = body.get("candidates") or []
            parts = (candidates[0].get("content") or {}).get("parts") or []
            reply = "".join(part.get("text", "") for part in parts)
            usage = body.get("usageMetadata") or {}
        except Exception as exc:
            logger.info("reviewer: unreachable (%s), no opinion", type(exc).__name__)
            with contextlib.suppress(Exception):
                increment(
                    "equip.gemini.calls_total",
                    model=self._review_model,
                    outcome="review_failed",
                    status_code="0",
                )
            return ReviewVerdict()

        with contextlib.suppress(Exception):
            increment(
                "equip.gemini.calls_total",
                model=self._review_model,
                outcome="review",
                status_code="200",
            )
            # The reviewer bills exactly like the translator and was
            # never asked what it spent. ``usageMetadata`` has been in
            # every reply all along; nothing read it.
            self._emit_token_metrics(
                model=self._review_model,
                role="review",
                input_tokens=usage.get("promptTokenCount"),
                output_tokens=usage.get("candidatesTokenCount"),
                thinking_tokens=usage.get("thoughtsTokenCount"),
            )
        return parse_review(reply)

    def _build_payload(self, request: TranslationRequest) -> dict[str, Any]:
        system_prompt = build_system_prompt(
            source_locale=request.source_locale,
            target_locale=request.target_locale,
        )
        user_prompt = build_user_prompt(
            text=request.text,
            content_kind=request.content_kind,
            context=request.context,
            source_locale=request.source_locale,
            target_locale=request.target_locale,
            rewrite_notes=request.rewrite_notes,
            term_memory=request.term_memory,
        )
        return {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                # ``temperature=0`` for translation: we want the most
                # likely rendering, not creative paraphrase.
                "temperature": 0,
                "maxOutputTokens": self._max_output_tokens,
            },
        }

    @staticmethod
    @staticmethod
    def _drop_markdown_fence(translated: str, source: str) -> str:
        """Remove a code fence the model added and the author never wrote.

        Asked for HTML, the model sometimes answers in a markdown code
        block — ```html, the markup, ```. The scaffolding unwrapper above
        does not see it, because it looks for the tokens the prompt
        supplied; this is the model volunteering a different convention.

        Production shipped one: a live Ukrainian lesson body carries an
        opening fence welded to the end of a heading and a bare closing
        one at the end of the block — three backticks, twice, on a page
        students read. It passed every check.
        The markup either side is intact, so the tag comparison balances;
        a fence is not a tag.

        Conditioned on the source, not on the shape of the reply. A lesson
        that genuinely teaches markdown would carry the fence in the
        Russian too, and then it is content and stays. Only a fence the
        author did not write is scaffolding.
        """
        if "```" not in translated or "```" in source:
            return translated
        return _FENCE_MARKER.sub("", translated)

    @staticmethod
    def _unwrap_echoed_fence(text: str) -> str:
        """Take the translation out of a reply that repeated the prompt.

        Asked to translate a short line that opens with a quotation, the
        model sometimes answers twice: the source verbatim, then the
        fence markers it was given, then the actual translation. The
        answer is in there and it is correct — production hit this on
        «Злачное место» in the shepherd psalm, where the second half
        read „Grüne Auen“, exactly right, and the first half was the
        untouched Russian.

        Structural validation rejects the whole thing, and rightly: a
        reply containing the scaffolding is not a translation. But
        throwing it away costs a call and gets the same answer, because
        sampling is at temperature 0. So the scaffolding is removed and
        the result validated on its merits — if what is left is still
        wrong, every check that would have failed still fails.
        """
        if "===BEGIN" not in text:
            return text
        after_begin = text.rsplit("===BEGIN", 1)[-1]
        # The token itself runs to the end of its line; the content
        # starts on the next one.
        _, _, body = after_begin.partition("\n")
        return (body.split("===END", 1)[0] or after_begin).strip() or text

    def _parse_response(self, body: dict[str, Any]) -> TranslationResult:
        candidates = body.get("candidates") or []
        if not candidates:
            raise TranslationError(f"Gemini returned no candidates: {body!r}")

        # Gemini occasionally returns malformed candidates (string entries,
        # missing ``content``/``parts``, ``parts`` items that are not dicts).
        # Treat any structural deviation as a typed translation error so the
        # orchestrator can persist a ``status='failed'`` row instead of the
        # raw ``AttributeError`` taking down the whole batch.
        try:
            content = candidates[0].get("content") or {}
            parts = content.get("parts") or []
            text = self._unwrap_echoed_fence("".join(p.get("text", "") for p in parts).strip())
            finish_reason = candidates[0].get("finishReason")
        except (AttributeError, KeyError, TypeError, IndexError) as exc:
            raise TranslationError(f"Gemini returned malformed candidate: {body!r}") from exc

        # Only ``STOP`` represents a complete, voluntarily-terminated response.
        # Anything else (``MAX_TOKENS``, ``SAFETY``, ``RECITATION``, ``OTHER``,
        # …) means the model bailed mid-flight and we'd be persisting a
        # truncated or refused output as if it were a real translation. Fail
        # so the orchestrator records ``status='failed'`` and we can fix the
        # cause (bump ``maxOutputTokens``, adjust the prompt, etc.).
        # ``finish_reason`` is only allowed to be missing entirely; older
        # Gemini API shapes occasionally omitted it for short responses.
        if finish_reason is not None and finish_reason != "STOP":
            raise TranslationError(
                f"Gemini stopped with finishReason={finish_reason!r}; discarding partial output ({len(text)} chars)"
            )

        if not text:
            raise TranslationError("Gemini returned an empty translation")

        usage = body.get("usageMetadata") or {}
        return TranslationResult(
            text=text,
            input_tokens=usage.get("promptTokenCount"),
            output_tokens=usage.get("candidatesTokenCount"),
            thinking_tokens=usage.get("thoughtsTokenCount"),
            model=self._model,
        )


__all__ = ["GeminiTranslationProvider"]


# mypy enforces ``GeminiTranslationProvider`` matches ``TranslationProvider``
# structurally; the binding keeps the protocol import alive so the check
# runs even when nothing in this module consumes it directly.
_PROVIDER_TYPE: type[TranslationProvider] = GeminiTranslationProvider
