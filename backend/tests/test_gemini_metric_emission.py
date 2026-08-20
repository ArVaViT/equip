"""Tests for ``equip.gemini.*`` emission from
``GeminiTranslationProvider`` — both of the calls it makes.

Cost visibility is the whole point: ``calls_total`` is what tells us
if we're hammering Gemini, ``tokens_input_total`` / ``tokens_output_total``
fold into Gemini's $/M-token rate to give us $-burn over the
window.

Pinned guarantees:

* One ``calls_total`` increment per network call — the review call
  included, in both directions. Until 2026-08-20 the reviewer emitted a
  bare count on success and nothing at all on failure, while running a
  model that bills 6.25x the translator on output and made up about half
  of a rebuild's cost.
* Token counts emitted via ``emit`` (not ``increment``) so the metric
  value carries the token count itself — Datadog ``sum:`` over the
  window gives cumulative spend. From the review path as well as the
  translate path.
* Tags include ``model`` so a future flash → pro migration keeps
  cost curves separable, and ``role`` so translation and review stay
  separable even in a deployment where both run the same model id.
* The ``outcome`` vocabulary carries the whole diagnosis, because
  ``status_code`` does not survive into Datadog: a 429 says
  ``rate_limited``, a transient 5xx says ``retry``, a shut door
  (401/403/404) says ``unavailable`` and a rejected payload (400/413)
  says ``rejected``. The last two used to share the name ``fatal``.
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


class TestTheOutcomeTagSaysWhatWentWrong:
    """``outcome`` has to carry the diagnosis on its own.

    ``status_code`` is emitted on every branch and is not queryable: the
    log-based metric rule for ``equip.gemini.calls_total`` groups by
    ``model`` and ``outcome`` only, so every series in production comes
    back ``status_code:N/A`` — checked across thirty days on 2026-08-20.
    A value that reaches Datadog and dies there cannot be the thing that
    distinguishes a spent balance from a busy model.
    """

    def _outcomes_for(self, response: httpx.Response, caplog: pytest.LogCaptureFixture) -> list[str]:
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = response
        provider = _make_provider(client)
        # A failing status raises — expected, we only assert on metrics.
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
        return [r.getMessage() for r in caplog.records if "equip.gemini.calls_total" in r.getMessage()]

    def test_a_spent_balance_is_not_filed_under_the_same_name_as_a_busy_model(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """The one that cost a day of not knowing.

        On 2026-08-19 ``outcome:retry`` went from nothing to 1,685 in an
        hour while successes collapsed, and the metric could not say
        whether the prepaid balance had run out or the model was busy.
        Both are 429-or-5xx and both were called ``retry``. A 429 is the
        money one — a quota or a loop of ours — so it gets its own name.
        """
        rate_limited = self._outcomes_for(httpx.Response(status_code=429, text="RESOURCE_EXHAUSTED"), caplog)
        assert rate_limited
        assert all("outcome=rate_limited" in m for m in rate_limited)
        assert any("status_code=429" in m for m in rate_limited)

        caplog.clear()
        overloaded = self._outcomes_for(httpx.Response(status_code=503, text="overloaded"), caplog)
        assert overloaded
        assert all("outcome=retry" in m for m in overloaded)
        assert not any("rate_limited" in m for m in overloaded)

    def test_a_shut_door_and_a_refused_payload_no_longer_share_a_name(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """``fatal`` used to mean both, and only one of them is our text.

        This is the split ``protocol.py`` already draws —
        ``TranslationUnavailable`` for a provider that could not answer,
        ``TranslationError`` for one that looked at this request and
        refused it — carried into the tag rather than invented again.
        """
        shut = self._outcomes_for(httpx.Response(status_code=403, text="billing disabled"), caplog)
        assert any("outcome=unavailable" in m and "status_code=403" in m for m in shut)

        caplog.clear()
        refused = self._outcomes_for(httpx.Response(status_code=400, text="Bad request"), caplog)
        assert any("outcome=rejected" in m and "status_code=400" in m for m in refused)

    def test_the_word_fatal_is_gone_from_the_vocabulary(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Nothing may still emit it, or the monitor scope would have to
        carry a name that means two different things."""
        for response in (
            httpx.Response(status_code=400, text="Bad request"),
            httpx.Response(status_code=403, text="no"),
            httpx.Response(status_code=404, text="no such model"),
        ):
            caplog.clear()
            assert not any("outcome=fatal" in m for m in self._outcomes_for(response, caplog))

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


def _review_response(
    *,
    input_tokens: int = 900,
    output_tokens: int = 60,
    thinking_tokens: int | None = None,
) -> httpx.Response:
    usage: dict[str, int] = {
        "promptTokenCount": input_tokens,
        "candidatesTokenCount": output_tokens,
    }
    if thinking_tokens is not None:
        usage["thoughtsTokenCount"] = thinking_tokens
    return httpx.Response(
        status_code=200,
        json={
            "candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}],
            "usageMetadata": usage,
        },
    )


def _reviewing_provider(client: httpx.Client) -> GeminiTranslationProvider:
    return GeminiTranslationProvider(
        api_key="k",
        model="gemini-2.5-flash-lite",
        review_model="gemini-3.5-flash-lite",
        timeout_seconds=1.0,
        max_output_tokens=256,
        client=client,
    )


def _review(provider: GeminiTranslationProvider) -> None:
    provider.review(
        source="Hello",
        translation="Привет",
        source_locale="en",
        target_locale="ru",
        content_kind="plain",
    )


class TestTheReviewerBillIsVisible:
    """The half of the bill nobody could see.

    Measured 2026-08-20 over thirty days of production: 1,756 review
    calls in ``equip.gemini.calls_total{outcome:review}`` and not one
    matching point in either token metric — a query grouped by ``model``
    returned ``gemini-2.5-flash-lite`` and ``gemini-flash-latest`` and
    never the reviewer's ``gemini-3.5-flash-lite``. The reviewer costs
    $0.30/M in and $2.50/M out against the translator's $0.10 and $0.40,
    and made up roughly 52% of a full rebuild.
    """

    def test_the_review_call_reports_what_it_spent(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = _review_response(input_tokens=911, output_tokens=57)
        provider = _reviewing_provider(client)
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            _review(provider)
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        assert any("equip.gemini.tokens_input_total" in m and "value=911.0" in m for m in msgs)
        assert any("equip.gemini.tokens_output_total" in m and "value=57.0" in m for m in msgs)

    def test_the_reviewers_spend_is_tagged_with_the_reviewers_model(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Otherwise the two models' curves add up into one number, and
        the expensive one hides inside the cheap one's total."""
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = _review_response()
        provider = _reviewing_provider(client)
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            _review(provider)
        tokens = [r.getMessage() for r in caplog.records if "equip.gemini.tokens_" in r.getMessage()]
        assert tokens
        assert all("model=gemini-3.5-flash-lite" in m for m in tokens)
        assert all("role=review" in m for m in tokens)

    def test_a_deployment_with_one_model_for_both_jobs_can_still_tell_them_apart(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """``review_model`` defaults to the translating model. There the
        ``model`` tag is the same string on both calls, and ``role`` is
        the only thing left that separates a $0.10 translation from a
        $0.30 review of it."""
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
        client.post.return_value = _review_response()
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            _review(provider)
        tokens = [r.getMessage() for r in caplog.records if "equip.gemini.tokens_" in r.getMessage()]
        assert any("role=translate" in m for m in tokens)
        assert any("role=review" in m for m in tokens)

    def test_a_thinking_reviewer_shows_up_the_same_hour(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Thinking tokens bill as output — at the reviewer's rate, that
        is $2.50 per million for text nobody ever reads. Emitted always,
        including as zero, so the series exists before it is needed."""
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = _review_response(thinking_tokens=840)
        provider = _reviewing_provider(client)
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            _review(provider)
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        assert any("equip.gemini.tokens_thinking_total" in m and "value=840.0" in m for m in msgs)

        caplog.clear()
        client.post.return_value = _review_response()
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            _review(provider)
        quiet = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        assert any("equip.gemini.tokens_thinking_total" in m and "value=0.0" in m for m in quiet)

    def test_a_reviewer_that_refuses_every_call_is_not_silence(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """A review model id that no longer exists answers 404 to
        everything, turns review off across the whole pipeline, and used
        to emit nothing whatsoever — indistinguishable from a pipeline
        with no reviewer configured."""
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = httpx.Response(status_code=404, text="model not found")
        provider = _reviewing_provider(client)
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            _review(provider)
        calls = [r.getMessage() for r in caplog.records if "equip.gemini.calls_total" in r.getMessage()]
        assert any("outcome=review_failed" in m and "status_code=404" in m for m in calls)

    def test_a_reviewer_that_cannot_be_reached_is_not_silence_either(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        client = MagicMock(spec=httpx.Client)
        client.post.side_effect = httpx.ConnectError("name resolution failed")
        provider = _reviewing_provider(client)
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            _review(provider)
        calls = [r.getMessage() for r in caplog.records if "equip.gemini.calls_total" in r.getMessage()]
        assert any("outcome=review_failed" in m and "status_code=0" in m for m in calls)

    def test_a_successful_review_still_counts_under_its_own_name(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """``outcome:review`` is thirty days of history and the only
        thing that separates review calls from translation calls in a
        metric whose ``role`` tag Datadog currently drops."""
        client = MagicMock(spec=httpx.Client)
        client.post.return_value = _review_response()
        provider = _reviewing_provider(client)
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            _review(provider)
        calls = [r.getMessage() for r in caplog.records if "equip.gemini.calls_total" in r.getMessage()]
        assert any("outcome=review" in m and "model=gemini-3.5-flash-lite" in m for m in calls)
