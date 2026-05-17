"""Translation provider factory + a pass-through fallback.

Most environments boot without a Gemini key configured (local dev, CI). We
still want the rest of the service to import the translation module without
raising, so ``get_translation_provider()`` returns a ``NoopTranslationProvider``
that simply echoes the source text. Callers can branch on
``is_translation_enabled()`` if they need to refuse to publish a course
when no real provider is wired up.

Caching strategy: we keep one provider per process (so the underlying
``httpx.Client`` connection pool is reused on warm serverless invocations),
but key the cache on the *current* settings tuple — API key, model,
timeout, max-output-tokens. When any of those change (e.g. the operator
rotates ``GEMINI_API_KEY`` in Vercel and the worker is warm-restarted into
the new env), the next call rebuilds the provider with the fresh values
instead of holding onto the dead key for the worker's lifetime.
"""

from __future__ import annotations

import logging
import threading

from app.core.config import settings
from app.services.translation.protocol import (
    TranslationProvider,
    TranslationRequest,
    TranslationResult,
)

logger = logging.getLogger(__name__)


class NoopTranslationProvider:
    """Return the source text unchanged. Safe default when Gemini is off."""

    name = "noop"

    def translate(self, request: TranslationRequest) -> TranslationResult:
        return TranslationResult(text=request.text, model="noop")

    def translate_batch(self, requests: list[TranslationRequest]) -> list[TranslationResult]:
        return [self.translate(req) for req in requests]


def _api_key_value() -> str | None:
    """Return the configured Gemini API key as a plain string (or ``None``).

    Pydantic stores it as ``SecretStr | None``; the rest of the pipeline
    expects a regular string at the call site. Centralising the unwrap means
    every other module reads the key the same way.
    """
    raw = getattr(settings, "GEMINI_API_KEY", None)
    if raw is None:
        return None
    # ``SecretStr.get_secret_value()`` returns ``""`` for an empty secret;
    # treat that as "not configured" so we degrade to the noop provider.
    value = raw.get_secret_value() if hasattr(raw, "get_secret_value") else str(raw)
    return value or None


def is_translation_enabled() -> bool:
    """Cheap predicate the API/UI can call to gate translation features."""
    return _api_key_value() is not None


# Cache key includes every setting that influences provider construction.
# When any of these mutate (e.g. an env-var rotation between requests on a
# warm serverless instance) the next call detects the mismatch and rebuilds.
_ProviderCacheKey = tuple[str | None, str, float, int, float]


def _current_cache_key() -> _ProviderCacheKey:
    return (
        _api_key_value(),
        settings.GEMINI_MODEL,
        settings.GEMINI_TIMEOUT_SECONDS,
        settings.GEMINI_MAX_OUTPUT_TOKENS,
        settings.GEMINI_MIN_INTERVAL_SECONDS,
    )


_cache_lock = threading.Lock()
_cached_key: _ProviderCacheKey | None = None
_cached_provider: TranslationProvider | None = None


def get_translation_provider() -> TranslationProvider:
    """Return the configured provider, rebuilding when settings change.

    Thread-safe: a lock guards the (key, provider) pair so two workers
    racing on cold start don't construct two ``httpx.Client``s.
    """
    global _cached_key, _cached_provider

    key = _current_cache_key()
    cached = _cached_provider
    if cached is not None and _cached_key == key:
        return cached

    with _cache_lock:
        if _cached_provider is not None and _cached_key == key:
            return _cached_provider

        api_key = key[0]
        if api_key is None:
            logger.info("Translation provider not configured — using NoopTranslationProvider")
            provider: TranslationProvider = NoopTranslationProvider()
        else:
            # Imported lazily so environments without ``httpx`` (e.g. tooling)
            # can still touch this module.
            from app.services.translation.gemini import GeminiTranslationProvider

            # If we're rotating to a new key, release the stale provider's
            # HTTP client before swapping in the new one — otherwise warm
            # workers leak a connection pool per rotation.
            previous = _cached_provider
            if previous is not None:
                _close_if_possible(previous)

            provider = GeminiTranslationProvider(
                api_key=api_key,
                model=settings.GEMINI_MODEL,
                timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
                max_output_tokens=settings.GEMINI_MAX_OUTPUT_TOKENS,
                min_interval_seconds=settings.GEMINI_MIN_INTERVAL_SECONDS,
            )

        _cached_provider = provider
        _cached_key = key
        return provider


def _close_if_possible(provider: TranslationProvider) -> None:
    """Best-effort close of a provider's resources on cache eviction."""
    closer = getattr(provider, "close", None)
    if callable(closer):
        try:
            closer()
        except Exception:
            # close() must never propagate during cache eviction.
            logger.debug("Translation provider close() failed", exc_info=True)


def reset_translation_provider_cache() -> None:
    """Test-only hook: clear the cached provider.

    The pipeline is exercised in unit tests with monkeypatched settings; if
    we don't reset the cache between tests the first one to hit the factory
    pins a stale provider.
    """
    global _cached_key, _cached_provider
    with _cache_lock:
        previous = _cached_provider
        _cached_key = None
        _cached_provider = None
    if previous is not None:
        _close_if_possible(previous)
