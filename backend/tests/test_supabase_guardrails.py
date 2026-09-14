"""The two guardrails standing between the Supabase project and silent rot.

Both scripts run in CI rather than in the app, and both encode judgement
that cost this project real incidents — so the judgement is tested here
rather than trusted.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    path = ROOT / ".github" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


advisors = _load("supabase_advisors")
auth_config = _load("supabase_auth_config")


def finding(name: str, level: str = "WARN", table: str | None = None) -> dict:
    out: dict = {"name": name, "level": level, "detail": f"{name} detail"}
    if table:
        out["metadata"] = {"name": table, "schema": "public"}
    return out


class TestUnindexedForeignKeys:
    """The 2026-09-13 case: 17 findings, every table empty."""

    def test_empty_table_is_not_worth_an_index(self):
        assert not advisors.should_report(
            finding("unindexed_foreign_keys", "INFO", "grade_sheets"),
            {"grade_sheets": 0},
        )

    def test_same_finding_matters_once_the_table_is_big(self):
        assert advisors.should_report(
            finding("unindexed_foreign_keys", "INFO", "grade_sheets"),
            {"grade_sheets": 50_000},
        )

    def test_threshold_is_a_floor_not_a_guess(self):
        f = finding("unindexed_foreign_keys", "INFO", "t")
        assert not advisors.should_report(f, {"t": advisors.ROW_THRESHOLD - 1})
        assert advisors.should_report(f, {"t": advisors.ROW_THRESHOLD})

    def test_table_missing_from_sizes_we_did_read_is_reported(self):
        """We could measure and it was not there — that deserves a look."""
        assert advisors.should_report(finding("unindexed_foreign_keys", "INFO", "mystery"), {})

    def test_rule_is_skipped_when_sizes_could_not_be_read_at_all(self):
        """
        The CI run on 2026-09-14: `supabase db query` failed silently, sizes came
        back empty, and the gate fired seventeen lines nobody could act on. A gate
        that cries wolf gets muted, so it now says it could not measure instead.
        """
        assert not advisors.should_report(finding("unindexed_foreign_keys", "INFO", "t"), None)

    def test_skipping_the_fk_rule_does_not_silence_real_findings(self):
        """Sizes missing must not become a way for a WARN to slip through."""
        assert advisors.should_report(finding("some_new_lint", "WARN"), None)
        assert advisors.should_report(finding("rls_disabled_in_public", "ERROR", "profiles"), None)

    def test_threshold_is_overridable_for_a_deliberate_sweep(self):
        f = finding("unindexed_foreign_keys", "INFO", "t")
        assert advisors.should_report(f, {"t": 10}, threshold=5)


class TestAcceptedFindings:
    def test_deny_all_rls_is_not_reported(self):
        assert not advisors.should_report(finding("rls_enabled_no_policy", "INFO"), {})

    def test_security_definer_helpers_are_not_reported(self):
        """Revoking EXECUTE would break the public catalogue, not close a hole."""
        assert not advisors.should_report(finding("anon_security_definer_function_executable", "WARN"), {})
        assert not advisors.should_report(finding("authenticated_security_definer_function_executable", "WARN"), {})

    def test_long_otp_expiry_is_a_decision_not_a_defect(self):
        assert not advisors.should_report(finding("auth_otp_long_expiry", "WARN"), {})

    def test_every_accepted_entry_carries_its_reason(self):
        """An allowlist without reasons becomes a place to hide findings."""
        for name, reason in advisors.ACCEPTED.items():
            assert len(reason) > 40, f"{name} is accepted without a real explanation"


class TestUnknownFindings:
    def test_a_new_warning_fails_the_run(self):
        assert advisors.should_report(finding("some_new_lint", "WARN"), {})

    def test_an_error_fails_the_run(self):
        assert advisors.should_report(finding("policy_exists_rls_disabled", "ERROR"), {})

    def test_a_new_info_finding_stays_quiet(self):
        """INFO is a catalogue, not a task list — except for the FK rule above."""
        assert not advisors.should_report(finding("some_new_lint", "INFO"), {})

    def test_rls_disabled_would_be_reported(self):
        """The finding that was real in August must not be swallowed."""
        assert advisors.should_report(finding("rls_disabled_in_public", "ERROR", "profiles"), {})


class TestRowCountParsing:
    def test_reads_the_query_shape_the_workflow_sends(self):
        rows = [{"line": "content_versions=28926"}, {"line": "grade_sheets=0"}]
        assert advisors.parse_row_counts(rows) == {"content_versions": 28926, "grade_sheets": 0}

    def test_survives_junk_without_crashing_the_run(self):
        rows = [{"line": "broken"}, {"line": "t=notanumber"}, {}, {"line": "ok=5"}]
        assert advisors.parse_row_counts(rows) == {"ok": 5}


class TestRowCountsFromApi:
    """Sizes come from the Management API now — the CLI needed a password CI has not."""

    def test_reads_the_management_api_shape(self, monkeypatch):
        monkeypatch.setattr(
            advisors,
            "post",
            lambda *a, **k: [
                {"relname": "content_versions", "n_live_tup": 28926},
                {"relname": "grade_sheets", "n_live_tup": 0},
            ],
        )
        assert advisors.fetch_row_counts("ref", "token") == {
            "content_versions": 28926,
            "grade_sheets": 0,
        }

    def test_unwraps_a_result_envelope(self, monkeypatch):
        monkeypatch.setattr(advisors, "post", lambda *a, **k: {"result": [{"relname": "t", "n_live_tup": 5}]})
        assert advisors.fetch_row_counts("ref", "token") == {"t": 5}

    def test_returns_none_when_the_call_fails(self, monkeypatch):
        def boom(*a, **k):
            raise TimeoutError

        monkeypatch.setattr(advisors, "post", boom)
        assert advisors.fetch_row_counts("ref", "token") is None

    def test_returns_none_rather_than_an_empty_set(self, monkeypatch):
        """Empty and unknown must not be confused: empty would skip every table."""
        monkeypatch.setattr(advisors, "post", lambda *a, **k: [])
        assert advisors.fetch_row_counts("ref", "token") is None


class TestAuthConfigFile:
    """The file is the point: these settings were invisible before it."""

    raw = json.loads((ROOT / "supabase" / "config" / "auth.production.json").read_text())

    def test_prose_keys_are_not_sent_to_the_api(self):
        desired = auth_config.desired_settings(self.raw)
        assert not any(k.startswith("$") for k in desired)
        assert "mailer_otp_exp" in desired

    def test_the_email_rate_limit_is_the_repaired_value(self):
        """2/hour was the real cause of 'missing' recovery mail."""
        assert auth_config.desired_settings(self.raw)["rate_limit_email_sent"] == 30

    def test_settings_that_protect_accounts_are_pinned(self):
        desired = auth_config.desired_settings(self.raw)
        assert desired["password_min_length"] >= 12
        assert desired["password_hibp_enabled"] is True
        assert desired["mailer_autoconfirm"] is False
        assert desired["refresh_token_rotation_enabled"] is True

    def test_every_setting_carries_its_own_reason(self):
        """A value with no written reason is one nobody later dares to change."""
        for key in auth_config.desired_settings(self.raw):
            reason = self.raw.get(f"${key}")
            assert isinstance(reason, str) and len(reason) > 40, (
                f"{key} has no ${key} line explaining why it holds that value"
            )

    def test_no_orphan_explanations(self):
        """A $line whose setting was removed is documentation that lies."""
        settings = set(auth_config.desired_settings(self.raw))
        for key in self.raw:
            if key.startswith("$") and key != "$comment":
                assert key[1:] in settings, f"{key} explains a setting that is no longer here"


class TestAuthConfigDiff:
    def test_no_diff_when_production_matches(self):
        assert auth_config.diff({"a": 1}, {"a": 1, "unrelated": 9}) == {}

    def test_reports_what_we_want_and_what_is_there(self):
        assert auth_config.diff({"rate_limit_email_sent": 30}, {"rate_limit_email_sent": 2}) == {
            "rate_limit_email_sent": (30, 2)
        }

    def test_absent_key_counts_as_drift(self):
        assert auth_config.diff({"a": 1}, {}) == {"a": (1, "<absent>")}

    def test_ignores_every_field_we_do_not_claim(self):
        """The file owns its keys and nothing else — Supabase keeps adding fields."""
        assert auth_config.diff({"a": 1}, {"a": 1, "b": 2, "c": 3}) == {}

    def test_false_is_a_value_not_a_missing_one(self):
        assert auth_config.diff({"mailer_autoconfirm": False}, {"mailer_autoconfirm": False}) == {}
        assert auth_config.diff({"mailer_autoconfirm": False}, {"mailer_autoconfirm": True}) == {
            "mailer_autoconfirm": (False, True)
        }

    @pytest.mark.parametrize("live", [{"n": "30"}, {"n": 30.0}])
    def test_type_changes_are_drift_not_equality(self, live):
        """A string '30' from the API is not the integer we asked for."""
        result = auth_config.diff({"n": 30}, live)
        assert ("n" in result) == (live["n"] != 30)
