"""Coverage tests for the thin edges of
``app.services.translation.gemini.GeminiTranslationProvider``.

The existing ``test_translation_orchestrator.py`` and friends stub
``translate()`` end-to-end. This file pins the constructor guard +
the short-circuits inside ``translate()`` that the e2e tests don't
exercise.
"""

from __future__ import annotations

import pytest

from app.services.translation.gemini import GeminiTranslationProvider
from app.services.translation.protocol import TranslationRequest


class TestConstructorGuards:
    def test_empty_api_key_raises_value_error(self) -> None:
        """An empty ``api_key`` is a config bug — silently swallowing
        it would leave us calling Gemini unauthenticated. Pin the
        loud failure."""
        with pytest.raises(ValueError) as exc:
            GeminiTranslationProvider(
                api_key="",
                model="gemini-2.5-flash-lite",
                timeout_seconds=30.0,
                max_output_tokens=4096,
            )
        assert "non-empty api_key" in str(exc.value)


class TestTranslateShortCircuits:
    """The first two checks in ``translate()`` cheap-short-circuit
    without hitting the network: same source/target locale, and
    empty/whitespace text. Both return a passthrough
    ``TranslationResult`` so the caller's flow is uniform.
    """

    def test_same_source_and_target_returns_input_unchanged(self) -> None:
        provider = GeminiTranslationProvider(
            api_key="k",
            model="gemini-2.5-flash-lite",
            timeout_seconds=1.0,
            max_output_tokens=256,
        )
        try:
            result = provider.translate(
                TranslationRequest(
                    text="Hello",
                    source_locale="en",
                    target_locale="en",
                    content_kind="text",
                )
            )
            assert result.text == "Hello"
            assert result.model == "gemini-2.5-flash-lite"
        finally:
            provider.close()

    def test_blank_text_returns_input_unchanged(self) -> None:
        provider = GeminiTranslationProvider(
            api_key="k",
            model="gemini-2.5-flash-lite",
            timeout_seconds=1.0,
            max_output_tokens=256,
        )
        try:
            result = provider.translate(
                TranslationRequest(
                    text="   ",
                    source_locale="en",
                    target_locale="ru",
                    content_kind="text",
                )
            )
            # Passes the input through; doesn't issue a Gemini call.
            assert result.text == "   "
        finally:
            provider.close()


class TestExternalClientOwnership:
    def test_external_client_not_closed_by_provider(self) -> None:
        """Caller-injected ``httpx.Client`` instances must NOT be
        closed by ``provider.close()`` — the caller owns the lifecycle
        (e.g. a shared client across a batch script). Pin the
        ``_owns_client`` flag's effect."""

        class _Recorder:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        external = _Recorder()
        provider = GeminiTranslationProvider(
            api_key="k",
            model="gemini-2.5-flash-lite",
            timeout_seconds=1.0,
            max_output_tokens=256,
            client=external,  # type: ignore[arg-type]
        )
        provider.close()
        assert external.closed is False

    def test_owned_client_is_closed(self) -> None:
        provider = GeminiTranslationProvider(
            api_key="k",
            model="gemini-2.5-flash-lite",
            timeout_seconds=1.0,
            max_output_tokens=256,
        )

        class _Recorder:
            def __init__(self) -> None:
                self.closed = False

            def close(self) -> None:
                self.closed = True

        external = _Recorder()
        provider._client = external  # type: ignore[assignment]
        provider._owns_client = True
        provider.close()
        assert external.closed is True
