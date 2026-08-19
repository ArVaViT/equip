"""``scripts/apply_datadog_monitors.py`` must be safe to run twice.

The whole point of the script is that the owner can run it the moment a
write-scoped key exists, and then again whenever a file changes, without
thinking about it. That only holds if the second run is silent: a script
that reports drift on every invocation trains the reader to ignore its
output, which is the same failure as having no monitors at all — just
noisier.

Two things make a false diff easy here. Datadog echoes ``10`` back as
``10.0``, and it fills in options the committed file never mentioned.
Both are tested below against the shapes the real API returned on
2026-08-19.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from scripts.apply_datadog_monitors import (
    MONITORS_DIR,
    SpecError,
    apply_one,
    diff_spec,
    index_by_name,
    is_blocked,
    load_specs,
    payload_for,
    resolve_site,
)

A_SPEC: dict[str, Any] = {
    "name": "[Equip] Gemini calls are failing",
    "type": "metric alert",
    "query": "sum(last_30m):sum:equip.gemini.calls_total{outcome:transport}.as_count() > 20",
    "message": "The translation provider is refusing or timing out.",
    "tags": ["env:production", "project:equip"],
    "priority": 2,
    "options": {
        "evaluation_delay": 120,
        "thresholds": {"warning": 10, "critical": 20},
        "notify_no_data": False,
    },
}


def _write(tmp_path: Any, filename: str, spec: dict[str, Any]) -> None:
    (tmp_path / filename).write_text(json.dumps(spec), encoding="utf-8")


class TestTheSecondRunIsQuiet:
    def test_a_monitor_that_already_matches_produces_no_diff(self) -> None:
        assert diff_spec(A_SPEC, dict(A_SPEC)) == []

    def test_a_threshold_echoed_back_as_a_float_is_not_a_change(self) -> None:
        live = json.loads(json.dumps(A_SPEC))
        live["options"]["thresholds"] = {"warning": 10.0, "critical": 20.0}
        assert diff_spec(A_SPEC, live) == []

    def test_tags_in_another_order_are_not_a_change(self) -> None:
        live = json.loads(json.dumps(A_SPEC))
        live["tags"] = ["project:equip", "env:production"]
        assert diff_spec(A_SPEC, live) == []

    def test_options_datadog_added_by_itself_are_not_a_change(self) -> None:
        # Every Datadog release grows the options object. A strict
        # comparison would call each new default "drift" forever.
        live = json.loads(json.dumps(A_SPEC))
        live["options"].update({"notify_by": [], "on_missing_data": "default", "silenced": {}})
        assert diff_spec(A_SPEC, live) == []

    def test_runtime_fields_datadog_returns_are_not_a_change(self) -> None:
        live = json.loads(json.dumps(A_SPEC))
        live.update({"id": 20465339, "overall_state": "OK", "creator": {"name": "Vadym Arnaut"}})
        assert diff_spec(A_SPEC, live) == []


class TestARealChangeIsReported:
    def test_a_retuned_threshold_shows_both_values(self) -> None:
        live = json.loads(json.dumps(A_SPEC))
        live["options"]["thresholds"]["critical"] = 2000000
        report = "\n".join(diff_spec(A_SPEC, live))
        assert "options:" in report
        assert "2000000" in report

    def test_a_rewritten_query_shows_up(self) -> None:
        live = json.loads(json.dumps(A_SPEC))
        live["query"] = "sum(last_30m):sum:equip.gemini.calls_total{*}.as_count() > 20"
        assert any(line.strip().startswith("query:") for line in diff_spec(A_SPEC, live))

    def test_a_missing_option_on_the_live_monitor_shows_up(self) -> None:
        live = json.loads(json.dumps(A_SPEC))
        del live["options"]["evaluation_delay"]
        assert diff_spec(A_SPEC, live) != []


class TestLoadingTheDirectory:
    def test_two_files_cannot_claim_one_monitor_name(self, tmp_path: Any) -> None:
        _write(tmp_path, "a.json", A_SPEC)
        _write(tmp_path, "b.json", A_SPEC)
        with pytest.raises(SpecError, match="already claimed"):
            load_specs(tmp_path)

    def test_a_spec_without_a_name_is_refused(self, tmp_path: Any) -> None:
        _write(tmp_path, "a.json", {"query": "x", "type": "metric alert"})
        with pytest.raises(SpecError, match="name"):
            load_specs(tmp_path)

    def test_a_spec_without_a_query_is_refused(self, tmp_path: Any) -> None:
        _write(tmp_path, "a.json", {"name": "x", "type": "metric alert"})
        with pytest.raises(SpecError, match="query"):
            load_specs(tmp_path)

    def test_broken_json_names_the_file(self, tmp_path: Any) -> None:
        (tmp_path / "a.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(SpecError, match=r"a\.json"):
            load_specs(tmp_path)

    def test_every_committed_monitor_parses(self) -> None:
        # The sentinel that matters: a malformed file in the real
        # directory would otherwise only be discovered on the day
        # somebody finally runs the apply.
        specs = load_specs(MONITORS_DIR)
        assert len(specs) >= 12
        assert all(spec["name"] for _, spec in specs)


class TestABlockedMonitorStaysInert:
    def test_a_message_opening_with_blocked_is_recognised(self) -> None:
        assert is_blocked({"message": "BLOCKED — DO NOT IMPORT YET. The metric does not exist."})

    def test_the_word_blocked_further_in_is_not_a_marker(self) -> None:
        # ``edits-held-too-long`` explains at length that edits are
        # *blocked*; that is the subject matter, not a directive.
        assert not is_blocked({"message": "Edits a teacher has made are held back — BLOCKED on translation."})

    def test_a_spec_with_no_message_is_not_blocked(self) -> None:
        assert not is_blocked({"name": "x"})


class TestTheSite:
    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("us5", "us5.datadoghq.com"),
            ("us5.datadoghq.com", "us5.datadoghq.com"),
            ("  us5  ", "us5.datadoghq.com"),
            ("datadoghq.eu", "datadoghq.eu"),
            (None, "us5.datadoghq.com"),
            ("", "us5.datadoghq.com"),
        ],
    )
    def test_it_is_accepted_written_either_way(self, given: str | None, expected: str) -> None:
        # A wrong host fails as a 403, which reads exactly like a scope
        # problem and sends the reader looking in the wrong place.
        assert resolve_site(given) == expected


class TestThePayload:
    def test_a_pasted_id_is_not_sent_back(self) -> None:
        # A UI export carries ``id``; posting it would either be
        # rejected or, worse, silently retarget the call.
        spec = dict(A_SPEC) | {"id": 20465339, "overall_state": "OK"}
        assert "id" not in payload_for(spec)
        assert "overall_state" not in payload_for(spec)

    def test_it_carries_what_the_file_mirrors(self) -> None:
        assert set(payload_for(A_SPEC)) == {"name", "type", "query", "message", "tags", "priority", "options"}


class TestApplyingAgainstAFakeDatadog:
    """End-to-end over ``apply_one`` with a stub transport: create the
    monitor, feed the result back as the live state, and require the
    second pass to be silent."""

    @staticmethod
    def _client(created: list[dict[str, Any]]) -> httpx.Client:
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            # Datadog answers with an id and with float thresholds —
            # both of which the second run must forgive.
            echoed = json.loads(json.dumps(body)) | {"id": 100 + len(created), "overall_state": "No Data"}
            echoed.setdefault("options", {}).setdefault("silenced", {})
            created.append(echoed)
            return httpx.Response(200, json=echoed)

        return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.us5.datadoghq.com")

    def test_the_first_run_creates_and_the_second_changes_nothing(self) -> None:
        created: list[dict[str, Any]] = []
        with self._client(created) as client:
            verdict, _ = apply_one(client, MONITORS_DIR / "a.json", A_SPEC, {}, write=True)
            assert verdict == "CREATE"

            live_by_name = index_by_name(created)
            verdict, lines = apply_one(client, MONITORS_DIR / "a.json", A_SPEC, live_by_name, write=True)
        assert verdict == "UNCHANGED"
        assert lines == []
        assert len(created) == 1

    def test_a_dry_run_writes_nothing(self) -> None:
        created: list[dict[str, Any]] = []
        with self._client(created) as client:
            verdict, _ = apply_one(client, MONITORS_DIR / "a.json", A_SPEC, {}, write=False)
        assert verdict == "CREATE"
        assert created == []

    def test_a_changed_file_updates_the_existing_monitor(self) -> None:
        created: list[dict[str, Any]] = []
        with self._client(created) as client:
            apply_one(client, MONITORS_DIR / "a.json", A_SPEC, {}, write=True)
            retuned = json.loads(json.dumps(A_SPEC))
            retuned["options"]["thresholds"]["critical"] = 50
            verdict, _ = apply_one(client, MONITORS_DIR / "a.json", retuned, index_by_name(created), write=True)
        assert verdict == "UPDATE"

    def test_a_blocked_spec_is_skipped_without_a_request(self) -> None:
        created: list[dict[str, Any]] = []
        blocked = dict(A_SPEC) | {"message": "BLOCKED — the metric does not exist."}
        with self._client(created) as client:
            verdict, _ = apply_one(client, MONITORS_DIR / "a.json", blocked, {}, write=True)
        assert verdict == "SKIPPED"
        assert created == []

    def test_two_live_monitors_with_one_name_are_not_guessed_at(self) -> None:
        created: list[dict[str, Any]] = []
        twins = [dict(A_SPEC) | {"id": 1}, dict(A_SPEC) | {"id": 2}]
        with self._client(created) as client:
            verdict, lines = apply_one(client, MONITORS_DIR / "a.json", A_SPEC, index_by_name(twins), write=True)
        assert verdict == "FAILED"
        assert "share this name" in "\n".join(lines)
        assert created == []
