"""ORM mapping for ``content_versions`` — the single multi-locale text store.

Every ``(entity, field, locale)`` is a first-class row with its own
provenance, status, and version chain. Replaces the original
dual-table model: entity text columns held the source and a
``content_translations`` overlay held the rest. Both are gone — the
source columns were dropped entity by entity, the overlay table with
them.

Design rules pinned by the schema
---------------------------------

* ``locale`` has no CHECK constraint at the DB level — adding a new
  language is INSERT, not DDL. The supported set is validated only at
  the API edge via the Pydantic ``LocaleCode`` Literal.
* Exactly one ACTIVE version per ``(entity, field, locale)`` via the
  partial unique index ``uniq_content_versions_active``. Updates
  supersede (set the old row's ``superseded_by``) instead of
  overwriting — translation history is never destroyed.
* ``origin`` distinguishes ``human`` (typed by a teacher / admin) from
  ``mt`` (Gemini output). The MT pipeline never overwrites a ``human``
  row; that's enforced by the orchestrator, not by a DB constraint
  (constraint would be too restrictive — operators can override).
* ``source_version_id`` lets MT rows point at the EXACT version they
  were translated from. When a human row is superseded, every MT
  derivative is precisely invalidatable.
* ``status`` is a typed enum (``ContentVersionStatus``) — every
  Python comparison goes through the enum so a typo silently breaks
  the build instead of silently mis-routing the orchestrator.
"""

import enum
import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, SmallInteger, Text, func, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Mirrors ``content_versions.entity_type`` (no DB CHECK — see schema
# comment). The set here is the SUPPORTED-by-the-app surface; adding
# a new entity type means appending here AND ensuring the registry
# (``app/services/translation/registry.py`` or its V1 successor)
# knows how to walk it. No migration needed.
ContentVersionEntityType = Literal[
    "course",
    "module",
    "chapter",
    "chapter_block",
    "quiz",
    "quiz_question",
    "quiz_option",
    "assignment",
    "announcement",
    "course_event",
    "cohort",
    "daily_challenge_question",
    "daily_challenge_option",
    "rubric",
    "rubric_criterion",
    "rubric_level",
]

ContentVersionField = Literal[
    "title",
    "description",
    "content",
    "question_text",
    "option_text",
    "instructions",
    "explanation",
]

ContentVersionOrigin = Literal["human", "mt"]


class ContentVersionStatus(enum.StrEnum):
    """Lifecycle of a single ``content_versions`` row.

    The string values match the ``content_versions_status_check`` CHECK
    constraint (see ``__table_args__`` below). Every Python comparison
    against ``ContentVersion.status`` goes through the enum so a typo
    surfaces at the type-check pass instead of at runtime as a quiet
    "no rows matched".
    """

    OK = "ok"
    # The provider answered, and the answer failed a structural check
    # against its source — a lost scripture marker, halved markup, the
    # wrong language. The text is kept (a human reviewing it needs to
    # see what came back) but it is not servable: readers filter on
    # ``ok``, so this row shows as "not translated yet" until someone
    # accepts or replaces it. See ``services/translation/validation.py``.
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"
    FAILED_PERMANENT = "failed_permanent"


# How many MT attempts we tolerate before promoting to
# ``failed_permanent``. Centralised here so admin tooling that
# re-queues a row refers back to the same constant.
#
# An "attempt" is the model being shown this text and producing
# something unusable. A call that never reached the model — a 429, a
# 5xx, a timeout, an exhausted balance — is not one, and does not
# increment this counter: see ``record_mt_failure``'s ``transient``.
# The cap exists to stop asking about a text that defeats translation,
# and an outage is not a fact about any text.
CONTENT_VERSION_MAX_ATTEMPTS = 5


class ContentVersion(Base):
    __tablename__ = "content_versions"
    __table_args__ = (
        # Partial unique: exactly one ACTIVE version per
        # (entity, field, locale). Superseded rows are excluded so a
        # teacher can supersede a translation without violating the
        # constraint. Both ``postgresql_where`` (prod) and
        # ``sqlite_where`` (tests) are required — without the SQLite
        # variant, SQLite emits a full unique constraint that would
        # forbid supersession.
        Index(
            "uniq_content_versions_active",
            "entity_type",
            "entity_id",
            "field",
            "locale",
            unique=True,
            postgresql_where="superseded_by IS NULL",
            sqlite_where=text("superseded_by IS NULL"),
        ),
        Index(
            "ix_content_versions_active_lookup",
            "entity_type",
            "entity_id",
            "locale",
            postgresql_where="superseded_by IS NULL AND status = 'ok'",
            sqlite_where=text("superseded_by IS NULL AND status = 'ok'"),
        ),
        Index("ix_content_versions_entity", "entity_type", "entity_id"),
        # The review queue: rows a human still has to accept or replace.
        Index(
            "ix_content_versions_needs_review",
            "locale",
            "created_at",
            postgresql_where="superseded_by IS NULL AND status = 'needs_review'",
            sqlite_where=text("superseded_by IS NULL AND status = 'needs_review'"),
        ),
        Index(
            "ix_content_versions_source_version",
            "source_version_id",
            postgresql_where="source_version_id IS NOT NULL",
            sqlite_where=text("source_version_id IS NOT NULL"),
        ),
        CheckConstraint("origin IN ('human', 'mt')", name="content_versions_origin_check"),
        CheckConstraint(
            "status IN ('ok', 'needs_review', 'failed', 'failed_permanent')",
            name="content_versions_status_check",
        ),
        CheckConstraint("attempts >= 0", name="content_versions_attempts_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    entity_type: Mapped[str] = mapped_column(Text)
    entity_id: Mapped[str] = mapped_column(Text)
    field: Mapped[str] = mapped_column(Text)
    locale: Mapped[str] = mapped_column(Text)

    text: Mapped[str] = mapped_column(Text)

    origin: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="ok", server_default="ok")

    # Why a ``needs_review`` row is not servable, in words a person can
    # act on ("[scripture_marker_mismatch] lost 1 (VERSE_a3f9c2b1)").
    # NULL on every other status.
    review_reason: Mapped[str | None] = mapped_column(Text)

    source_hash: Mapped[str | None] = mapped_column(Text)
    source_locale: Mapped[str | None] = mapped_column(Text)
    source_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("content_versions.id", ondelete="SET NULL"),
    )

    authored_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="SET NULL"),
    )

    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    #: Which generation of the translation pipeline produced this row.
    #: Lower than ``TRANSLATOR_VERSION`` means the row predates the rules
    #: now in force — the glossary, the per-language calque notes, the
    #: correcting pass — and is due for another attempt. Human rows keep
    #: 0 and are never re-translated.
    translator_version: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")

    superseded_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("content_versions.id", ondelete="SET NULL"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<ContentVersion entity={self.entity_type}:{self.entity_id} "
            f"field={self.field} locale={self.locale} "
            f"origin={self.origin} status={self.status}>"
        )
