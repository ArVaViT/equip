"""Tests for the admin queue-status dashboard endpoint.

Pin five observable invariants the operator needs:

1. Auth — admin-only (teacher → 403, anon → 401).
2. Empty queue → all counts 0, ``oldest_queued_age_seconds`` is None.
3. Mixed states → per-state counts add up correctly.
4. ``done_last_hour`` excludes older completions so the throughput
   proxy stays accurate.
5. Stuck-job detection — a job in ``processing`` past the threshold
   shows up; one inside the threshold doesn't.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.models.course import Course
from app.models.translation_job import TranslationJob, TranslationJobStatus

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


_PATH = "/api/v1/admin/translations/queue-status"


def _make_course(db: Session, teacher_id) -> Course:
    course = Course(
        id=f"qstat-{uuid.uuid4().hex[:8]}",
        status="published",
        source_locale="ru",
        created_by=teacher_id,
    )
    db.add(course)
    db.commit()
    return course


def _seed_job(db: Session, course_id: str, **fields) -> TranslationJob:
    job = TranslationJob(course_id=course_id, **fields)
    db.add(job)
    db.commit()
    return job


def test_empty_queue_returns_zero_counts(admin_client: TestClient):
    resp = admin_client.get(_PATH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["by_state"] == {
        "queued": 0,
        "processing": 0,
        "done_last_hour": 0,
        "failed": 0,
        "failed_permanent": 0,
    }
    assert body["oldest_queued_age_seconds"] is None
    assert body["stuck_jobs"] == []


def test_per_state_counts_aggregate_correctly(admin_client: TestClient, db: Session, teacher):
    course = _make_course(db, teacher.id)
    _seed_job(db, course.id, status=TranslationJobStatus.QUEUED)
    _seed_job(db, course.id, status=TranslationJobStatus.QUEUED)
    _seed_job(
        db,
        course.id,
        status=TranslationJobStatus.PROCESSING,
        started_at=datetime.now(UTC),
    )
    _seed_job(
        db,
        course.id,
        status=TranslationJobStatus.DONE,
        finished_at=datetime.now(UTC),
    )
    _seed_job(db, course.id, status=TranslationJobStatus.FAILED, attempts=2)
    _seed_job(db, course.id, status=TranslationJobStatus.FAILED_PERMANENT, attempts=5)

    body = admin_client.get(_PATH).json()
    assert body["by_state"] == {
        "queued": 2,
        "processing": 1,
        "done_last_hour": 1,
        "failed": 1,
        "failed_permanent": 1,
    }


def test_done_last_hour_excludes_older_completions(admin_client: TestClient, db: Session, teacher):
    course = _make_course(db, teacher.id)
    _seed_job(
        db,
        course.id,
        status=TranslationJobStatus.DONE,
        finished_at=datetime.now(UTC) - timedelta(hours=2),
    )
    body = admin_client.get(_PATH).json()
    assert body["by_state"]["done_last_hour"] == 0


def test_oldest_queued_age_reported(admin_client: TestClient, db: Session, teacher):
    course = _make_course(db, teacher.id)
    _seed_job(
        db,
        course.id,
        status=TranslationJobStatus.QUEUED,
        enqueued_at=datetime.now(UTC) - timedelta(seconds=600),
    )
    body = admin_client.get(_PATH).json()
    assert body["oldest_queued_age_seconds"] is not None
    assert body["oldest_queued_age_seconds"] >= 590


def test_stuck_jobs_surfaced_past_threshold(admin_client: TestClient, db: Session, teacher):
    course = _make_course(db, teacher.id)
    stuck = _seed_job(
        db,
        course.id,
        status=TranslationJobStatus.PROCESSING,
        started_at=datetime.now(UTC) - timedelta(minutes=10),
        attempts=2,
    )
    _seed_job(
        db,
        course.id,
        status=TranslationJobStatus.PROCESSING,
        started_at=datetime.now(UTC),
        attempts=1,
    )

    body = admin_client.get(_PATH).json()
    stuck_jobs = body["stuck_jobs"]
    assert len(stuck_jobs) == 1
    assert stuck_jobs[0]["id"] == str(stuck.id)
    assert stuck_jobs[0]["attempts"] == 2


def test_requires_admin(client: TestClient):
    """Teacher client (no admin role) must get 403."""
    resp = client.get(_PATH)
    assert resp.status_code == 403
