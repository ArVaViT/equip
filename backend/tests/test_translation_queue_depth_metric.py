"""Tests for ``equip.translation.queue_*`` gauge emission.

These metrics drive the Datadog ``translation-queue-backlog`` monitor
and the Course Engagement dashboard's queue-depth widget. Emission
must be:

* Idempotent — gauges emit once per worker tick, not per claim.
* Non-raising — a metric failure must NEVER break the worker tick
  (the queue itself drains regardless).
* Accurate — ``queue_depth`` counts ``queued + failed`` (the
  claimable backlog), not ``done`` (already-processed work).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.api.v1.internal_translation_worker import _emit_queue_gauges
from app.models.translation_job import TranslationJob, TranslationJobStatus
from app.models.user import User, UserRole

from ._cv_helpers import make_course_with_text
from .conftest import TEACHER_ID

if TYPE_CHECKING:
    import pytest
    from sqlalchemy.orm import Session


def _seed_jobs(db: Session, counts_per_status: dict[str, int]) -> None:
    """Insert ``n`` jobs at each status value listed.

    Each job needs a courses row to satisfy the FK; we mint one
    per job up front.
    """
    if db.query(User).filter(User.id == TEACHER_ID).first() is None:
        db.add(User(id=TEACHER_ID, email="t@e.com", full_name="X", role=UserRole.TEACHER.value))
        db.flush()
    for status, n in counts_per_status.items():
        for i in range(n):
            course_id = f"c-{status}-{i}"
            make_course_with_text(
                db,
                course_id=course_id,
                title=f"T {status} {i}",
                status="draft",
                created_by=TEACHER_ID,
            )
            db.add(
                TranslationJob(
                    course_id=course_id,
                    status=status,
                )
            )
    db.commit()


class TestQueueGaugeEmission:
    def test_emits_three_gauges_on_empty_queue(
        self,
        db: Session,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Empty queue → all gauges fire with value 0. Absence-of-data
        on the dashboard tile would look like a metric outage; explicit
        zeros prove the worker is alive."""
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            _emit_queue_gauges(db)
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        assert any("equip.translation.queue_depth" in m and "value=0.0" in m for m in msgs)
        assert any("equip.translation.queue_processing" in m and "value=0.0" in m for m in msgs)
        assert any("equip.translation.queue_failed_permanent" in m and "value=0.0" in m for m in msgs)

    def test_queue_depth_counts_queued_plus_failed(
        self,
        db: Session,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """``queue_depth`` is the *claimable* backlog. ``failed`` rows
        are eligible for re-claim by the next worker pass, so they
        belong in the backlog gauge alongside ``queued``."""
        _seed_jobs(
            db,
            {
                TranslationJobStatus.QUEUED.value: 3,
                TranslationJobStatus.FAILED.value: 2,
                TranslationJobStatus.DONE.value: 10,
                TranslationJobStatus.PROCESSING.value: 1,
            },
        )
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            _emit_queue_gauges(db)
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        depth = [m for m in msgs if "equip.translation.queue_depth" in m]
        assert depth, "expected queue_depth gauge to fire"
        # 3 queued + 2 failed = 5; done + processing are NOT in depth.
        assert any("value=5.0" in m for m in depth)

    def test_queue_processing_counts_only_processing(
        self,
        db: Session,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _seed_jobs(
            db,
            {
                TranslationJobStatus.PROCESSING.value: 4,
                TranslationJobStatus.QUEUED.value: 7,
            },
        )
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            _emit_queue_gauges(db)
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        processing = [m for m in msgs if "equip.translation.queue_processing" in m]
        assert processing
        assert any("value=4.0" in m for m in processing)

    def test_queue_failed_permanent_counts_only_dead_letters(
        self,
        db: Session,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _seed_jobs(
            db,
            {
                TranslationJobStatus.FAILED_PERMANENT.value: 2,
                TranslationJobStatus.FAILED.value: 5,
            },
        )
        with caplog.at_level(logging.INFO, logger="equip.metric"):
            _emit_queue_gauges(db)
        msgs = [r.getMessage() for r in caplog.records if r.name == "equip.metric"]
        permanent = [m for m in msgs if "equip.translation.queue_failed_permanent" in m]
        assert permanent
        assert any("value=2.0" in m for m in permanent)
        # ``failed`` (re-claimable) MUST NOT be folded into the
        # ``failed_permanent`` gauge — the two are routed to
        # different dashboard widgets.
        assert not any("value=7.0" in m for m in permanent)


class TestQueueHealthEndpoint:
    """The /internal/translation-queue/health endpoint is the curl-check
    surface for ops; pinning it here also pins the get_queue_status
    shape used by the metric emitter."""

    def test_health_returns_per_status_counts(
        self,
        db: Session,
        client,
        monkeypatch,
    ) -> None:
        from app.core import config

        # Endpoint requires worker secret; stub the env-backed setting.
        class FakeSecret:
            @staticmethod
            def get_secret_value() -> str:
                return "test-worker-secret"

        monkeypatch.setattr(config.settings, "TRANSLATION_WORKER_SECRET", FakeSecret())

        _seed_jobs(
            db,
            {
                TranslationJobStatus.QUEUED.value: 2,
                TranslationJobStatus.DONE.value: 5,
                TranslationJobStatus.FAILED_PERMANENT.value: 1,
            },
        )
        resp = client.get(
            "/api/v1/internal/translation-queue/health",
            headers={"X-Worker-Secret": "test-worker-secret"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["queued"] == 2
        assert body["done"] == 5
        assert body["failed_permanent"] == 1
        assert body["processing"] == 0
        assert body["failed"] == 0

    def test_health_rejects_missing_secret(
        self,
        db: Session,
        client,
        monkeypatch,
    ) -> None:
        from app.core import config

        class FakeSecret:
            @staticmethod
            def get_secret_value() -> str:
                return "another-secret"

        monkeypatch.setattr(config.settings, "TRANSLATION_WORKER_SECRET", FakeSecret())

        resp = client.get("/api/v1/internal/translation-queue/health")
        assert resp.status_code == 401
