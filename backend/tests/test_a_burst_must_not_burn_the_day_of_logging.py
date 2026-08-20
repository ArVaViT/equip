"""What a hundred identical warnings a minute did to observability.

On 2026-08-20 the translation provider began refusing every call. The
worker logged one warning per row — the same sentence with a different
id in it — at roughly a hundred a minute, for hours. Datadog stopped
indexing logs that morning and had not resumed eleven hours later: the
intake still answered 202, and nothing submitted since was searchable.

The outage itself had to be diagnosed out of the database, because the
place you would normally look was empty. And the error-spike monitor
reported *recovered* seven minutes in — not because the errors had
stopped but because the logs had, which reads identically to a monitor
with nothing to say.

These tests hold the collapsing that stops a burst costing a day of
indexing, and — just as important — hold the parts that must NOT
collapse, because a log that hides a second, different problem during
an incident is worse than a log that costs money.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from app.core.logging import DatadogHTTPHandler


@pytest.fixture
def handler(monkeypatch: pytest.MonkeyPatch) -> tuple[DatadogHTTPHandler, list[dict[str, Any]]]:
    """A handler whose POSTs land in a list instead of on the network."""
    shipped: list[dict[str, Any]] = []
    h = DatadogHTTPHandler(
        api_key="test-key",
        site="datadoghq.com",
        service="equip-backend",
        env="production",
        version="abc1234",
        vercel_region="iad1",
    )
    h.setFormatter(logging.Formatter("%(message)s"))

    import json as json_module
    import urllib.request as urllib_request

    def fake_urlopen(req: Any, timeout: float | None = None) -> Any:
        shipped.append(json_module.loads(req.data.decode()))

        class _Resp:
            def __enter__(self) -> _Resp:
                return self

            def __exit__(self, *exc: object) -> None:
                return None

        return _Resp()

    monkeypatch.setattr(urllib_request, "urlopen", fake_urlopen)
    return h, shipped


def _record(template: str, *args: object, name: str = "app.worker", level: int = logging.WARNING) -> logging.LogRecord:
    return logging.LogRecord(
        name=name, level=level, pathname=__file__, lineno=1, msg=template, args=args, exc_info=None
    )


class TestABurstOfOneKindCostsThreeLinesNotThreeHundred:
    def test_a_hundred_of_the_same_warning_ship_once(
        self, handler: tuple[DatadogHTTPHandler, list[dict[str, Any]]]
    ) -> None:
        """The production shape exactly: one template, a different entity
        id each time, a hundred of them inside a minute."""
        h, shipped = handler
        for i in range(100):
            h.emit(_record("Translation failed entity=%s field=%s locale=%s", f"quiz_option:{i}", "option_text", "de"))

        assert len(shipped) == 1, "the first says everything the next ninety-nine would have"

    def test_the_ones_that_were_folded_are_counted_not_lost(
        self, handler: tuple[DatadogHTTPHandler, list[dict[str, Any]]]
    ) -> None:
        """Folding that loses the count would turn a hundred failures
        into one, which is a different lie from the one being fixed."""
        h, shipped = handler
        for i in range(100):
            h.emit(_record("Translation failed entity=%s", f"quiz_option:{i}"))
        h.REPEAT_WINDOW_SECONDS = 0.0  # the window closes
        h.emit(_record("Translation failed entity=%s", "quiz_option:100"))

        assert len(shipped) == 2
        assert shipped[1]["dd.suppressed_repeats"] == 99
        assert "+99 more like this" in shipped[1]["message"], "and a human reading the stream can see it"


class TestWhatMustNeverBeFolded:
    def test_a_different_kind_of_warning_is_never_held_behind_a_burst(
        self, handler: tuple[DatadogHTTPHandler, list[dict[str, Any]]]
    ) -> None:
        """The failure mode that would make this change worse than the
        problem: a second, unrelated fault arriving during an incident
        and being swallowed by the noise of the first."""
        h, shipped = handler
        for i in range(50):
            h.emit(_record("Translation failed entity=%s", f"quiz_option:{i}"))
        h.emit(_record("Database connection lost: %s", "read-only transaction"))

        messages = [s["message"] for s in shipped]
        assert any("Database connection lost" in m for m in messages), "a new kind of trouble always gets through"

    def test_the_same_sentence_from_a_different_logger_is_a_different_kind(
        self, handler: tuple[DatadogHTTPHandler, list[dict[str, Any]]]
    ) -> None:
        """Two subsystems failing the same way is two facts, not one."""
        h, shipped = handler
        h.emit(_record("Timed out after %ss", 30, name="app.services.translation"))
        h.emit(_record("Timed out after %ss", 30, name="app.services.email"))

        assert len(shipped) == 2

    def test_an_error_is_not_folded_into_a_warning(
        self, handler: tuple[DatadogHTTPHandler, list[dict[str, Any]]]
    ) -> None:
        """Severity is part of what the record says."""
        h, shipped = handler
        h.emit(_record("Provider unreachable: %s", "429", level=logging.WARNING))
        h.emit(_record("Provider unreachable: %s", "429", level=logging.ERROR))

        assert len(shipped) == 2

    def test_a_flood_of_distinct_templates_still_gets_through(
        self, handler: tuple[DatadogHTTPHandler, list[dict[str, Any]]]
    ) -> None:
        """The bookkeeping dict is bounded, and the bound must spend
        itself on holding fewer records rather than on dropping unseen
        ones. Past the cap, a template nobody has seen still ships."""
        h, shipped = handler
        for i in range(h.MAX_TRACKED_TEMPLATES + 40):
            h.emit(_record(f"A warning of kind {i}: %s", "detail"))

        assert len(shipped) == h.MAX_TRACKED_TEMPLATES + 40


class TestTheWindowReopens:
    def test_a_problem_that_lasts_is_still_reported_while_it_lasts(
        self, handler: tuple[DatadogHTTPHandler, list[dict[str, Any]]]
    ) -> None:
        """Collapsing must not become silence. An outage that runs for an
        hour has to keep saying so — otherwise the log looks like a burst
        that ended, which is the exact misreading that made the monitor
        report recovery yesterday."""
        h, shipped = handler
        h.emit(_record("Translation failed entity=%s", "a"))
        assert len(shipped) == 1

        h.REPEAT_WINDOW_SECONDS = 0.0
        h.emit(_record("Translation failed entity=%s", "b"))
        h.emit(_record("Translation failed entity=%s", "c"))

        assert len(shipped) == 3, "still happening, still being said"
