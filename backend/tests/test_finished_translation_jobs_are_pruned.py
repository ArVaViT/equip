"""Finished translation jobs do not pile up forever (2026-10-03).

1 120 rows, all done, 1 076 older than thirty days — a table nothing pruned.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.models.course import Course
from app.models.translation_job import TranslationJob, TranslationJobStatus
from app.services.translation.job_retention import KEEP_PER_COURSE, prune_finished_jobs

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _course(db: Session, teacher_id) -> Course:
    course = Course(id=f"jobs-{uuid.uuid4().hex[:8]}", status="published", source_locale="ru", created_by=teacher_id)
    db.add(course)
    db.commit()
    return course


def _job(db: Session, course_id: str, *, days_ago: int, status: str = TranslationJobStatus.DONE) -> None:
    at = datetime.now(UTC) - timedelta(days=days_ago)
    db.add(TranslationJob(course_id=course_id, status=status, enqueued_at=at, finished_at=at))


def test_old_finished_jobs_go_and_the_newest_ten_per_course_stay(db: Session, teacher) -> None:
    busy = _course(db, teacher.id)
    quiet = _course(db, teacher.id)
    for d in range(40, 60):  # twenty old done jobs on a busy course
        _job(db, busy.id, days_ago=d)
    for d in range(40, 43):  # three old done jobs on a quiet one
        _job(db, quiet.id, days_ago=d)
    _job(db, busy.id, days_ago=50, status=TranslationJobStatus.FAILED)  # not done: never touched
    db.commit()

    removed = prune_finished_jobs(db, older_than_days=30)

    assert removed == 20 - KEEP_PER_COURSE
    left_busy = db.query(TranslationJob).filter_by(course_id=busy.id, status=TranslationJobStatus.DONE).count()
    assert left_busy == KEEP_PER_COURSE
    # A quiet course keeps all it has: its admin list never comes up empty.
    assert db.query(TranslationJob).filter_by(course_id=quiet.id).count() == 3
    assert db.query(TranslationJob).filter_by(status=TranslationJobStatus.FAILED).count() == 1


def test_recent_finished_jobs_are_kept(db: Session, teacher) -> None:
    course = _course(db, teacher.id)
    for d in range(15):
        _job(db, course.id, days_ago=d)
    db.commit()

    assert prune_finished_jobs(db, older_than_days=30) == 0
