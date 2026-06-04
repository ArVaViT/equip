"""Sentinel: every ``equip.*`` metric emitted from ``app/`` must be
mentioned in ``docs/datadog/README.md``.

Without this gate, future PRs ship metric emitters but forget the
README update — and the dashboard reader has no way to discover the
metric exists. We learned this the hard way on 2026-06-02 when the
Course Engagement dashboard JSON referenced metrics that didn't
exist (``equip.enrollments.active_7d``,
``equip.engagement.dropoff_count``, ``equip.reviews.rating_avg``).
Symmetric problem: the README listed metrics that nobody emitted any
longer. This test catches both directions.

Scope: only ``equip.*`` namespaces emitted via the ``app.core.metrics``
helpers (``emit`` / ``increment`` / ``gauge`` / ``timing``). The test
walks every Python file under ``app/`` and extracts the metric name
strings; each must appear verbatim somewhere in the README.

Allow-list: an emitted name can be intentionally absent from the
README if the README explicitly mentions it as a *family prefix*
(e.g. README says ``equip.grading.*`` covers both ``graded_total``
and ``time_to_grade.p50``). We honour ``equip.<segment>.*`` wildcards
literally.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_DIR = REPO_ROOT / "backend" / "app"
README = REPO_ROOT / "docs" / "datadog" / "README.md"

# Captures the first argument to metrics helpers (``emit("equip.X")``
# / ``increment("equip.X")`` / ``gauge("equip.X")`` / ``timing("equip.X")``).
# The two-line form (helper name on one line, string literal on the
# next) is intentional — black + ruff format wraps long calls and we
# need to catch both shapes.
_METRIC_CALL_RE = re.compile(
    r"""(?:emit|increment|gauge|timing)\s*\(\s*\n?\s*["']
        (equip\.[a-zA-Z0-9_.]+)
        ["']""",
    re.VERBOSE,
)


def _collect_emitted_metrics() -> set[str]:
    """Walk every .py under app/ and harvest the metric name from
    every helper call site."""
    found: set[str] = set()
    for py in APP_DIR.rglob("*.py"):
        src = py.read_text(encoding="utf-8")
        for match in _METRIC_CALL_RE.finditer(src):
            name = match.group(1)
            found.add(name)
    return found


def _readme_text() -> str:
    return README.read_text(encoding="utf-8")


def _readme_mentions(metric: str, doc: str) -> bool:
    """A metric is "documented" when:

    1. Its exact name appears in the README, OR
    2. A prefix of the form ``equip.<group>.*`` is in the README and
       the metric belongs to that group.
    """
    if metric in doc:
        return True
    # Reduce ``equip.grading.graded_total`` to ``equip.grading.*``
    # and check that prefix.
    segments = metric.split(".")
    if len(segments) >= 3:
        wildcard = ".".join(segments[:2]) + ".*"
        if wildcard in doc:
            return True
    return False


def test_every_emitted_metric_is_documented_in_readme() -> None:
    emitted = _collect_emitted_metrics()
    # ``equip.metric`` is the LOGGER name, not a metric. The helpers
    # never emit a metric with that exact 2-segment name; filter
    # defensively in case a future test or helper does.
    emitted.discard("equip.metric")
    assert emitted, "expected to find at least one emit() call site"

    doc = _readme_text()
    undocumented = sorted(m for m in emitted if not _readme_mentions(m, doc))
    assert not undocumented, (
        "These metrics are emitted from app/ but NOT documented in "
        "docs/datadog/README.md. Add a stanza for each (or a "
        "``equip.<group>.*`` wildcard that covers them):\n  - " + "\n  - ".join(undocumented)
    )


def test_collect_emitted_metrics_finds_known_emitters() -> None:
    """Smoke check the harvester itself — if our regex stops matching
    new helper shapes, the sentinel above silently passes by finding
    nothing. Lock that this test would fail if the harvester returned
    an empty set."""
    emitted = _collect_emitted_metrics()
    # These are known to ship today (post-#701 / #702 / #707).
    assert "equip.activity.requests_total" in emitted
    assert "equip.errors.unhandled_total" in emitted
