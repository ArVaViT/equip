"""ORM mapping for the Daily Challenge MVP.

Five tables — see ``supabase/migrations/20260529210000_add_daily_challenge_
foundation.sql`` for the canonical schema commentary. Mapped[] models
mirror the SQL exactly; the SQLite test path materialises the schema
via ``Base.metadata.create_all`` so partial indexes carry the
``sqlite_where`` variant alongside ``postgresql_where``.

Architecture decisions locked 2026-05-29 by Vadym after a 4-agent
parallel review. Read ``memory:
project-equip-daily-challenge-decisions.md`` before editing this file.

Translatable text lives in ``content_versions`` — there are no
``question_text`` / ``option_text`` / ``explanation`` columns on these
tables. The new entity types ``daily_challenge_question`` and
``daily_challenge_option`` are appended to ``ContentVersionEntityType``
in ``content_version.py``; the new field ``explanation`` is added to
``ContentVersionField`` in the same file.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime  # noqa: TC003 — Mapped[] runtime resolution

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

# SQLite uses JSON; Postgres uses JSONB. SQLAlchemy's generic ``JSON``
# type renders as JSONB on Postgres and TEXT-encoded JSON on SQLite,
# so the same model definition works on both backends without a
# dialect dance.
from app.core.database import Base


class DailyChallengeQuestionType(enum.StrEnum):
    """The two auto-validatable question shapes supported by the MVP.

    Locked by Vadym 2026-05-29: only types that can be graded by
    ``selected_option_id`` comparison — no string-match fuzziness, no
    teacher-graded essays on the daily surface. Adding a new type is
    an append-only migration that extends the CHECK constraint AND
    this enum AND the Pydantic ``Literal``; the registry-drift test
    catches mismatches.
    """

    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"


class DailyChallengeQuestionStatus(enum.StrEnum):
    """Forward-only editorial pipeline.

    Stages 2-5 correspond to Agent C's 5-stage review (scripture →
    doctrine → bilingual → pilot). ``published`` is the terminal live
    state. ``archived`` is the terminal end-of-life state for a
    question that has rotated out of the pool.

    The ``rejected`` boolean on the row is orthogonal: a question can
    be rejected at any stage. Rejection does NOT roll the status back;
    the row stays at whatever stage killed it, ``rejected=true``, and
    is excluded from the publishable pool forever.
    """

    DRAFT = "draft"
    SCRIPTURE_VALIDATED = "scripture_validated"
    DOCTRINALLY_REVIEWED = "doctrinally_reviewed"
    BILINGUALLY_REVIEWED = "bilingually_reviewed"
    PILOT_PASSED = "pilot_passed"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class DailyChallengeQuestion(Base):
    """Editorial bank entry. Translatable text lives in
    ``content_versions`` — see module docstring."""

    __tablename__ = "daily_challenge_questions"
    __table_args__ = (
        CheckConstraint(
            "question_type IN ('multiple_choice', 'true_false')",
            name="daily_challenge_questions_type_check",
        ),
        CheckConstraint(
            "status IN ('draft', 'scripture_validated', 'doctrinally_reviewed', "
            "'bilingually_reviewed', 'pilot_passed', 'published', 'archived')",
            name="daily_challenge_questions_status_check",
        ),
        CheckConstraint("bible_chapter > 0", name="daily_challenge_questions_chapter_pos"),
        CheckConstraint(
            "bible_verse_from IS NULL OR bible_verse_from > 0",
            name="daily_challenge_questions_verse_from_pos",
        ),
        CheckConstraint(
            "bible_verse_to IS NULL OR (bible_verse_from IS NOT NULL AND bible_verse_to >= bible_verse_from)",
            name="daily_challenge_questions_verse_range",
        ),
        Index(
            "ix_dc_questions_status_created",
            "status",
            "created_at",
            postgresql_where="rejected = FALSE AND status <> 'archived'",
            sqlite_where=text("rejected = 0 AND status <> 'archived'"),
        ),
        Index(
            "ix_dc_questions_publishable",
            "published_at",
            postgresql_where="status = 'published' AND rejected = FALSE",
            sqlite_where=text("status = 'published' AND rejected = 0"),
        ),
        Index(
            "ix_dc_questions_scripture",
            "bible_book",
            "bible_chapter",
            "bible_verse_from",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    question_type: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="draft", server_default="draft")

    # Rejection — orthogonal to status. See module docstring.
    rejected: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    rejected_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL")
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Publication breadcrumb — published_at being non-NULL + status =
    # 'published' + rejected = FALSE is the schedule trigger's gate.
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL")
    )

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL")
    )

    # Scripture anchor — every question must cite a verse range.
    bible_book: Mapped[str] = mapped_column(Text)
    bible_chapter: Mapped[int] = mapped_column(Integer)
    bible_verse_from: Mapped[int | None] = mapped_column(Integer)
    bible_verse_to: Mapped[int | None] = mapped_column(Integer)

    # Editorial category — free-form text. Pydantic Literal gates at
    # the API edge; categories can evolve without a migration.
    category: Mapped[str | None] = mapped_column(Text)

    # Source locale of the human-authored text (RU / EN / …). Same
    # detection pattern as ``courses.source_locale``.
    source_locale: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    options: Mapped[list[DailyChallengeOption]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="DailyChallengeOption.order_index",
    )

    def __repr__(self) -> str:
        return (
            f"<DailyChallengeQuestion id={self.id} type={self.question_type} "
            f"status={self.status} rejected={self.rejected}>"
        )


class DailyChallengeOption(Base):
    """One option on a question. ``option_text`` lives in
    ``content_versions`` — see module docstring."""

    __tablename__ = "daily_challenge_options"
    __table_args__ = (
        CheckConstraint("order_index BETWEEN 0 AND 5", name="daily_challenge_options_order_check"),
        Index("ix_dc_options_question", "question_id", "order_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("daily_challenge_questions.id", ondelete="CASCADE"),
    )
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    order_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    question: Mapped[DailyChallengeQuestion] = relationship(back_populates="options")


class DailyChallengeSchedule(Base):
    """Maps a UTC date to the question scheduled for that date.

    PK is ``challenge_date`` — at most one question per UTC day.
    A Postgres trigger (``dc_schedule_assert_publishable``) enforces
    that ``question_id`` references a row with ``status='published'``,
    ``rejected=false``, and ``published_at IS NOT NULL``.
    """

    __tablename__ = "daily_challenge_schedule"
    __table_args__ = (Index("ix_dc_schedule_question", "question_id"),)

    challenge_date: Mapped[date] = mapped_column(Date, primary_key=True)
    question_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("daily_challenge_questions.id", ondelete="RESTRICT"),
    )
    scheduled_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL")
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DailyChallengeAttempt(Base):
    """Per-user attempt. Live attempts move the streak; archive replays
    don't (enforced by the ``is_archive`` flag + the partial unique
    index + a CHECK constraint that archives have NULL ``streak_after``)."""

    __tablename__ = "daily_challenge_attempts"
    __table_args__ = (
        CheckConstraint(
            "NOT is_archive OR streak_after IS NULL",
            name="dc_attempts_archive_null_streak",
        ),
        Index(
            "uniq_dc_attempts_live_per_day",
            "user_id",
            "challenge_date",
            unique=True,
            postgresql_where="is_archive = FALSE",
            sqlite_where=text("is_archive = 0"),
        ),
        Index("ix_dc_attempts_user_date", "user_id", "challenge_date"),
        Index("ix_dc_attempts_question", "question_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"))
    question_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("daily_challenge_questions.id", ondelete="CASCADE"),
    )
    challenge_date: Mapped[date] = mapped_column(Date)
    is_archive: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    selected_option_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("daily_challenge_options.id", ondelete="SET NULL"),
    )
    is_correct: Mapped[bool] = mapped_column(Boolean)
    streak_after: Mapped[int | None] = mapped_column(Integer)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DailyChallengeStreak(Base):
    """Per-user streak counter. YouVersion-style semantics — any
    submission counts. See module docstring for the math."""

    __tablename__ = "daily_challenge_streaks"
    __table_args__ = (
        CheckConstraint("current_streak >= 0", name="dc_streaks_current_nonneg"),
        CheckConstraint("longest_streak >= 0", name="dc_streaks_longest_nonneg"),
        Index(
            "ix_dc_streaks_last_engaged",
            "last_engaged_date",
            postgresql_where="current_streak >= 1",
            sqlite_where=text("current_streak >= 1"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    current_streak: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    longest_streak: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_engaged_date: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DailyChallengeQuestionEvent(Base):
    """Append-only audit trail for editorial transitions + AI rounds.

    Sprint 3 adds this so the editorial team can answer "why was this
    question moved from doctrinally_reviewed to rejected?" without
    log-diving. The AI generation orchestrator (future sprint) writes
    here too — every cross-critique, every synthesis, every validation
    check leaves a row keyed by ``generation_run_id``.

    The schema is the index; the payload lives in the JSON column.
    Adding a new event type is an additive migration on the CHECK
    constraint; adding a new field on an existing event_type is no
    migration at all (the service layer decides the shape).
    """

    __tablename__ = "daily_challenge_question_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('status_change', 'rejected', 'published', "
            "'scheduled', 'unscheduled', 'ai_generated', 'ai_critique', "
            "'ai_synthesis', 'scripture_validated', 'doctrinally_reviewed', "
            "'bilingually_reviewed', 'pilot_summary')",
            name="dc_q_events_type_check",
        ),
        Index(
            "ix_dc_q_events_question_created",
            "question_id",
            "created_at",
        ),
        Index(
            "ix_dc_q_events_generation_run",
            "generation_run_id",
            "created_at",
            postgresql_where="generation_run_id IS NOT NULL",
            sqlite_where=text("generation_run_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("daily_challenge_questions.id", ondelete="CASCADE"),
    )
    event_type: Mapped[str] = mapped_column(Text)
    generation_run_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL")
    )
    details: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DailyChallengePilotReview(Base):
    """Stage 5 pilot answers + engagement ratings.

    One row per (question, reviewer). The promotion threshold (≥80%
    correct rate + ≥3.5/5 mean engagement, n≥5) is computed in the
    service layer rather than persisted as a denormalised column,
    because the threshold is an editorial knob we may tune.

    Updating a review re-uses the same row — the service layer does
    an upsert; the unique constraint enforces uniqueness.
    """

    __tablename__ = "daily_challenge_pilot_reviews"
    __table_args__ = (
        UniqueConstraint("question_id", "reviewer_id", name="uq_dc_pilot_reviews_pair"),
        CheckConstraint(
            "engagement_rating BETWEEN 1 AND 5",
            name="dc_pilot_reviews_rating_check",
        ),
        Index("ix_dc_pilot_reviews_question", "question_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("daily_challenge_questions.id", ondelete="CASCADE"),
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="SET NULL"),
    )
    answered_correctly: Mapped[bool] = mapped_column(Boolean)
    engagement_rating: Mapped[int] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
