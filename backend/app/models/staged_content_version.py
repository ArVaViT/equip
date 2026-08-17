"""ORM mapping for ``staged_content_versions`` — edits that are not ready.

Design rationale lives in
``supabase/migrations/20260817114500_an_edit_reaches_every_language_at_once.sql``.

One row is one (entity, field, locale) of an edit in flight: the
teacher's new text (``origin='human'``) or one of its translations
(``origin='mt'``). They live together here, invisible to every reader,
until the field is whole — every locale present, every one ``ok`` — at
which point ``staged_edits.promote`` writes them into
``content_versions`` in a single transaction and clears them from here.

Why not a column on ``content_versions``
----------------------------------------

Because "not ready to be seen" and "one predicate away from being
seen" would then be the same state, in thirty-one query sites, forever.
A table that the reading path never names cannot leak into it.

Invariants
----------

* At most one row per (entity_type, entity_id, field, locale) — a
  re-edit overwrites rather than superseding. Unreleased text has no
  readers, so it has no history worth keeping.
* Exactly one ``human`` row per (entity, field) while an edit is in
  flight: the edit itself. Everything else is its translations.
* ``source_hash`` ties each translation to the exact human text it was
  made from, so a second edit arriving mid-flight cannot promote the
  translations of the first.
* An empty table is the resting state.
"""

from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003 — Mapped[] runtime resolution

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StagedContentVersion(Base):
    __tablename__ = "staged_content_versions"
    __table_args__ = (
        Index(
            "uniq_staged_content_versions_key",
            "entity_type",
            "entity_id",
            "field",
            "locale",
            unique=True,
        ),
        Index("ix_staged_content_versions_entity", "entity_type", "entity_id"),
        Index("ix_staged_content_versions_course", "course_id"),
        Index("ix_staged_content_versions_created", "created_at"),
        CheckConstraint("origin IN ('human', 'mt')", name="staged_content_versions_origin_check"),
        CheckConstraint(
            "status IN ('ok', 'needs_review', 'failed', 'failed_permanent')",
            name="staged_content_versions_status_check",
        ),
        CheckConstraint("attempts >= 0", name="staged_content_versions_attempts_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str] = mapped_column(Text)
    field: Mapped[str] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(Text)

    # Denormalised so every course-scoped question is one indexed read
    # instead of a tree walk, and so a deleted course takes its
    # unreleased edits with it (the polymorphic entity key cannot have
    # a foreign key; this can).
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))

    text: Mapped[str] = mapped_column(Text)

    origin: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="ok", server_default="ok")
    review_reason: Mapped[str | None] = mapped_column(Text)

    source_hash: Mapped[str | None] = mapped_column(Text)
    source_locale: Mapped[str | None] = mapped_column(Text)

    authored_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="SET NULL"),
    )

    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<StagedContentVersion entity={self.entity_type}:{self.entity_id} "
            f"field={self.field} locale={self.locale} "
            f"origin={self.origin} status={self.status}>"
        )
