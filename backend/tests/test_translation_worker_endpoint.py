"""Tests for the cron-driven translation worker endpoint.

The worker has four behavioural invariants:

1. Without ``TRANSLATION_WORKER_SECRET`` configured, every request
   is 503. This protects dev environments that don't run the queue.
2. With the secret configured but missing / wrong on the request,
   every request is 401 with a generic detail (no secret-vs-no-header
   distinction so a probing attacker learns nothing).
3. With the correct secret and an empty queue, the response is
   ``{"status": "idle"}`` — the cron driver knows there's nothing
   to do this tick.
4. With a job in the queue, ONE tick claims one job, runs the
   orchestrator, marks the job ``done`` (success) or ``failed`` /
   ``failed_permanent`` (failure), and reports the outcome.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from pydantic import SecretStr
from sqlalchemy.exc import SQLAlchemyError

from app.models.course import Course
from app.models.translation_job import (
    TRANSLATION_JOB_MAX_ATTEMPTS,
    TranslationJob,
    TranslationJobStatus,
)
from app.services.translation.queue import enqueue_course_translation

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


_WORKER_PATH = "/api/v1/internal/translation-worker"
_GOOD_SECRET = "test-worker-secret-do-not-use-in-prod"


@pytest.fixture
def configured_worker(monkeypatch):
    """Activate the worker secret for the duration of the test."""
    monkeypatch.setattr(
        "app.core.config.settings.TRANSLATION_WORKER_SECRET",
        SecretStr(_GOOD_SECRET),
        raising=False,
    )


def _make_course(db: Session, teacher_id) -> Course:
    course = Course(
        id=f"worker-{uuid.uuid4().hex[:8]}",
        status="published",
        source_locale="ru",
        created_by=teacher_id,
    )
    db.add(course)
    db.commit()
    return course


def test_accepts_authorization_bearer_header(client: TestClient, configured_worker):
    """Vercel Cron sends ``Authorization: Bearer <secret>`` automatically.
    The worker accepts that shape so the same env var serves both
    direct human access (``X-Worker-Secret``) and the Vercel-managed
    cron auth."""
    resp = client.post(
        _WORKER_PATH,
        headers={"Authorization": f"Bearer {_GOOD_SECRET}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "idle"


def test_get_alias_works_for_vercel_cron(client: TestClient, configured_worker):
    """Vercel Cron sends GET — pin the alias so a refactor that drops
    the GET method breaks CI instead of silently leaving the cron 405."""
    resp = client.get(
        _WORKER_PATH,
        headers={"Authorization": f"Bearer {_GOOD_SECRET}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "idle"


def test_503_when_worker_secret_is_unset(client: TestClient):
    """Default state: TRANSLATION_WORKER_SECRET is unset → endpoint
    refuses every call so a dev env that hasn't configured the queue
    cron doesn't accidentally expose the route."""
    resp = client.post(_WORKER_PATH, headers={"X-Worker-Secret": "anything"})
    assert resp.status_code == 503


def test_401_on_missing_secret_header(client: TestClient, configured_worker):
    resp = client.post(_WORKER_PATH)
    assert resp.status_code == 401


def test_401_on_wrong_secret(client: TestClient, configured_worker):
    resp = client.post(_WORKER_PATH, headers={"X-Worker-Secret": "wrong"})
    assert resp.status_code == 401


def test_idle_when_queue_is_empty(client: TestClient, configured_worker):
    resp = client.post(_WORKER_PATH, headers={"X-Worker-Secret": _GOOD_SECRET})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "idle"
    assert body["job_id"] is None


def test_drains_one_job_to_done_on_success(client: TestClient, db: Session, teacher, configured_worker):
    course = _make_course(db, teacher.id)
    job = enqueue_course_translation(db, course.id)

    with patch("app.api.v1.internal_translation_worker.translate_course_content") as orchestrator:
        resp = client.post(_WORKER_PATH, headers={"X-Worker-Secret": _GOOD_SECRET})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done"
    assert body["job_id"] == str(job.id)
    assert body["course_id"] == course.id
    assert body["attempts"] == 1
    orchestrator.assert_called_once()

    db.refresh(job)
    assert job.status == TranslationJobStatus.DONE
    assert job.finished_at is not None


def test_marks_job_failed_when_orchestrator_raises(client: TestClient, db: Session, teacher, configured_worker):
    course = _make_course(db, teacher.id)
    job = enqueue_course_translation(db, course.id)

    with patch(
        "app.api.v1.internal_translation_worker.translate_course_content",
        side_effect=RuntimeError("gemini exploded"),
    ):
        resp = client.post(_WORKER_PATH, headers={"X-Worker-Secret": _GOOD_SECRET})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["job_id"] == str(job.id)

    db.refresh(job)
    assert job.status == TranslationJobStatus.FAILED
    assert job.last_error is not None
    assert "RuntimeError" in job.last_error


def test_promotes_to_failed_permanent_at_attempt_cap(client: TestClient, db: Session, teacher, configured_worker):
    """A job that has already burned through the budget gets
    terminated on the next failure so the worker doesn't spin on it
    forever."""
    course = _make_course(db, teacher.id)
    job = enqueue_course_translation(db, course.id)
    # Simulate a worker that already retried this job up to one short
    # of the cap. The next failed tick should promote.
    job.attempts = TRANSLATION_JOB_MAX_ATTEMPTS - 1
    db.commit()

    with patch(
        "app.api.v1.internal_translation_worker.translate_course_content",
        side_effect=RuntimeError("still broken"),
    ):
        resp = client.post(_WORKER_PATH, headers={"X-Worker-Secret": _GOOD_SECRET})

    assert resp.status_code == 200
    db.refresh(job)
    assert job.status == TranslationJobStatus.FAILED_PERMANENT


def test_marks_failed_when_course_was_soft_deleted_between_enqueue_and_claim(
    client: TestClient, db: Session, teacher, configured_worker
):
    """The publish path enqueued the job for a course that has since
    been soft-deleted. ``get_course`` filters ``deleted_at`` and
    returns ``None``; the worker must not crash — it bumps the
    attempts counter and reports the failure cleanly.

    A hard-delete is a different shape: the FK ``ON DELETE CASCADE``
    on ``translation_jobs.course_id`` takes the queue row out with
    the course, so the worker never sees the orphan and the queue is
    just empty. That path is implicitly tested by every other
    test seeding a course that hasn't been hard-deleted.
    """
    from datetime import UTC, datetime

    course = _make_course(db, teacher.id)
    job = enqueue_course_translation(db, course.id)
    course.deleted_at = datetime.now(UTC)
    db.commit()
    course_id = course.id

    resp = client.post(_WORKER_PATH, headers={"X-Worker-Secret": _GOOD_SECRET})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["course_id"] == course_id

    db.refresh(job)
    assert job.status == TranslationJobStatus.FAILED
    assert "not found" in (job.last_error or "")


def test_concurrent_workers_dont_claim_the_same_row(client: TestClient, db: Session, teacher, configured_worker):
    """SKIP LOCKED guarantees two crons firing at the same time pick
    different rows. Two enqueued jobs + two ticks should drain both
    without either tick reporting idle."""
    c1 = _make_course(db, teacher.id)
    c2 = _make_course(db, teacher.id)
    enqueue_course_translation(db, c1.id)
    enqueue_course_translation(db, c2.id)

    with patch("app.api.v1.internal_translation_worker.translate_course_content"):
        first = client.post(_WORKER_PATH, headers={"X-Worker-Secret": _GOOD_SECRET}).json()
        second = client.post(_WORKER_PATH, headers={"X-Worker-Secret": _GOOD_SECRET}).json()

    assert {first["status"], second["status"]} == {"done"}
    assert first["job_id"] != second["job_id"]
    assert {first["course_id"], second["course_id"]} == {c1.id, c2.id}

    remaining = db.query(TranslationJob).filter(TranslationJob.status == TranslationJobStatus.QUEUED).count()
    assert remaining == 0


def test_sqlalchemy_error_still_bumps_attempts(client: TestClient, db: Session, teacher, configured_worker):
    """Regression: the ``except SQLAlchemyError`` path must persist the
    attempts increment. It used to ``db.rollback()`` before failing,
    which discarded the flush-only increment from ``claim_next_job`` and
    reverted ``attempts`` to its pre-claim value — so the failure was
    recorded with the WRONG (un-incremented) count."""
    course = _make_course(db, teacher.id)
    job = enqueue_course_translation(db, course.id)
    assert job.attempts == 0

    with patch(
        "app.api.v1.internal_translation_worker.translate_course_content",
        side_effect=SQLAlchemyError("deadlock detected"),
    ):
        resp = client.post(_WORKER_PATH, headers={"X-Worker-Secret": _GOOD_SECRET})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["attempts"] == 1

    db.refresh(job)
    assert job.status == TranslationJobStatus.FAILED
    # The increment survives the rollback — this is the whole point.
    assert job.attempts == 1
    assert "sqlalchemy" in (job.last_error or "")


def test_sqlalchemy_error_at_cap_promotes_to_failed_permanent(
    client: TestClient, db: Session, teacher, configured_worker
):
    """Regression for the poison-loop: a DB-failing job at one short of
    the attempt cap must promote to ``failed_permanent`` on the next
    tick. Before the fix the rolled-back increment meant the cap check
    read the stale count and re-queued the job forever (re-claimed every
    cron tick, burning Gemini calls, never visible in failed_permanent)."""
    course = _make_course(db, teacher.id)
    job = enqueue_course_translation(db, course.id)
    job.attempts = TRANSLATION_JOB_MAX_ATTEMPTS - 1
    db.commit()

    with patch(
        "app.api.v1.internal_translation_worker.translate_course_content",
        side_effect=SQLAlchemyError("still deadlocking"),
    ):
        resp = client.post(_WORKER_PATH, headers={"X-Worker-Secret": _GOOD_SECRET})

    assert resp.status_code == 200
    db.refresh(job)
    assert job.attempts == TRANSLATION_JOB_MAX_ATTEMPTS
    assert job.status == TranslationJobStatus.FAILED_PERMANENT


def test_sqlalchemy_poison_job_terminates_within_cap_ticks(client: TestClient, db: Session, teacher, configured_worker):
    """End-to-end poison-loop guard: a job that raises SQLAlchemyError on
    EVERY tick must reach ``failed_permanent`` after exactly
    TRANSLATION_JOB_MAX_ATTEMPTS ticks and then stop being claimable —
    not spin forever."""
    course = _make_course(db, teacher.id)
    job = enqueue_course_translation(db, course.id)

    with patch(
        "app.api.v1.internal_translation_worker.translate_course_content",
        side_effect=SQLAlchemyError("permanently broken"),
    ):
        for _ in range(TRANSLATION_JOB_MAX_ATTEMPTS):
            client.post(_WORKER_PATH, headers={"X-Worker-Secret": _GOOD_SECRET})
        # One more tick: the job is failed_permanent now, so the queue is
        # empty and the worker reports idle (it is NOT re-claimed).
        extra = client.post(_WORKER_PATH, headers={"X-Worker-Secret": _GOOD_SECRET}).json()

    assert extra["status"] == "idle"
    db.refresh(job)
    assert job.attempts == TRANSLATION_JOB_MAX_ATTEMPTS
    assert job.status == TranslationJobStatus.FAILED_PERMANENT
