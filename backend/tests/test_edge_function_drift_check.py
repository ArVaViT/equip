"""The drift check that guards the edge function's deploy.

The check itself lives in `.github/scripts/edge_function_drift.py` because
it runs in CI, not in the app — but its logic decides whether anybody is
told that production is sending email from code older than main, so it is
tested here with the rest of the suite rather than trusted.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import os
import subprocess
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


def _git(cwd: Path, *args: str, when: dt.datetime | None = None) -> str:
    env = None
    if when is not None:
        stamp = when.isoformat()
        env = {**os.environ, "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout.strip()


def _commit(repo: Path, path: str, content: str, when: dt.datetime | None = None) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"touch {path}", when=when)
    return _git(repo, "rev-parse", "HEAD")


def _ago(**delta: float) -> dt.datetime:
    return (dt.datetime.now(tz=dt.UTC) - dt.timedelta(**delta)).replace(microsecond=0)


FUNCTION = "supabase/functions/send-email"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A repository whose last commit touched only a workflow file.

    That is the shape of the three 2026-09-15 pushes that failed the deploy:
    the function last changed (and was deployed) a day earlier, then actions
    bumps edited .github/workflows/edge-functions-deploy.yml.
    """
    root = tmp_path / "origin"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    function_commit = _commit(root, f"{FUNCTION}/index.ts", "v1", when=_ago(days=1))
    workflow_commit = _commit(root, ".github/workflows/edge-functions-deploy.yml", "bump")
    monkeypatch.chdir(root)
    return {"root": root, "function_commit": function_commit, "workflow_commit": workflow_commit}


class TestSourceChangedSince:
    def test_a_push_that_did_not_touch_the_function_needs_no_fresh_deploy(self, repo):
        """The CLI answers "No change found" and the deploy time rightly stays put."""
        assert not drift.source_changed_since(repo["function_commit"], [FUNCTION])

    def test_a_push_that_touched_the_function_needs_a_fresh_deploy(self, repo):
        _commit(repo["root"], f"{FUNCTION}/index.ts", "v2")
        assert drift.source_changed_since(repo["workflow_commit"], [FUNCTION])

    @pytest.mark.parametrize("base", [None, "", "0" * 40])
    def test_no_base_counts_as_changed(self, repo, base):
        """A manual run or a newly created ref: cannot tell, so stay strict."""
        assert drift.source_changed_since(base, [FUNCTION])

    def test_a_base_this_clone_does_not_have_counts_as_changed(self, repo):
        """After a force-push the old SHA is gone; that is not "unchanged"."""
        assert drift.source_changed_since("1" * 40, [FUNCTION])


class TestShallowClone:
    def test_full_history_reports_the_commit_that_touched_the_function(self, repo):
        assert not drift.is_shallow_clone()
        touched = drift.last_source_change([FUNCTION])
        assert touched == dt.datetime.fromisoformat(
            _git(repo["root"], "log", "-1", "--format=%cI", repo["function_commit"])
        ).astimezone(dt.UTC)

    def test_a_shallow_clone_is_detected(self, repo, tmp_path, monkeypatch):
        """What actions/checkout gives by default, and what broke the deploy.

        With only HEAD available, git attributes every path to HEAD — so the
        workflow-only commit looks like a change to the function. The script
        must refuse this clone rather than answer from it.
        """
        shallow = tmp_path / "shallow"
        _git(tmp_path, "clone", "-q", "--depth", "1", f"file://{repo['root']}", str(shallow))
        monkeypatch.chdir(shallow)
        assert drift.is_shallow_clone()
        head = _git(shallow, "rev-parse", "HEAD")
        assert head == repo["workflow_commit"]
        assert _git(shallow, "log", "-1", "--format=%H", "--", FUNCTION) == head


class TestMain:
    """The whole check, with Supabase's answer stubbed and git real."""

    def _run(self, monkeypatch, *argv: str, deployed_at: dt.datetime) -> int:
        monkeypatch.setenv("SUPABASE_ACCESS_TOKEN", "test-token")
        monkeypatch.setattr(
            drift,
            "fetch_function",
            lambda ref, slug, token: {"updated_at": int(deployed_at.timestamp() * 1000), "version": 17},
        )
        monkeypatch.setattr("sys.argv", ["edge_function_drift.py", *argv])
        return drift.main()

    def _commit_time(self, repo, sha: str) -> dt.datetime:
        return dt.datetime.fromisoformat(_git(repo["root"], "log", "-1", "--format=%cI", sha)).astimezone(dt.UTC)

    def test_the_2026_09_15_push_passes(self, repo, monkeypatch):
        """Deployed a day ago, right after the last function change; this push bumped a workflow.

        Production is current, and the CLI answered "No change found", so the
        deploy time is a day old. The run must pass.
        """
        deployed = self._commit_time(repo, repo["function_commit"]) + dt.timedelta(seconds=20)
        base = repo["function_commit"]
        assert self._run(monkeypatch, "--require-fresh-if-changed-since", base, deployed_at=deployed) == 0

    def test_the_same_state_fails_when_the_push_cannot_be_told_apart(self, repo, monkeypatch):
        """Guards the test above: with no base, freshness is demanded and a day-old deploy fails."""
        deployed = self._commit_time(repo, repo["function_commit"]) + dt.timedelta(seconds=20)
        assert self._run(monkeypatch, "--require-fresh-if-changed-since", "", deployed_at=deployed) == 1

    def test_a_function_change_that_did_not_deploy_still_fails(self, repo, monkeypatch):
        """A no-op deploy of a real change fails even when timestamps alone look fine.

        The change's commit date is two hours old (a merge keeps the branch
        commit's date) and something deployed an hour ago, so the drift
        comparison passes. Only freshness catches that this push's deploy did
        nothing.
        """
        before = repo["workflow_commit"]
        _commit(repo["root"], f"{FUNCTION}/index.ts", "v2", when=_ago(hours=2))
        assert self._run(monkeypatch, "--require-fresh-if-changed-since", before, deployed_at=_ago(hours=1)) == 1

    def test_a_function_change_that_deployed_passes(self, repo, monkeypatch):
        before = repo["workflow_commit"]
        _commit(repo["root"], f"{FUNCTION}/index.ts", "v2")
        deployed = dt.datetime.now(tz=dt.UTC) + dt.timedelta(seconds=1)
        assert self._run(monkeypatch, "--require-fresh-if-changed-since", before, deployed_at=deployed) == 0

    def test_a_shallow_clone_fails_before_asking_supabase(self, repo, tmp_path, monkeypatch):
        shallow = tmp_path / "shallow"
        _git(tmp_path, "clone", "-q", "--depth", "1", f"file://{repo['root']}", str(shallow))
        monkeypatch.chdir(shallow)

        def unreachable(*_args):
            raise AssertionError("must not reach Supabase from a shallow clone")

        monkeypatch.setattr(drift, "fetch_function", unreachable)
        monkeypatch.setattr("sys.argv", ["edge_function_drift.py"])
        assert drift.main() == 1


class TestFreshnessWindow:
    def test_window_is_generous_enough_for_a_slow_runner(self):
        """A CI deploy takes minutes; the window must not fail an honest one."""
        assert drift.FRESH_DEPLOY_MAX_AGE_SECONDS >= 5 * 60

    def test_window_is_tight_enough_to_catch_a_no_op_deploy(self):
        """Yesterday's deploy must not read as 'fresh' after today's run."""
        assert drift.FRESH_DEPLOY_MAX_AGE_SECONDS < 24 * 60 * 60
