"""Gemini-backed implementation of ``TranslationProvider``.

We hit the public ``generativelanguage.googleapis.com`` REST surface
directly with ``httpx``; pulling in ``google-generativeai`` would add a
sizeable transitive dependency tree for one endpoint. The API contract is
documented at https://ai.google.dev/api/rest/v1beta/models/generateContent.

The provider is *only* constructed when ``settings.GEMINI_API_KEY`` is
set. See ``app.services.translation.service.get_translation_provider``.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from types import TracebackType

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

        payload = self._build_payload(request)
        url = f"{_API_BASE}/models/{self._model}:generateContent"
        headers = {"Content-Type": "application/json", "X-goog-api-key": self._api_key}

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(url, json=payload, headers=headers)
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("Gemini transport error attempt=%s err=%s", attempt, exc)
            else:
                if response.status_code == 200:
                    return self._parse_response(response.json())
                if response.status_code in _RETRYABLE_STATUSES:
                    last_error = TranslationError(f"Gemini returned {response.status_code}: {response.text[:200]}")
                    logger.warning(
                        "Gemini transient %s attempt=%s body=%s",
                        response.status_code,
                        attempt,
                        response.text[:200],
                    )
                else:
                    raise TranslationError(f"Gemini returned {response.status_code}: {response.text[:200]}")

            if attempt < self._max_retries:
                # Exponential back-off, but capped so the *total* sleep
                # budget across all retries is ≤ 1.5s. Combined with the
                # per-call read timeout this bounds worst-case time on a
                # bad batch instead of letting one stuck call pile retries
                # on top of a 30s timeout.
                time.sleep(min(0.5, 0.1 * (2**attempt)))

        raise TranslationError(f"Gemini call failed after retries: {last_error!r}")

    def translate_batch(self, requests: list[TranslationRequest]) -> list[TranslationResult]:
        # The REST endpoint translates one request at a time; the batching
        # win comes from issuing them on a shared HTTP/2 connection. The
        # default sequential implementation is fine for the volumes we
        # anticipate (one course publish is a few hundred chunks).
        return [self.translate(req) for req in requests]

    def _build_payload(self, request: TranslationRequest) -> dict[str, Any]:
        system_prompt = build_system_prompt(
            source_locale=request.source_locale,
            target_locale=request.target_locale,
        )
        user_prompt = build_user_prompt(
            text=request.text,
            content_kind=request.content_kind,
            context=request.context,
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
        except (AttributeError, KeyError, TypeError, IndexError) as exc:
            raise TranslationError(f"Gemini returned malformed candidate: {body!r}") from exc

        if not text:
            raise TranslationError("Gemini returned an empty translation")

        usage = body.get("usageMetadata") or {}
        return TranslationResult(
            text=text,
            input_tokens=usage.get("promptTokenCount"),
            output_tokens=usage.get("candidatesTokenCount"),
            model=self._model,
        )


__all__ = ["GeminiTranslationProvider"]


# mypy enforces ``GeminiTranslationProvider`` matches ``TranslationProvider``
# structurally; the binding keeps the protocol import alive so the check
# runs even when nothing in this module consumes it directly.
_PROVIDER_TYPE: type[TranslationProvider] = GeminiTranslationProvider
