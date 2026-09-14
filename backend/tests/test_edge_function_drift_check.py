"""The drift check that guards the edge function's deploy.

The check itself lives in `.github/scripts/edge_function_drift.py` because
it runs in CI, not in the app — but its logic decides whether anybody is
told that production is sending email from code older than main, so it is
tested here with the rest of the suite rather than trusted.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "edge_function_drift.py"


def _load():
    spec = importlib.util.spec_from_file_location("edge_function_drift", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


drift = _load()


def _utc(*args: int) -> dt.datetime:
    return dt.datetime(*args, tzinfo=dt.UTC)


class TestIsDrifted:
    def test_source_newer_than_deploy_is_drift(self):
        """The 2026-09-01 case: fixes merged, function never redeployed."""
        assert drift.is_drifted(source_changed_at=_utc(2026, 9, 1, 12), deployed_at=_utc(2026, 8, 20, 9))

    def test_deploy_newer_than_source_is_fine(self):
        assert not drift.is_drifted(source_changed_at=_utc(2026, 8, 20, 9), deployed_at=_utc(2026, 9, 1, 12))

    def test_same_instant_is_in_sync(self):
        """A deploy landing in the same second as the commit is the good case."""
        same = _utc(2026, 9, 13, 2, 55)
        assert not drift.is_drifted(source_changed_at=same, deployed_at=same)

    def test_one_second_of_drift_still_counts(self):
        assert drift.is_drifted(
            source_changed_at=_utc(2026, 9, 13, 2, 55, 1),
            deployed_at=_utc(2026, 9, 13, 2, 55, 0),
        )

    def test_comparison_survives_mixed_offsets(self):
        """Deploy time arrives as UTC epoch, git as a local ISO offset."""
        source_local = dt.datetime(2026, 9, 13, 22, 55, tzinfo=dt.timezone(dt.timedelta(hours=-4))).astimezone(dt.UTC)
        deployed = _utc(2026, 9, 14, 3, 0)
        assert not drift.is_drifted(source_changed_at=source_local, deployed_at=deployed)


class TestParseDeployedAt:
    def test_reads_epoch_milliseconds(self):
        """What the Management API actually returns today."""
        got = drift.parse_deployed_at({"updated_at": 1789354500000})
        assert got == dt.datetime.fromtimestamp(1789354500, tz=dt.UTC)
        assert got.tzinfo is dt.UTC

    def test_tolerates_iso_8601(self):
        """Defensive: the field is documented as a timestamp, not as epoch ms."""
        got = drift.parse_deployed_at({"updated_at": "2026-09-13T02:55:00Z"})
        assert got == _utc(2026, 9, 13, 2, 55)

    def test_missing_field_is_an_error_not_a_silent_pass(self):
        with pytest.raises(ValueError):
            drift.parse_deployed_at({"version": 16})


class TestFreshnessWindow:
    def test_window_is_generous_enough_for_a_slow_runner(self):
        """A CI deploy takes minutes; the window must not fail an honest one."""
        assert drift.FRESH_DEPLOY_MAX_AGE_SECONDS >= 5 * 60

    def test_window_is_tight_enough_to_catch_a_no_op_deploy(self):
        """Yesterday's deploy must not read as 'fresh' after today's run."""
        assert drift.FRESH_DEPLOY_MAX_AGE_SECONDS < 24 * 60 * 60
