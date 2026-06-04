"""Tests for ``equip.translation.duration_ms`` emission.

Pinned because the Course Engagement dashboard's p50/p95 widget
splits the latency curve by outcome — a sustained gap between
``done`` and ``failed`` distributions is the cue that the failure
path is timing out on Gemini or the YouVersion API. Emission must:

* Fire on every translate_course_content invocation (success + both
  failure branches).
* Carry the outcome tag (done / failed) so the dashboard can split.
* Be non-raising so a metric failure can't break the worker tick.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import patch

from app.api.v1.internal_translation_worker import _emit_translation_duration

if TYPE_CHECKING:
    import pytest


class TestDurationEmission:
    def test_emits_value_in_milliseconds_with_outcome_tag(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Patch monotonic to return a controlled "now" 2.5 seconds
        # after start.
        with (
            patch("app.api.v1.internal_translation_worker.time.monotonic", return_value=12.5),
            caplog.at_level(logging.INFO, logger="equip.metric"),
        ):
            _emit_translation_duration(start_monotonic=10.0, outcome="done")
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        events = [m for m in msgs if "equip.translation.duration_ms" in m]
        assert events, "expected duration_ms event"
        # 2.5 s = 2500 ms.
        assert any("value=2500.0" in m for m in events)
        assert any("outcome=done" in m for m in events)

    def test_failed_outcome_keeps_tag_distinct(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        with (
            patch("app.api.v1.internal_translation_worker.time.monotonic", return_value=5.0),
            caplog.at_level(logging.INFO, logger="equip.metric"),
        ):
            _emit_translation_duration(start_monotonic=4.7, outcome="failed")
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        events = [m for m in msgs if "equip.translation.duration_ms" in m]
        assert events
        assert any("outcome=failed" in m for m in events)
        # ~300 ms (floating-point arithmetic: 5.0 - 4.7 yields
        # 0.29999... so allow a tolerance).
        assert any(("value=29" in m or "value=30" in m) for m in events)

    def test_swallows_emit_failures(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A logger failure on the timing path MUST NOT propagate —
        the worker tick must finish even when Datadog forwarder is
        down."""

        def boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("simulated logger failure")

        # Patch the metrics.timing function (used by the worker) so
        # the call site raises; the worker helper must catch it.
        import app.api.v1.internal_translation_worker as worker_module

        monkeypatch.setattr(worker_module, "timing", boom)

        # No assertion — passes if this call doesn't raise.
        _emit_translation_duration(start_monotonic=0.0, outcome="done")
