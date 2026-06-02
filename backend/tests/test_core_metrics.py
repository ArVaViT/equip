"""Tests for ``app.core.metrics``.

Pins the wire format that the Datadog log-based metrics queries
depend on (the JSON specs in ``docs/datadog/*.json``). A regression
that changes the shape of these log lines silently breaks every
dashboard.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core import metrics

if TYPE_CHECKING:
    import pytest


class TestEmit:
    def test_emit_logs_metric_name_and_value(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            metrics.emit("equip.grading.pending", 5.0)
        records = [r for r in caplog.records if r.name == "equip.metric"]
        assert len(records) == 1
        msg = records[0].getMessage()
        # The log shape is what the Datadog query parses; do not
        # break the prefix / value=N pattern.
        assert msg.startswith("equip.grading.pending")
        assert "value=5.0" in msg

    def test_emit_with_tags_renders_key_value_pairs(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            metrics.emit(
                "equip.completion.course_avg_pct",
                73.5,
                course_id="abc-123",
                locale="ru",
            )
        msg = caplog.records[-1].getMessage()
        assert "course_id=abc-123" in msg
        assert "locale=ru" in msg

    def test_emit_drops_none_and_empty_tags(self, caplog: pytest.LogCaptureFixture) -> None:
        """Empty / None tags must not produce ``key=`` noise — the
        Datadog parser treats that as a malformed attribute."""
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            metrics.emit(
                "equip.activity.requests_total",
                1.0,
                course_id="c-1",
                teacher_id=None,
                locale="",
            )
        msg = caplog.records[-1].getMessage()
        assert "course_id=c-1" in msg
        assert "teacher_id" not in msg
        assert "locale=" not in msg

    def test_emit_never_raises_on_logging_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If the underlying logger fails, the caller's request must
        NOT see an exception bubble up. Pin the swallow path."""

        def boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("simulated logger failure")

        monkeypatch.setattr(metrics.logger, "info", boom)
        # No assertion — the test passes if this call doesn't raise.
        metrics.emit("equip.test.never_raises", 1.0)


class TestConveniences:
    def test_increment_emits_value_one(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            metrics.increment("equip.activity.requests_total")
        assert "value=1.0" in caplog.records[-1].getMessage()

    def test_gauge_emits_named_value(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            metrics.gauge("equip.grading.pending", 42.0, teacher_id="t-1")
        msg = caplog.records[-1].getMessage()
        assert "value=42.0" in msg
        assert "teacher_id=t-1" in msg

    def test_timing_emits_milliseconds(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            metrics.timing("equip.grading.time_to_grade.p50", 172800000.0)
        assert "value=172800000.0" in caplog.records[-1].getMessage()
