"""Doing nothing must not look like doing well.

Every metric this pipeline had described the *queue*: depth, processing,
failed_permanent, duration. None described output. So a worker that
claimed a job, walked a thousand fields, wrote none of them and reported
"done" produced exactly the same telemetry as a worker with nothing to
do — empty queue, healthy duration, no warnings. Production span that
way for an hour on 2026-08-19 and the only thing that noticed was a
person reading a database.

The counters existed the whole time; they went to one INFO line, which
the Datadog index drops, and to an HTTP response body nobody reads.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.api.v1.internal_translation_worker import _emit_field_outcomes
from app.services.translation.orchestrator import OrchestratorReport


@pytest.fixture
def emitted():
    with patch("app.api.v1.internal_translation_worker.emit") as emit:
        yield emit


def _tags(emit) -> dict[str, float]:
    return {call.kwargs["outcome"]: call.args[1] for call in emit.call_args_list}


class TestTheTickReportsWhatItMoved:
    def test_each_outcome_is_its_own_series(self, emitted) -> None:
        _emit_field_outcomes(OrchestratorReport(translated=12, skipped=800, failed=1, needs_review=2))
        assert _tags(emitted) == {
            "translated": 12.0,
            "skipped": 800.0,
            "failed": 1.0,
            "needs_review": 2.0,
        }

    def test_the_metric_name_is_stable(self, emitted) -> None:
        _emit_field_outcomes(OrchestratorReport(translated=1))
        assert emitted.call_args_list[0].args[0] == "equip.translation.fields_total"

    def test_the_hour_of_doing_nothing_is_expressible(self, emitted) -> None:
        # The exact production shape: a full plan, every field skipped,
        # nothing translated. "translated is flat while skipped is not"
        # is now a condition a monitor can be written against.
        _emit_field_outcomes(OrchestratorReport(translated=0, skipped=810))
        recorded = _tags(emitted)
        assert recorded == {"skipped": 810.0}
        assert "translated" not in recorded

    def test_a_metric_failure_never_reaches_the_worker(self) -> None:
        with patch(
            "app.api.v1.internal_translation_worker.emit",
            side_effect=RuntimeError("datadog is down"),
        ):
            _emit_field_outcomes(OrchestratorReport(translated=5))  # must not raise
