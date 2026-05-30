"""Editorial-side service for the Daily Challenge.

Sprint 3 covers the manual editorial flow — teachers and admins
create questions in DRAFT, walk them forward through the 5 stages,
reject what fails review, publish what passes, and schedule what's
published. The AI generation orchestrator lands in a future sprint;
it writes to the same ``daily_challenge_question_events`` audit
table this service writes to, so the audit history is unified across
manual + AI flows.

Status transition rules — forward-only

    draft -> scripture_validated -> doctrinally_reviewed
          -> bilingually_reviewed -> pilot_passed -> published

The service rejects out-of-order or backward transitions. ``archived``
is a terminal forward transition allowed from any non-rejected stage
(retire a question without deleting it).

Rejection is orthogonal — a rejected question stays at whatever stage
killed it but is excluded from the publishable pool forever.

Bilingual text writes go through ``record_human_version`` directly
(daily challenge entities are platform-wide; there's no course parent
to drive ``reconcile_entity_if_course_published``). Each create or
PATCH call also runs the language detector against the new text to
update ``source_locale``.
"""

from __future__ import annotations

import uuid  # noqa: TC003 — runtime resolution via dataclass annotations
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from app.models.daily_challenge import (
    DailyChallengeOption,
    DailyChallengeQuestion,
    DailyChallengeQuestionEvent,
    DailyChallengeQuestionStatus,
    DailyChallengeSchedule,
)
from app.services.content_versions.write import record_human_version
from app.services.language_detection import detect_locale

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# Forward edges for ``promote_status``. Note that ``pilot_passed →
# published`` is deliberately NOT in this map — publishing requires
# stamping ``published_at`` / ``published_by`` (the schedule trigger
# checks the former), which the generic promote helper doesn't know
# about. The caller invokes ``publish_question`` for that transition
# instead. This keeps the publish event auditable as a distinct
# action and means a quiet promote can't accidentally publish.
_FORWARD_TRANSITIONS: dict[str, str] = {
    DailyChallengeQuestionStatus.DRAFT.value: DailyChallengeQuestionStatus.SCRIPTURE_VALIDATED.value,
    DailyChallengeQuestionStatus.SCRIPTURE_VALIDATED.value: DailyChallengeQuestionStatus.DOCTRINALLY_REVIEWED.value,
    DailyChallengeQuestionStatus.DOCTRINALLY_REVIEWED.value: DailyChallengeQuestionStatus.BILINGUALLY_REVIEWED.value,
    DailyChallengeQuestionStatus.BILINGUALLY_REVIEWED.value: DailyChallengeQuestionStatus.PILOT_PASSED.value,
}


class StatusTransitionError(Exception):
    """Raised when a status promote violates the forward-only DAG."""


class QuestionRejectedError(Exception):
    """Raised when the caller tries to promote / publish / schedule a
    question that's already rejected."""


class NotPublishableError(Exception):
    """Raised when the caller tries to schedule a question that's not
    at status=published + non-rejected + published_at set."""


@dataclass(frozen=True, slots=True)
class OptionDraft:
    """Author-supplied option payload for ``create_question``."""

    text: str
    is_correct: bool


def _log_event(
    db: Session,
    *,
    question_id: uuid.UUID | None,
    event_type: str,
    actor_id: uuid.UUID | None,
    details: dict | None = None,
    generation_run_id: uuid.UUID | None = None,
) -> None:
    """Append to the audit trail. The schema is the index; the payload
    lives in ``details``. Service callers pass typed dicts per
    event_type; ``details`` is opaque to the schema.

    ``question_id`` is nullable so the AI orchestrator can log
    pre-persistence rounds keyed only by ``generation_run_id``."""
    db.add(
        DailyChallengeQuestionEvent(
            question_id=question_id,
            event_type=event_type,
            actor_id=actor_id,
            details=details or {},
            generation_run_id=generation_run_id,
        )
    )


def create_question(
    db: Session,
    *,
    question_type: str,
    bible_book: str,
    bible_chapter: int,
    bible_verse_from: int | None,
    bible_verse_to: int | None,
    question_text: str,
    options: list[OptionDraft],
    explanation: str | None,
    category: str | None,
    created_by: uuid.UUID,
    fallback_locale: str | None = None,
) -> DailyChallengeQuestion:
    """Create a DRAFT question + its options. Text lands in cv via
    ``record_human_version``; ``source_locale`` is detected from the
    combined question + explanation text.

    Service-level invariant enforced here: exactly one option has
    ``is_correct=True``. Violations raise ``ValueError`` BEFORE any
    INSERT lands.
    """
    correct_count = sum(1 for o in options if o.is_correct)
    if correct_count != 1:
        raise ValueError(f"daily challenge question must have exactly one correct option, got {correct_count}")
    if len(options) < 2:
        raise ValueError("daily challenge question needs at least two options")
    if question_type == "true_false" and len(options) != 2:
        raise ValueError("true_false questions need exactly two options")

    detected = detect_locale(" ".join(t for t in (question_text, explanation) if t))
    source_locale = detected or fallback_locale or "en"

    question = DailyChallengeQuestion(
        question_type=question_type,
        status=DailyChallengeQuestionStatus.DRAFT.value,
        rejected=False,
        created_by=created_by,
        bible_book=bible_book,
        bible_chapter=bible_chapter,
        bible_verse_from=bible_verse_from,
        bible_verse_to=bible_verse_to,
        category=category,
        source_locale=source_locale,
    )
    db.add(question)
    db.flush()

    record_human_version(
        db,
        entity_type="daily_challenge_question",
        entity_id=str(question.id),
        field="question_text",
        locale=source_locale,
        text=question_text,
        authored_by=created_by,
    )
    if explanation:
        record_human_version(
            db,
            entity_type="daily_challenge_question",
            entity_id=str(question.id),
            field="explanation",
            locale=source_locale,
            text=explanation,
            authored_by=created_by,
        )

    for idx, opt_draft in enumerate(options):
        opt = DailyChallengeOption(
            question_id=question.id,
            is_correct=opt_draft.is_correct,
            order_index=idx,
        )
        db.add(opt)
        db.flush()
        record_human_version(
            db,
            entity_type="daily_challenge_option",
            entity_id=str(opt.id),
            field="option_text",
            locale=source_locale,
            text=opt_draft.text,
            authored_by=created_by,
        )

    _log_event(
        db,
        question_id=question.id,
        event_type="status_change",
        actor_id=created_by,
        details={"from": None, "to": DailyChallengeQuestionStatus.DRAFT.value},
    )
    db.commit()
    db.refresh(question)
    return question


def promote_status(
    db: Session,
    *,
    question: DailyChallengeQuestion,
    actor_id: uuid.UUID,
) -> DailyChallengeQuestion:
    """Advance the question one stage forward through the editorial
    DAG. Raises ``QuestionRejectedError`` if the question is rejected
    and ``StatusTransitionError`` if there's no forward edge from the
    current status (e.g., already at ``published`` or ``archived``)."""
    if question.rejected:
        raise QuestionRejectedError(f"question {question.id} is rejected; cannot promote")
    next_status = _FORWARD_TRANSITIONS.get(question.status)
    if next_status is None:
        raise StatusTransitionError(f"no forward transition from status={question.status} on question {question.id}")

    previous = question.status
    question.status = next_status
    db.flush()

    _log_event(
        db,
        question_id=question.id,
        event_type="status_change",
        actor_id=actor_id,
        details={"from": previous, "to": next_status},
    )
    db.commit()
    db.refresh(question)
    return question


def reject_question(
    db: Session,
    *,
    question: DailyChallengeQuestion,
    actor_id: uuid.UUID,
    reason: str,
) -> DailyChallengeQuestion:
    """Set ``rejected=true`` with reason + actor. Status is unchanged
    — the question stays at whatever stage killed it (Agent C's audit
    trail philosophy)."""
    if question.rejected:
        return question  # idempotent

    question.rejected = True
    question.rejection_reason = reason
    question.rejected_by = actor_id
    question.rejected_at = datetime.now(UTC)
    db.flush()

    _log_event(
        db,
        question_id=question.id,
        event_type="rejected",
        actor_id=actor_id,
        details={"reason": reason, "at_stage": question.status},
    )
    db.commit()
    db.refresh(question)
    return question


def publish_question(
    db: Session,
    *,
    question: DailyChallengeQuestion,
    actor_id: uuid.UUID,
) -> DailyChallengeQuestion:
    """Move a ``pilot_passed`` question to ``published`` and stamp
    ``published_at`` / ``published_by``. Schedules are written separately
    — this is the gate that opens the door for the schedule trigger
    to accept the question."""
    if question.rejected:
        raise QuestionRejectedError(f"question {question.id} is rejected; cannot publish")
    if question.status != DailyChallengeQuestionStatus.PILOT_PASSED.value:
        raise StatusTransitionError(
            f"question {question.id} must be at pilot_passed to publish (current: {question.status})"
        )

    question.status = DailyChallengeQuestionStatus.PUBLISHED.value
    question.published_at = datetime.now(UTC)
    question.published_by = actor_id
    db.flush()

    _log_event(
        db,
        question_id=question.id,
        event_type="published",
        actor_id=actor_id,
        details={"published_at": question.published_at.isoformat()},
    )
    db.commit()
    db.refresh(question)
    return question


def schedule_for_date(
    db: Session,
    *,
    question: DailyChallengeQuestion,
    on_date: date,
    actor_id: uuid.UUID,
) -> DailyChallengeSchedule:
    """Attach a published, non-rejected question to a UTC date. The
    Postgres trigger ``dc_schedule_assert_publishable`` is the second
    line of defence — this service raises before the INSERT so the
    caller gets a clean Python error path.

    Idempotent on (date, question_id) — re-scheduling the same pair
    no-ops. Re-scheduling a different question for the date raises
    because the PK on challenge_date enforces single-question-per-day
    (we deliberately don't auto-replace; the editor calls
    ``unschedule_date`` first)."""
    if question.rejected:
        raise QuestionRejectedError(f"question {question.id} is rejected; cannot schedule")
    if question.status != DailyChallengeQuestionStatus.PUBLISHED.value or question.published_at is None:
        raise NotPublishableError(f"question {question.id} is not at status=published / published_at is NULL")

    existing = db.query(DailyChallengeSchedule).filter(DailyChallengeSchedule.challenge_date == on_date).one_or_none()
    if existing is not None:
        if existing.question_id == question.id:
            return existing  # idempotent
        raise NotPublishableError(f"date {on_date.isoformat()} already scheduled to question {existing.question_id}")

    schedule = DailyChallengeSchedule(
        challenge_date=on_date,
        question_id=question.id,
        scheduled_by=actor_id,
    )
    db.add(schedule)
    db.flush()

    _log_event(
        db,
        question_id=question.id,
        event_type="scheduled",
        actor_id=actor_id,
        details={"challenge_date": on_date.isoformat()},
    )
    db.commit()
    db.refresh(schedule)
    return schedule
