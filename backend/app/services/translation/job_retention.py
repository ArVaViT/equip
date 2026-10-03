"""Retention for finished translation jobs.

Every course save enqueues a ``translation_jobs`` row and the worker marks it
``done``; nothing ever removed one. 1 120 rows by 2026-10-03, all done, 1 076
of them older than thirty days — a table that only grows, read by nothing but
the admin's «recent jobs» list and the queue counters.

A finished job is not history anybody reads: no foreign key points at it, and
a content version does not carry a job id. So: past the same retention window
as superseded machine translations, delete it — keeping the newest few per
course, so the admin list never comes up empty for a quiet course.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select

from app.models.translation_job import TranslationJob, TranslationJobStatus

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

#: Finished jobs kept per course whatever their age.
KEEP_PER_COURSE = 10


def prune_finished_jobs(db: Session, *, older_than_days: int, limit: int = 500) -> int:
    """Delete up to ``limit`` done jobs older than the window, keeping the
    ``KEEP_PER_COURSE`` newest per course. Commits when it deletes; returns
    how many rows went."""
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    ranked = (
        select(
            TranslationJob.id,
            func.row_number()
            .over(partition_by=TranslationJob.course_id, order_by=TranslationJob.enqueued_at.desc())
            .label("rn"),
        )
        .where(TranslationJob.status == TranslationJobStatus.DONE)
        .subquery()
    )
    ids = (
        db.execute(
            select(TranslationJob.id)
            .join(ranked, ranked.c.id == TranslationJob.id)
            .where(
                TranslationJob.status == TranslationJobStatus.DONE,
                func.coalesce(TranslationJob.finished_at, TranslationJob.enqueued_at) < cutoff,
                ranked.c.rn > KEEP_PER_COURSE,
            )
            .order_by(TranslationJob.enqueued_at.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    if not ids:
        return 0
    db.execute(delete(TranslationJob).where(TranslationJob.id.in_(ids)))
    db.commit()
    return len(ids)
