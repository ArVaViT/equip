"""Thin Gemini wrapper for free-form prompts used by the question
generation orchestrator.

The existing ``GeminiTranslationProvider`` is shaped around the
translation contract (TranslationRequest → TranslationResult). The
question generation flow needs arbitrary ``(system, user) → text``
calls with JSON-shaped responses, so we ship a focused wrapper here
that mirrors the translation provider's httpx + retry pattern but
exposes a different surface.

Both providers share the same API key and httpx layout. We do NOT
share state — each orchestrator run constructs a fresh client and
closes it via the context manager, so a long-running cron worker
doesn't accumulate sockets.

Lives under ``daily_challenge/`` rather than ``translation/`` because
the orchestrator is the only caller; promoting to a shared module
would be premature.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from types import TracebackType

logger = logging.getLogger(__name__)

_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_RETRYABLE_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


class LLMError(RuntimeError):
    """Raised when a Gemini call fails permanently. The orchestrator
    catches this, logs the round event with ``status='failed'``,
    and continues with whatever candidates survived."""


class GeminiPromptClient:
    """Synchronous Gemini client for free-form ``(system, user) → text``
    prompts.

    Designed for orchestrator runs that issue several round-trips with
    different prompts. ``model`` and ``temperature`` are per-call so a
    creative-generation round can use a higher temperature than a
    fact-checking round on the same client.
    """

    def __init__(
        self,
        *,
        api_key: str,
        default_model: str = "gemini-2.5-flash-lite",
        timeout_seconds: float = 60.0,
        max_retries: int = 2,
        min_request_interval_seconds: float = 0.0,
        retry_backoff_seconds: float = 0.5,
        retry_backoff_cap_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("GeminiPromptClient requires a non-empty api_key")
        self._api_key = api_key
        self._default_model = default_model
        self._max_retries = max_retries
        # Proactive client-side rate limit: keep at least this long between
        # requests so a burst-heavy orchestrator run stays under a free-tier
        # per-minute quota (0 = no throttle, the default for paid keys). On a
        # 429 we still back off — but spacing requests up front is what stops
        # the free tier 429-ing *mid-passage* and yielding half-built output.
        self._min_interval = max(0.0, min_request_interval_seconds)
        self._retry_backoff = max(0.0, retry_backoff_seconds)
        self._retry_backoff_cap = max(0.0, retry_backoff_cap_seconds)
        self._last_request_at: float | None = None
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(connect=5.0, read=timeout_seconds, write=10.0, pool=5.0),
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _throttle(self) -> None:
        """Sleep just enough to keep consecutive requests ``_min_interval``
        seconds apart. No-op when the interval is 0 (paid keys)."""
        if self._min_interval <= 0:
            return
        if self._last_request_at is not None:
            wait = self._min_interval - (time.monotonic() - self._last_request_at)
            if wait > 0:
                time.sleep(wait)
        self._last_request_at = time.monotonic()

    def _backoff_delay(self, attempt: int) -> float:
        return min(self._retry_backoff_cap, self._retry_backoff * (2**attempt))

    def __enter__(self) -> GeminiPromptClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def invoke(
        self,
        *,
        system: str,
        user: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_output_tokens: int = 4096,
        expect_json: bool = False,
    ) -> str | Any:
        """Issue one Gemini call. Returns the text response, or the
        parsed JSON object when ``expect_json=True``.

        When ``expect_json`` is set, the prompt is augmented to request
        a single JSON object response, the result is parsed via
        ``json.loads``, and parsing failures raise ``LLMError`` so the
        orchestrator records ``status='failed'`` rather than persisting
        garbage.
        """
        chosen_model = model or self._default_model
        url = f"{_API_BASE}/models/{chosen_model}:generateContent"
        headers = {"Content-Type": "application/json", "X-goog-api-key": self._api_key}

        # When we want JSON, push the model into structured-output mode
        # via the generationConfig.responseMimeType (Gemini honours this
        # for plain-text models by emitting valid JSON without the
        # ```json fence the model otherwise wraps around objects).
        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        }
        if expect_json:
            generation_config["responseMimeType"] = "application/json"

        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": generation_config,
        }

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            self._throttle()
            try:
                response = self._client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("Gemini prompt transport error attempt=%s err=%s", attempt, exc)
            else:
                if response.status_code == 200:
                    text = self._parse_text(response.json())
                    if expect_json:
                        try:
                            return json.loads(text)
                        except json.JSONDecodeError as exc:
                            raise LLMError(
                                f"Gemini returned non-JSON despite responseMimeType: {text[:200]!r}"
                            ) from exc
                    return text
                if response.status_code in _RETRYABLE_STATUSES:
                    last_error = LLMError(f"Gemini returned {response.status_code}: {response.text[:200]}")
                    logger.warning(
                        "Gemini prompt transient %s attempt=%s body=%s",
                        response.status_code,
                        attempt,
                        response.text[:200],
                    )
                else:
                    raise LLMError(f"Gemini returned {response.status_code}: {response.text[:200]}")

            if attempt < self._max_retries:
                time.sleep(self._backoff_delay(attempt))

        raise LLMError(f"Gemini prompt failed after retries: {last_error!r}")

    @staticmethod
    def _parse_text(body: dict[str, Any]) -> str:
        candidates = body.get("candidates") or []
        if not candidates:
            raise LLMError(f"Gemini returned no candidates: {body!r}")
        try:
            content = candidates[0].get("content") or {}
            parts = content.get("parts") or []
            text = "".join(p.get("text", "") for p in parts).strip()
            finish_reason = candidates[0].get("finishReason")
        except (AttributeError, KeyError, TypeError, IndexError) as exc:
            raise LLMError(f"Gemini returned malformed candidate: {body!r}") from exc
        if finish_reason is not None and finish_reason != "STOP":
            raise LLMError(f"Gemini stopped with finishReason={finish_reason!r}; truncated output ({len(text)} chars)")
        if not text:
            raise LLMError("Gemini returned an empty response")
        return text


__all__ = ["GeminiPromptClient", "LLMError"]
