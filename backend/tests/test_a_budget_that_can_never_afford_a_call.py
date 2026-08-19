"""A worker that reports "paused" forever and never makes a call.

``worker_budget`` keeps back the worst case for one provider call —
``GEMINI_TIMEOUT_SECONDS`` on each of three attempts, plus three seconds
of backoff, plus two for the commit and the promotion check. When that
reserve reaches ``TRANSLATION_WORKER_BUDGET_SECONDS``,
``can_afford_one_call()`` is already False at t=0. ``execute_plan`` sets
``incomplete`` before the first call, ``made_progress`` is False, and
``mark_job_paused`` never consults ``TRANSLATION_JOB_MAX_ATTEMPTS`` — so
the job returns to ``queued`` and is re-claimed every minute for as long
as the deployment stands, while the worker answers "paused", which reads
as healthy.

At the 180 s default the two settings are one raise apart: the
breakpoint is 58.33 s, and ``GEMINI_TIMEOUT_SECONDS`` has already been
raised once in ``core/config.py`` (15 → 30, for a 5 KB Russian block).
The next such raise crosses it. Nothing validated the pair, so the only
symptom would have been silence.

Refusing at boot is deliberate: an operator changing a timeout sees the
arithmetic and both setting names, instead of a queue that drains at
zero rows a minute.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings, call_reserve_seconds
from app.services.translation.budget import worker_budget


class TestTheArithmetic:
    def test_the_reserve_is_three_timeouts_plus_backoff_plus_the_tail(self) -> None:
        assert call_reserve_seconds(30.0) == 30.0 * 3 + 3.0 + 2.0

    def test_just_under_the_line_can_still_start_a_call(self) -> None:
        budget = worker_budget(seconds=180.0, gemini_timeout_seconds=58.0)
        assert budget.can_afford_one_call()

    def test_just_over_it_cannot_start_one_at_all(self) -> None:
        # Not "runs out of time mid-course" — never begins. This is the
        # state the validator below exists to keep out of production.
        budget = worker_budget(seconds=180.0, gemini_timeout_seconds=60.0)
        assert not budget.can_afford_one_call()


class TestTheDeploymentIsRefused:
    def test_a_timeout_past_the_breakpoint_does_not_boot(self) -> None:
        with pytest.raises(ValidationError) as caught:
            Settings(GEMINI_TIMEOUT_SECONDS=60.0, TRANSLATION_WORKER_BUDGET_SECONDS=180.0)

        message = str(caught.value)
        assert "GEMINI_TIMEOUT_SECONDS" in message
        assert "TRANSLATION_WORKER_BUDGET_SECONDS" in message
        # The operator has to be able to act on it without reading the
        # source, so the reserve that broke the pair is in the message.
        assert "185.0" in message

    def test_an_equal_reserve_is_refused_too(self) -> None:
        # The check is ``>=``: a reserve exactly equal to the budget
        # leaves ``remaining > reserve_seconds`` false at t=0.
        with pytest.raises(ValidationError):
            Settings(GEMINI_TIMEOUT_SECONDS=30.0, TRANSLATION_WORKER_BUDGET_SECONDS=95.0)

    def test_the_shipped_defaults_boot(self) -> None:
        settings = Settings()
        assert call_reserve_seconds(settings.GEMINI_TIMEOUT_SECONDS) < settings.TRANSLATION_WORKER_BUDGET_SECONDS

    def test_a_bigger_budget_is_the_other_way_out(self) -> None:
        # Two knobs, and the error message names both. Raising the
        # budget is legitimate as long as it stays under the function's
        # maxDuration.
        settings = Settings(GEMINI_TIMEOUT_SECONDS=60.0, TRANSLATION_WORKER_BUDGET_SECONDS=240.0)
        assert worker_budget(
            seconds=settings.TRANSLATION_WORKER_BUDGET_SECONDS,
            gemini_timeout_seconds=settings.GEMINI_TIMEOUT_SECONDS,
        ).can_afford_one_call()
