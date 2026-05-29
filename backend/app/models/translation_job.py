"""ORM mapping for ``translation_jobs`` — the publish-time work queue.

Design rationale lives in
``supabase/migrations/20260529150000_translation_jobs_table.sql``.

Lifecycle
---------

::

    queued ── claim_next_job ──▶ processing ── mark_done ──▶ done
                                     │
                                     ├── mark_failed (attempts < cap) ──▶ failed ──┐
                                     │                                             │
                                     ├── mark_failed (attempts >= cap) ──▶ failed_permanent
                                     │                                             │
                                     └── janitor pass (stale)         ──▶ failed ◀─┘

``failed`` jobs are re-claimable by the worker on the next pass; the
queue helper's claim predicate matches both ``queued`` and ``failed``
so a transient Gemini outage doesn't permanently lose the job.
``failed_permanent`` is terminal — the admin reset surface from Phase
5au is the only escape hatch.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime  # noqa: TC003 — Mapped[] runtime resolution

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TranslationJobStatus(enum.StrEnum):
    """Lifecycle of a single ``translation_jobs`` row.

    The string values mirror the ``translation_jobs_status_check``
    CHECK constraint in the migration. Every Python comparison goes
    through the enum so a typo surfaces at type-check time, not at
    runtime as a silent ``WHERE status = 'queed'`` no-op.
    """

    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    FAILED_PERMANENT = "failed_permanent"


# Same cap as ``content_versions``: after 5 attempts the job is
# considered terminally broken and the admin reset endpoint is the
# only path back to ``failed``. Centralised here so the queue helper
# + admin tooling refer to the same constant.
TRANSLATION_JOB_MAX_ATTEMPTS = 5


class TranslationJob(Base):
    __tablename__ = "translation_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'processing', 'done', 'failed', 'failed_permanent')",
            name="translation_jobs_status_check",
        ),
        CheckConstraint("attempts >= 0", name="translation_jobs_attempts_check"),
        Index(
            "ix_translation_jobs_queued",
            "enqueued_at",
            postgresql_where="status = 'queued'",
        ),
        Index("ix_translation_jobs_course", "course_id", "enqueued_at"),
        Index(
            "ix_translation_jobs_processing",
            "started_at",
            postgresql_where="status = 'processing'",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[str] = mapped_column(Text, ForeignKey("courses.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(Text, default=TranslationJobStatus.QUEUED, server_default="queued")

    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)

    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="SET NULL"),
    )

    def __repr__(self) -> str:
        return f"<TranslationJob id={self.id} course={self.course_id} status={self.status} attempts={self.attempts}>"
