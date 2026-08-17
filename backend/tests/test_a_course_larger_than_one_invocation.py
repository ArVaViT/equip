"""A course too big for one worker tick must still finish.

In August 2026 one course sat in the queue for two days across 161
attempts. Nothing was wrong with the course. The worker translated it
inside a single serverless invocation, the invocation was killed at its
``maxDuration``, and a killed process records nothing — so the row
stayed ``processing``, the stale sweep re-claimed it a quarter of an
hour later, and the same walk died at the same place. The attempt
counter climbed on every claim until the job was declared permanently
failed.

The behaviour these tests pin down is the one that was missing: a pass
knows its deadline, stops before it, says so, and is resumed. The
distinction that makes it safe is ``made_progress`` — a long course and
a broken course both come back unfinished, and only the one with
nothing to show for itself spends an attempt.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from app.models.course import Course
from app.models.translation_job import (
    TRANSLATION_JOB_MAX_ATTEMPTS,
    TranslationJobStatus,
)
from app.models.user import User
from app.services.content_versions.write import record_human_version
from app.services.translation.budget import NoBudget, TranslationBudget, worker_budget
from app.services.translation.course_pipeline import translate_course_content
from app.services.translation.orchestrator import (
    OrchestratorReport,
    TranslationFieldSpec,
    translate_entity_fields,
)
from app.services.translation.protocol import TranslationRequest, TranslationResult
from app.services.translation.queue import enqueue_course_translation
from app.services.translation.service import reset_translation_provider_cache
from tests._fake_translation import fake_translate
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

_WORKER_PATH = "/api/v1/internal/translation-worker"
_GOOD_SECRET = "test-worker-secret-do-not-use-in-prod"


class _SpentBudget(TranslationBudget):
    """A budget with nothing left — the state a long walk arrives at.

    Used instead of sleeping: the tests are about what the code does
    when the clock has run out, not about the clock.
    """

    def __init__(self) -> None:
        super().__init__(seconds=0.0)

    @property
    def remaining(self) -> float:
        return -1.0


class _BudgetAfterNCalls(TranslationBudget):
    """Affords exactly ``n`` provider calls, then nothing.

    Models the real shape of a tick: some work gets done, the clock runs
    out mid-course, the rest waits for the next one.
    """

    def __init__(self, n: int) -> None:
        super().__init__(seconds=0.0)
        self._left = n

    def expired(self) -> bool:
        return self._left <= 0

    def can_afford_one_call(self) -> bool:
        if self._left <= 0:
            return False
        self._left -= 1
        return True


class _CountingProvider:
    name = "counting"

    def __init__(self) -> None:
        self.calls: list[TranslationRequest] = []

    def translate(self, request: TranslationRequest) -> TranslationResult:
        self.calls.append(request)
        return TranslationResult(
            text=fake_translate(request.text, target_locale=request.target_locale),
            model="test",
        )


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


@pytest.fixture
def configured_worker(monkeypatch):
    monkeypatch.setattr(
        "app.core.config.settings.TRANSLATION_WORKER_SECRET",
        SecretStr(_GOOD_SECRET),
        raising=False,
    )


def _ensure_teacher(db: Session) -> None:
    if db.get(User, TEACHER_ID) is not None:
        return
    db.add(User(id=TEACHER_ID, email="teacher@example.com", full_name="T", role="teacher"))
    db.commit()


def _make_course(db: Session, **overrides: Any) -> Course:
    _ensure_teacher(db)
    defaults: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "status": "published",
        "source_locale": "ru",
        "created_by": TEACHER_ID,
    }
    defaults.update(overrides)
    course = Course(**defaults)
    db.add(course)
    db.commit()
    db.refresh(course)
    record_human_version(
        db,
        entity_type="course",
        entity_id=str(course.id),
        field="title",
        locale="ru",
        text=str(overrides.get("title_text", "Деяния апостолов")),
    )
    record_human_version(
        db,
        entity_type="course",
        entity_id=str(course.id),
        field="description",
        locale="ru",
        text="Обзор ранней Церкви и её свидетельства.",
    )
    db.commit()
    return course


# ---------------------------------------------------------------------------
# The budget itself
# ---------------------------------------------------------------------------


def test_a_call_is_only_started_if_its_worst_case_fits():
    """The check is not "is there time left" but "is there time for the
    whole of what I am about to start". A 30-second call with two
    retries must not begin with 10 seconds on the clock."""
    budget = worker_budget(seconds=180.0, gemini_timeout_seconds=30.0, gemini_max_retries=2)
    # 30 * 3 attempts + (1 + 2) backoff + 2 slack.
    assert budget.reserve_seconds == pytest.approx(95.0)
    assert budget.can_afford_one_call() is True

    nearly_spent = worker_budget(seconds=10.0, gemini_timeout_seconds=30.0, gemini_max_retries=2)
    assert nearly_spent.can_afford_one_call() is False
    # ...and it is not "expired": there is time on the clock, just not
    # enough to safely spend on a call. Conflating the two is how a tick
    # gets killed with a request in flight.
    assert nearly_spent.expired() is False


def test_no_budget_never_says_no():
    """Synchronous callers — a teacher saving one block, an admin retry
    — have no deadline, and must not inherit one by accident."""
    unlimited = NoBudget()
    assert unlimited.expired() is False
    assert unlimited.can_afford_one_call() is True
    assert unlimited.remaining == float("inf")


# ---------------------------------------------------------------------------
# The orchestrator honours it
# ---------------------------------------------------------------------------


def test_a_spent_budget_buys_nothing_and_writes_nothing(db: Session):
    """Out of time means the provider is not called at all — not called
    and discarded. The row is left exactly as it was so the next tick
    finds the work still waiting."""
    course = _make_course(db)
    provider = _CountingProvider()

    report = translate_entity_fields(
        db,
        entity_type="course",
        entity_id=str(course.id),
        source_locale="ru",
        fields=[TranslationFieldSpec(field="title", text="Деяния апостолов", content_kind="title")],
        provider=provider,
        budget=_SpentBudget(),
    )

    assert provider.calls == []
    assert report.incomplete is True
    assert report.translated == 0
    # Nothing moved, so this pass has no claim on another free tick.
    assert report.made_progress is False


def test_the_walk_stops_mid_course_and_says_so(db: Session):
    """Two fields, one call's worth of budget: the first is translated,
    the second is left for the next tick, and the report is honest
    about it."""
    course = _make_course(db)
    provider = _CountingProvider()

    report = translate_course_content(
        db,
        course,
        provider=provider,
        budget=_BudgetAfterNCalls(1),
    )

    assert len(provider.calls) == 1
    assert report.incomplete is True
    assert report.translated == 1
    # Something moved — this earns another tick without spending an
    # attempt, which is the whole distinction the incident lacked.
    assert report.made_progress is True


def test_an_unbudgeted_pass_still_runs_to_completion(db: Session):
    """Every existing caller passes no budget and must keep the
    run-to-completion behaviour it was written against."""
    course = _make_course(db)
    provider = _CountingProvider()

    report = translate_course_content(db, course, provider=provider)

    assert report.incomplete is False
    assert provider.calls  # it actually did the work


# ---------------------------------------------------------------------------
# The worker resumes rather than fails
# ---------------------------------------------------------------------------


def test_an_unfinished_tick_requeues_the_job_instead_of_failing_it(
    client: TestClient, db: Session, teacher, configured_worker
):
    """The tick ran out of clock with work left. That is not a failure:
    the job goes back to ``queued`` so the next cron minute continues
    it, and it carries no error."""
    course = _make_course(db, created_by=teacher.id)
    job = enqueue_course_translation(db, course.id)

    with patch(
        "app.api.v1.internal_translation_worker.translate_course_content",
        return_value=OrchestratorReport(translated=12, incomplete=True),
    ):
        resp = client.post(_WORKER_PATH, headers={"X-Worker-Secret": _GOOD_SECRET})

    assert resp.status_code == 200
    assert resp.json()["status"] == "paused"

    db.refresh(job)
    assert job.status == TranslationJobStatus.QUEUED
    assert job.last_error is None
    # Cleared so the next tick claims it now, rather than waiting out
    # the stale-processing window.
    assert job.started_at is None


def test_progress_does_not_spend_an_attempt(client: TestClient, db: Session, teacher, configured_worker):
    """The August 2026 regression, stated as a test.

    A course that needs more ticks than the attempt cap allows would be
    declared permanently failed for the crime of being long. As long as
    each tick moves something, the counter goes back to zero and the
    course keeps translating."""
    course = _make_course(db, created_by=teacher.id)
    job = enqueue_course_translation(db, course.id)
    job.attempts = TRANSLATION_JOB_MAX_ATTEMPTS - 1
    db.commit()

    with patch(
        "app.api.v1.internal_translation_worker.translate_course_content",
        return_value=OrchestratorReport(translated=7, incomplete=True),
    ):
        resp = client.post(_WORKER_PATH, headers={"X-Worker-Secret": _GOOD_SECRET})

    assert resp.status_code == 200
    db.refresh(job)
    assert job.status == TranslationJobStatus.QUEUED
    assert job.attempts == 0


def test_a_tick_that_achieves_nothing_still_counts(client: TestClient, db: Session, teacher, configured_worker):
    """The other half of the rule. A job that keeps waking up and
    accomplishing nothing is not merely large, and the attempt cap has
    to keep catching it — otherwise "resume forever" replaces one
    infinite loop with another."""
    course = _make_course(db, created_by=teacher.id)
    job = enqueue_course_translation(db, course.id)
    db.commit()

    with patch(
        "app.api.v1.internal_translation_worker.translate_course_content",
        return_value=OrchestratorReport(skipped=3, incomplete=True),
    ):
        resp = client.post(_WORKER_PATH, headers={"X-Worker-Secret": _GOOD_SECRET})

    assert resp.status_code == 200
    db.refresh(job)
    # The claim's increment stands: no progress, so this was an attempt.
    assert job.attempts == 1


def test_a_long_course_reaches_done_across_several_ticks(client: TestClient, db: Session, teacher, configured_worker):
    """End to end: four unfinished ticks then a finished one. The job
    must survive to be marked ``done`` — under the old code the fourth
    tick was already ``failed_permanent``."""
    course = _make_course(db, created_by=teacher.id)
    job = enqueue_course_translation(db, course.id)

    partial = OrchestratorReport(translated=5, incomplete=True)
    finished = OrchestratorReport(translated=2, incomplete=False)
    outcomes = [partial, partial, partial, partial, finished]

    with patch(
        "app.api.v1.internal_translation_worker.translate_course_content",
        side_effect=outcomes,
    ):
        statuses = [
            client.post(_WORKER_PATH, headers={"X-Worker-Secret": _GOOD_SECRET}).json()["status"] for _ in outcomes
        ]

    assert statuses == ["paused", "paused", "paused", "paused", "done"]
    db.refresh(job)
    assert job.status == TranslationJobStatus.DONE
