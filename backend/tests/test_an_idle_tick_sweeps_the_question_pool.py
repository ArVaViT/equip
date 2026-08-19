"""An idle minute is the cheapest minute there is.

The translation worker runs every minute. The Daily Challenge pool's own
sweep rides along with the nightly generator, two questions a night —
right for catching a question written before a language existed, and
hopeless for anything larger. Raising ``TRANSLATOR_VERSION`` left three
thousand pool rows behind it: at two questions a night, four months.

So a tick with an empty queue and no course behind sweeps the pool
instead of returning idle. It costs nothing — the invocation is paid for
either way — and it leaves the nightly Gemini budget alone. A time
budget keeps it inside the one invocation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from app.api.v1.internal_translation_worker import _run_one_tick
from app.services.daily_challenge.translate import SweepReport
from app.services.translation.orchestrator import OrchestratorReport
from app.services.translation.reconciler import SweepReport as CourseSweepReport
from app.services.translation.service import reset_translation_provider_cache

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


@pytest.fixture
def quiet_queue():
    """No job to claim and no course behind — the idle path."""
    with (
        patch("app.api.v1.internal_translation_worker.claim_next_job", return_value=None),
        patch(
            "app.api.v1.internal_translation_worker.sweep_courses",
            return_value=CourseSweepReport(examined=3, queued=0, complete=3),
        ),
    ):
        yield


class TestAnIdleTickLooksAtThePool:
    def test_it_sweeps_when_there_is_nothing_else_to_do(self, db: Session, quiet_queue) -> None:
        with patch(
            "app.api.v1.internal_translation_worker.translate_pending_questions",
            return_value=SweepReport(questions=3, rows=OrchestratorReport(translated=36)),
        ) as sweep:
            response = _run_one_tick(db)
        sweep.assert_called_once()
        assert response.status == "swept"
        assert response.translated == 36

    def test_a_quiet_pool_still_reports_idle(self, db: Session, quiet_queue) -> None:
        with patch(
            "app.api.v1.internal_translation_worker.translate_pending_questions",
            return_value=SweepReport(questions=0, rows=OrchestratorReport()),
        ):
            assert _run_one_tick(db).status == "idle"

    def test_a_course_behind_still_comes_first(self, db: Session) -> None:
        # The pool is the fallback, not a competitor: a course with a
        # real gap is what a reader is waiting on.
        with (
            patch("app.api.v1.internal_translation_worker.claim_next_job", return_value=None),
            patch(
                "app.api.v1.internal_translation_worker.sweep_courses",
                return_value=CourseSweepReport(examined=1, queued=1),
            ),
            patch("app.api.v1.internal_translation_worker.translate_pending_questions") as pool,
        ):
            assert _run_one_tick(db).status == "swept"
        pool.assert_not_called()

    def test_a_failing_pool_sweep_does_not_fail_the_tick(self, db: Session, quiet_queue) -> None:
        # An extra done with spare time must never take the worker down.
        with patch(
            "app.api.v1.internal_translation_worker.translate_pending_questions",
            side_effect=RuntimeError("provider exploded"),
        ):
            assert _run_one_tick(db).status == "idle"
