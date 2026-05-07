"""Unit tests for the translation pipeline.

The Gemini provider is exercised against a fake ``httpx.MockTransport`` so
nothing leaves the test process. ``settings.GEMINI_API_KEY`` is *not*
mutated globally — we instantiate the provider directly to keep the
factory cache out of the way.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.services.translation import (
    NoopTranslationProvider,
    TranslationError,
    TranslationProvider,
    TranslationRequest,
    compute_source_hash,
)
from app.services.translation.gemini import GeminiTranslationProvider
from app.services.translation.prompt import build_system_prompt, build_user_prompt
from app.services.translation.service import (
    get_translation_provider,
    is_translation_enabled,
    reset_translation_provider_cache,
)

# ---------------------------------------------------------------------------
# Hash
# ---------------------------------------------------------------------------


def test_hash_is_stable_across_whitespace():
    assert compute_source_hash("Hello world") == compute_source_hash("  Hello\n world  ")


def test_hash_changes_when_text_changes():
    assert compute_source_hash("Hello") != compute_source_hash("Hello!")


def test_hash_includes_locale():
    # Same text, different source language — still distinct so a re-author
    # in a new language re-triggers translation.
    assert compute_source_hash("Hello", locale="ru") != compute_source_hash("Hello", locale="en")


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def test_system_prompt_pins_kjv_for_english():
    prompt = build_system_prompt(source_locale="ru", target_locale="en")
    assert "King James" in prompt
    assert "Translate ONLY" in prompt


def test_system_prompt_pins_synodal_for_russian():
    prompt = build_system_prompt(source_locale="en", target_locale="ru")
    assert "Synodal" in prompt


def test_user_prompt_wraps_text_in_fences():
    body = build_user_prompt(text="Acts 1:8", content_kind="plain", context=None)
    assert "===BEGIN===" in body
    assert "===END===" in body
    assert "Acts 1:8" in body


def test_user_prompt_includes_context_hint():
    body = build_user_prompt(text="word", content_kind="title", context="course on Acts")
    assert "course on Acts" in body
    assert "Content kind: title" in body


# ---------------------------------------------------------------------------
# Noop provider + factory
# ---------------------------------------------------------------------------


def test_noop_provider_passes_through():
    provider = NoopTranslationProvider()
    result = provider.translate(TranslationRequest(text="hello", source_locale="ru", target_locale="en"))
    assert result.text == "hello"


def test_factory_returns_noop_when_disabled(monkeypatch):
    reset_translation_provider_cache()
    monkeypatch.setattr("app.services.translation.service.settings.GEMINI_API_KEY", None, raising=False)
    assert is_translation_enabled() is False
    provider = get_translation_provider()
    assert isinstance(provider, NoopTranslationProvider)
    reset_translation_provider_cache()


def test_factory_returns_gemini_when_enabled(monkeypatch):
    reset_translation_provider_cache()
    monkeypatch.setattr("app.services.translation.service.settings.GEMINI_API_KEY", "fake-key", raising=False)
    monkeypatch.setattr("app.services.translation.service.settings.GEMINI_MODEL", "gemini-flash-latest", raising=False)
    monkeypatch.setattr("app.services.translation.service.settings.GEMINI_TIMEOUT_SECONDS", 5.0, raising=False)
    monkeypatch.setattr("app.services.translation.service.settings.GEMINI_MAX_OUTPUT_TOKENS", 256, raising=False)
    try:
        provider = get_translation_provider()
        assert isinstance(provider, GeminiTranslationProvider)
        # Conforms to the structural protocol the service relies on.
        assert isinstance(provider, TranslationProvider)
    finally:
        reset_translation_provider_cache()


# ---------------------------------------------------------------------------
# Gemini provider with a mocked transport
# ---------------------------------------------------------------------------


def _gemini_with(handler: Any) -> GeminiTranslationProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, timeout=5.0)
    return GeminiTranslationProvider(
        api_key="fake-key",
        model="gemini-flash-latest",
        timeout_seconds=5.0,
        max_output_tokens=256,
        max_retries=1,
        client=client,
    )


def test_gemini_returns_translated_text():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "Привет, мир!"}]}}],
                "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 4},
            },
        )

    provider = _gemini_with(handler)
    result = provider.translate(TranslationRequest(text="Hello, world!", source_locale="en", target_locale="ru"))

    assert result.text == "Привет, мир!"
    assert result.input_tokens == 12
    assert result.output_tokens == 4
    assert result.model == "gemini-flash-latest"
    assert "gemini-flash-latest" in captured["url"]
    assert captured["headers"]["x-goog-api-key"] == "fake-key"
    # The system prompt has to be present so prompt-injection rules apply.
    assert "Translate ONLY" in captured["body"]["systemInstruction"]["parts"][0]["text"]


def test_gemini_short_circuits_when_locales_match():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("provider must not call upstream when locales match")

    provider = _gemini_with(handler)
    result = provider.translate(TranslationRequest(text="Hello", source_locale="en", target_locale="en"))
    assert result.text == "Hello"


def test_gemini_retries_on_429_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"error": "rate limited"})
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
        )

    provider = _gemini_with(handler)
    result = provider.translate(TranslationRequest(text="hi", source_locale="en", target_locale="ru"))
    assert result.text == "ok"
    assert calls["n"] == 2


def test_gemini_raises_on_permanent_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad request")

    provider = _gemini_with(handler)
    with pytest.raises(TranslationError):
        provider.translate(TranslationRequest(text="hi", source_locale="en", target_locale="ru"))


def test_gemini_raises_when_no_candidates_returned():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": []})

    provider = _gemini_with(handler)
    with pytest.raises(TranslationError):
        provider.translate(TranslationRequest(text="hi", source_locale="en", target_locale="ru"))


def test_gemini_raises_typed_error_on_malformed_candidate():
    """Non-dict ``candidates[0]`` must surface as a ``TranslationError``,
    not an ``AttributeError`` that takes down the orchestrator batch."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": ["not-a-dict"]})

    provider = _gemini_with(handler)
    with pytest.raises(TranslationError):
        provider.translate(TranslationRequest(text="hi", source_locale="en", target_locale="ru"))


def test_gemini_does_not_close_caller_owned_client():
    """If the caller injected an ``httpx.Client``, the provider must never
    close it — closing a client the caller still owns broke tests in the past."""
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
        )
    )
    client = httpx.Client(transport=transport, timeout=5.0)
    provider = GeminiTranslationProvider(
        api_key="fake-key",
        model="gemini-flash-latest",
        timeout_seconds=5.0,
        max_output_tokens=256,
        client=client,
    )
    provider.close()
    # Caller-owned client must still be usable after provider.close().
    assert client.is_closed is False
    client.close()


def test_gemini_closes_owned_client_via_context_manager():
    """A self-constructed client is released when used as a context manager."""
    with GeminiTranslationProvider(
        api_key="fake-key",
        model="gemini-flash-latest",
        timeout_seconds=5.0,
        max_output_tokens=256,
    ) as provider:
        owned = provider._client
        assert owned.is_closed is False
    assert owned.is_closed is True
