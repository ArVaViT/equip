"""Tests for the publish-time translation queue.

Pins six properties the publish path + worker rely on:

* enqueue creates a row in ``queued`` state
* enqueue is idempotent — a second call for the same course returns
  the same pending job, never creates a duplicate
* enqueue creates a NEW job once the previous one is ``done``
* ``claim_next_job`` claims oldest first, flips to ``processing``,
  bumps attempts
* ``claim_next_job`` returns ``None`` when the queue is empty
* ``mark_job_failed`` promotes to ``failed_permanent`` at the cap
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.course import Course
from app.models.translation_job import (
    TRANSLATION_JOB_MAX_ATTEMPTS,
    TranslationJob,
    TranslationJobStatus,
)
from app.services.translation.queue import (
    claim_next_job,
    enqueue_course_translation,
    mark_job_done,
    mark_job_failed,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _make_course(db: Session, teacher_id) -> Course:
    course = Course(
        id=f"queue-{uuid.uuid4().hex[:8]}",
        status="published",
        source_locale="ru",
        created_by=teacher_id,
    )
    db.add(course)
    db.commit()
    return course


def test_enqueue_creates_a_queued_row(db: Session, teacher):
    course = _make_course(db, teacher.id)
    job = enqueue_course_translation(db, course.id, requested_by=teacher.id)
    assert job.id is not None
    assert job.course_id == course.id
    assert job.status == TranslationJobStatus.QUEUED
    assert job.attempts == 0
    assert job.started_at is None
    assert job.finished_at is None


def test_enqueue_is_idempotent_for_pending_job(db: Session, teacher):
    """A second enqueue for the same course must reuse the pending
    job, not create a duplicate. Otherwise a teacher mashing Save
    five times in a row would queue five identical Gemini-bound
    pipeline runs."""
    course = _make_course(db, teacher.id)
    first = enqueue_course_translation(db, course.id, requested_by=teacher.id)
    second = enqueue_course_translation(db, course.id, requested_by=teacher.id)
    assert first.id == second.id

    rows = db.query(TranslationJob).filter_by(course_id=course.id).all()
    assert len(rows) == 1


def test_enqueue_creates_new_job_after_previous_is_done(db: Session, teacher):
    """Once the previous job is ``done`` the publish path is allowed
    to enqueue another one — a teacher who keeps editing a published
    course needs every edit to land in the queue eventually."""
    course = _make_course(db, teacher.id)
    first = enqueue_course_translation(db, course.id, requested_by=teacher.id)
    first.status = TranslationJobStatus.DONE
    db.commit()

    second = enqueue_course_translation(db, course.id, requested_by=teacher.id)
    assert second.id != first.id
    assert second.status == TranslationJobStatus.QUEUED


def test_claim_next_job_picks_oldest_and_flips_state(db: Session, teacher):
    course1 = _make_course(db, teacher.id)
    course2 = _make_course(db, teacher.id)
    older = enqueue_course_translation(db, course1.id)
    enqueue_course_translation(db, course2.id)

    claimed = claim_next_job(db)
    assert claimed is not None
    assert claimed.id == older.id
    assert claimed.status == TranslationJobStatus.PROCESSING
    assert claimed.started_at is not None
    assert claimed.attempts == 1


def test_claim_next_job_returns_none_on_empty_queue(db: Session):
    assert claim_next_job(db) is None


def test_claim_includes_failed_jobs_for_retry(db: Session, teacher):
    """A transient Gemini outage that promoted the job to ``failed``
    must be re-claimable by the next worker pass; ``failed_permanent``
    is the only terminal state."""
    course = _make_course(db, teacher.id)
    job = enqueue_course_translation(db, course.id)
    job.status = TranslationJobStatus.FAILED
    job.attempts = 1
    db.commit()

    claimed = claim_next_job(db)
    assert claimed is not None
    assert claimed.id == job.id
    assert claimed.status == TranslationJobStatus.PROCESSING
    assert claimed.attempts == 2


def test_mark_job_done(db: Session, teacher):
    course = _make_course(db, teacher.id)
    job = enqueue_course_translation(db, course.id)
    claimed = claim_next_job(db)
    assert claimed is not None

    mark_job_done(db, claimed)
    db.refresh(job)
    assert job.status == TranslationJobStatus.DONE
    assert job.finished_at is not None
    assert job.last_error is None


def test_mark_job_failed_requeues_below_attempt_cap(db: Session, teacher):
    course = _make_course(db, teacher.id)
    job = enqueue_course_translation(db, course.id)
    claimed = claim_next_job(db)
    assert claimed is not None
    assert claimed.attempts == 1

    mark_job_failed(db, claimed, error="gemini timeout")
    db.refresh(job)
    assert job.status == TranslationJobStatus.FAILED
    assert job.last_error == "gemini timeout"


def test_mark_job_failed_promotes_to_permanent_at_cap(db: Session, teacher):
    """At the attempt cap the job must promote to ``failed_permanent``
    so the worker never tries again — only the admin reset endpoint
    can revive it."""
    course = _make_course(db, teacher.id)
    job = enqueue_course_translation(db, course.id)
    job.attempts = TRANSLATION_JOB_MAX_ATTEMPTS
    db.commit()
    job.status = TranslationJobStatus.PROCESSING  # imagine just-claimed
    db.commit()

    mark_job_failed(db, job, error="permanent")
    db.refresh(job)
    assert job.status == TranslationJobStatus.FAILED_PERMANENT


def test_mark_job_failed_truncates_long_error_text(db: Session, teacher):
    """The ``last_error`` column gets very long stack traces; the helper
    truncates to keep the queue table small enough for an admin to scan
    without an editor."""
    course = _make_course(db, teacher.id)
    job = enqueue_course_translation(db, course.id)
    claimed = claim_next_job(db)
    assert claimed is not None

    mark_job_failed(db, claimed, error="x" * 5000)
    db.refresh(job)
    assert job.last_error is not None
    assert len(job.last_error) <= 2000
