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
import time
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from types import TracebackType

from app.core.metrics import emit, increment
from app.services.bible.substitution import post_substitute, pre_substitute
from app.services.translation.prompt import build_system_prompt, build_user_prompt
from app.services.translation.protocol import (
    TranslationError,
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
)

logger = logging.getLogger(__name__)

_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Retry only on transient classes, never on generic 4xx responses.
_RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


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
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            # Caller responsibility, but assert loudly. Silently swallowing
            # an empty key would leave us calling Gemini unauthenticated.
            raise ValueError("GeminiTranslationProvider requires a non-empty api_key")
        self._api_key = api_key
        self._model = model
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
        bible_subs: list = []
        request_text = request.text
        if request.content_kind in _KINDS_THAT_CAN_QUOTE_SCRIPTURE:
            request_text, bible_subs = pre_substitute(request_text, request.source_locale)
            if bible_subs:
                request = TranslationRequest(
                    text=request_text,
                    source_locale=request.source_locale,
                    target_locale=request.target_locale,
                    content_kind=request.content_kind,
                    context=request.context,
                )

        payload = self._build_payload(request)
        url = f"{_API_BASE}/models/{self._model}:generateContent"
        headers = {"Content-Type": "application/json", "X-goog-api-key": self._api_key}

        # Enforce the per-instance minimum interval before the first attempt
        # of this translate() call. We only gate ``translate()`` entries —
        # the bounded internal retry loop below should not be throttled too,
        # since retries already back off on their own.
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
                    try:
                        increment("equip.gemini.calls_total", model=self._model, outcome="success")
                        # ``emit`` lets us pass the token count as the metric
                        # value directly — Datadog ``sum:`` over this gives
                        # the cumulative token spend.
                        if result.input_tokens:
                            emit(
                                "equip.gemini.tokens_input_total",
                                float(result.input_tokens),
                                model=self._model,
                            )
                        if result.output_tokens:
                            emit(
                                "equip.gemini.tokens_output_total",
                                float(result.output_tokens),
                                model=self._model,
                            )
                        # Billed as output, absent from the reply, and the
                        # single largest thing that ever went wrong with
                        # this bill. Always emitted — including as zero —
                        # so the dashboard shows a flat line at nought
                        # rather than no line at all, and a model change
                        # that reintroduces thinking is visible the same
                        # hour instead of at the end of the month.
                        emit(
                            "equip.gemini.tokens_thinking_total",
                            float(result.thinking_tokens or 0),
                            model=self._model,
                        )
                    except Exception:
                        pass
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
                    return result
                if response.status_code in _RETRYABLE_STATUSES:
                    last_error = TranslationError(f"Gemini returned {response.status_code}: {response.text[:200]}")
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
                            outcome="retry",
                            status_code=str(response.status_code),
                        )
                else:
                    with contextlib.suppress(Exception):
                        increment(
                            "equip.gemini.calls_total",
                            model=self._model,
                            outcome="fatal",
                            status_code=str(response.status_code),
                        )
                    raise TranslationError(f"Gemini returned {response.status_code}: {response.text[:200]}")

            if attempt < self._max_retries:
                # Exponential back-off, but capped so the *total* sleep
                # budget across all retries is ≤ 1.5s. Combined with the
                # per-call read timeout this bounds worst-case time on a
                # bad batch instead of letting one stuck call pile retries
                # on top of a 30s timeout.
                time.sleep(min(0.5, 0.1 * (2**attempt)))

        raise TranslationError(f"Gemini call failed after retries: {last_error!r}")

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
            text = "".join(p.get("text", "") for p in parts).strip()
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
