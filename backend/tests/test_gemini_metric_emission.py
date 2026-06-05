"""Tests for ``equip.gemini.*`` emission from
``GeminiTranslationProvider.translate``.

Cost visibility is the whole point: ``calls_total`` is what tells us
if we're hammering Gemini, ``tokens_input_total`` / ``tokens_output_total``
fold into Gemini's $/M-token rate to give us $-burn over the
window.

Pinned guarantees:

* One ``calls_total`` increment per network call (success, retry, fatal).
* Token counts emitted via ``emit`` (not ``increment``) so the metric
  value carries the token count itself — Datadog ``sum:`` over the
  window gives cumulative spend.
* Tags include ``model`` so a future flash → pro migration keeps
  cost curves separable.
* Outcome is ``success`` / ``retry`` / ``fatal`` — the dashboard
  should be able to flag a rising retry-rate before it becomes a
  fatal-rate.
"""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import httpx

from app.services.translation.gemini import GeminiTranslationProvider
from app.services.translation.protocol import TranslationRequest

if TYPE_CHECKING:
    import pytest


def _make_provider(client: httpx.Client) -> GeminiTranslationProvider:
    return GeminiTranslationProvider(
        api_key="k",
        model="gemini-flash-latest",
        timeout_seconds=1.0,
        max_output_tokens=256,
        client=client,
    )


def _gemini_success_response(input_tokens: int = 100, output_tokens: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        json={
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": "Translated"}],
                    },
                }
            ],
            "usageMetadata": {
                "promptTokenCount": input_tokens,
                "candidatesTokenCount": output_tokens,
            },
        },
    )


class TestSuccessMetrics:
    def test_emits_calls_total_with_model_tag(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = _gemini_success_response()
        provider = _make_provider(client)
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            provider.translate(
                TranslationRequest(
                    text="Hello",
                    source_locale="en",
                    target_locale="ru",
                    content_kind="text",
                )
            )
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        calls = [m for m in msgs if "equip.gemini.calls_total" in m]
        assert calls, "expected calls_total event"
        assert any("model=gemini-flash-latest" in m for m in calls)
        assert any("outcome=success" in m for m in calls)
        assert any("value=1.0" in m for m in calls)

    def test_token_counts_emitted_as_metric_value(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = _gemini_success_response(input_tokens=42, output_tokens=137)
        provider = _make_provider(client)
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            provider.translate(
                TranslationRequest(
                    text="Hello",
                    source_locale="en",
                    target_locale="ru",
                    content_kind="text",
                )
            )
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        # Token counts ARE the metric value (not 1.0). sum: over the
        # window = cumulative token spend.
        in_events = [m for m in msgs if "equip.gemini.tokens_input_total" in m]
        out_events = [m for m in msgs if "equip.gemini.tokens_output_total" in m]
        assert in_events
        assert out_events
        assert any("value=42.0" in m for m in in_events)
        assert any("value=137.0" in m for m in out_events)

    def test_zero_token_count_does_not_emit(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """If Gemini omits usageMetadata (rare but possible), token
        counts default to 0 — no emit. The cumulative-sum metric
        would otherwise see meaningless 0-valued rows."""
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = httpx.Response(
            status_code=200,
            json={
                "candidates": [{"content": {"parts": [{"text": "Translated"}]}}],
                # No usageMetadata field at all.
            },
        )
        provider = _make_provider(client)
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            provider.translate(
                TranslationRequest(
                    text="Hello",
                    source_locale="en",
                    target_locale="ru",
                    content_kind="text",
                )
            )
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        # calls_total still fires; tokens_*_total skipped.
        assert any("equip.gemini.calls_total" in m for m in msgs)
        assert not any("equip.gemini.tokens_input_total" in m for m in msgs)
        assert not any("equip.gemini.tokens_output_total" in m for m in msgs)


class TestFatalMetrics:
    def test_4xx_emits_fatal_outcome(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """400/401/403 are non-retryable — fired as ``outcome=fatal``
        immediately before raising. Dashboard distinction matters:
        a rising fatal-rate is "credentials / config broken NOW",
        rising retry-rate is "Gemini is rate-limiting us"."""
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = httpx.Response(
            status_code=400,
            text="Bad request",
        )
        provider = _make_provider(client)
        # non-retryable status raises — expected, we only assert on metrics
        with (
            caplog.at_level(logging.INFO, logger="equip.metric"),
            contextlib.suppress(Exception),
        ):
            provider.translate(
                TranslationRequest(
                    text="Hello",
                    source_locale="en",
                    target_locale="ru",
                    content_kind="text",
                )
            )
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        calls = [m for m in msgs if "equip.gemini.calls_total" in m]
        assert calls
        assert any("outcome=fatal" in m and "status_code=400" in m for m in calls)

    def test_transport_error_emits_transport_outcome(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A network-level failure (timeout/connect/DNS) yields no HTTP
        status. Without an emit on this branch a full Gemini outage is
        invisible on the cost/budget dashboard — so it must fire
        outcome=transport status_code=0 (per failed attempt)."""
        client = MagicMock(spec=httpx.Client)
        client.post.side_effect = httpx.ConnectError("name resolution failed")
        provider = _make_provider(client)
        with (
            caplog.at_level(logging.INFO, logger="equip.metric"),
            contextlib.suppress(Exception),
        ):
            provider.translate(
                TranslationRequest(
                    text="Hello",
                    source_locale="en",
                    target_locale="ru",
                    content_kind="text",
                )
            )
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        calls = [m for m in msgs if "equip.gemini.calls_total" in m]
        assert calls
        assert any("outcome=transport" in m and "status_code=0" in m for m in calls)
