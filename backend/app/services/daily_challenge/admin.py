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

from sqlalchemy import select

from app.models.content_version import ContentVersion, ContentVersionStatus
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


def _normalize_verse_range(verse_from: int | None, verse_to: int | None) -> tuple[int | None, int | None]:
    """Coerce a (verse_from, verse_to) pair so it satisfies the
    ``daily_challenge_questions`` CHECK constraints:

      * ``bible_verse_from IS NULL OR bible_verse_from > 0``
      * ``bible_verse_to IS NULL OR (bible_verse_from IS NOT NULL AND bible_verse_to >= bible_verse_from)``

    LLM-generated survivors (``verse_start`` / ``verse_end`` from the model) can
    carry a dangling ``verse_to`` with no ``verse_from``, a reversed range, or a
    non-positive value — all rejected by the DB, which silently dropped the
    generated question (the fat-bank run lost ~27% of whole-chapter passages this
    way, and the daily replenish cron fell back to recycling on such days).
    Normalising at the persistence chokepoint keeps every path CHECK-safe.
    """
    vf = verse_from if isinstance(verse_from, int) and not isinstance(verse_from, bool) and verse_from > 0 else None
    vt = verse_to if isinstance(verse_to, int) and not isinstance(verse_to, bool) and verse_to > 0 else None
    if vf is None:
        # No start verse → can't anchor an end; treat as whole-chapter/unspecified.
        return None, None
    if vt is None or vt < vf:
        return vf, None
    return vf, vt


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
    # Upper bound mirrors daily_challenge_options_order_check (order_index
    # BETWEEN 0 AND 5): a 7th option would die as an IntegrityError deep in
    # the generation pipeline ("persist failed", question silently dropped)
    # instead of a clear gate error here — same failure class as the verse
    # range fixed in #791.
    if len(options) > 6:
        raise ValueError(f"daily challenge question allows at most six options, got {len(options)}")
    if question_type == "true_false" and len(options) != 2:
        raise ValueError("true_false questions need exactly two options")

    # Keep the verse range CHECK-safe regardless of what the generator/admin
    # passed (dangling end, reversed range, non-positive). See _normalize_verse_range.
    bible_verse_from, bible_verse_to = _normalize_verse_range(bible_verse_from, bible_verse_to)

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
    no-ops. A date already holding a DIFFERENT *editorial* question
    (``scheduled_by`` set) raises — we don't silently clobber a
    deliberate choice. But an AUTO-FILLED placeholder (``scheduled_by
    IS NULL`` — written by the live path when the schedule ran dry) is
    transparently replaced so the editor's curated pick isn't blocked
    by the dry-day fallback."""
    if question.rejected:
        raise QuestionRejectedError(f"question {question.id} is rejected; cannot schedule")
    if question.status != DailyChallengeQuestionStatus.PUBLISHED.value or question.published_at is None:
        raise NotPublishableError(f"question {question.id} is not at status=published / published_at is NULL")

    existing = db.query(DailyChallengeSchedule).filter(DailyChallengeSchedule.challenge_date == on_date).one_or_none()
    if existing is not None:
        if existing.question_id == question.id:
            return existing  # idempotent
        if existing.scheduled_by is None:
            # Auto-filled placeholder — replace with the editor's choice.
            existing.question_id = question.id
            existing.scheduled_by = actor_id
            db.flush()
            _log_event(
                db,
                question_id=question.id,
                event_type="scheduled",
                actor_id=actor_id,
                details={"challenge_date": on_date.isoformat(), "replaced": "autofill"},
            )
            db.commit()
            db.refresh(existing)
            return existing
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


# ---------------------------------------------------------------------------
# Bilingual review queue (Sprint 7)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CvCellView:
    """One cv row reduced to what the editor UI needs."""

    cv_id: uuid.UUID | None
    text: str
    origin: str | None
    locale: str
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class BilingualOption:
    id: uuid.UUID
    order_index: int
    is_correct: bool
    en: CvCellView
    ru: CvCellView


@dataclass(frozen=True, slots=True)
class BilingualView:
    question: DailyChallengeQuestion
    question_text: dict[str, CvCellView]
    explanation: dict[str, CvCellView]
    options: list[BilingualOption]


def _empty_cell(locale: str) -> CvCellView:
    return CvCellView(cv_id=None, text="", origin=None, locale=locale, updated_at=None)


def _active_cv_rows(
    db: Session,
    *,
    entity_type: str,
    entity_ids: list[str],
    fields: list[str],
) -> dict[tuple[str, str, str], ContentVersion]:
    """Map (entity_id, field, locale) → the latest active cv row."""
    if not entity_ids:
        return {}
    rows = (
        db.execute(
            select(ContentVersion).where(
                ContentVersion.entity_type == entity_type,
                ContentVersion.entity_id.in_(entity_ids),
                ContentVersion.field.in_(fields),
                ContentVersion.locale.in_(("en", "ru")),
                ContentVersion.superseded_by.is_(None),
                ContentVersion.status == ContentVersionStatus.OK,
            )
        )
        .scalars()
        .all()
    )
    by_key: dict[tuple[str, str, str], ContentVersion] = {}
    for row in rows:
        key = (row.entity_id, row.field, row.locale)
        existing = by_key.get(key)
        if existing is None or (row.updated_at or row.created_at) > (existing.updated_at or existing.created_at):
            by_key[key] = row
    return by_key


def fetch_bilingual_view(db: Session, *, question: DailyChallengeQuestion) -> BilingualView:
    """Return parallel EN + RU cv cells for a question's translatable
    fields. Cells are ``empty`` (cv_id=None, text="") when the locale
    has no row yet — the UI renders these as "MISSING" placeholders."""
    q_id = str(question.id)
    option_ids = [str(o.id) for o in question.options]

    q_rows = _active_cv_rows(
        db,
        entity_type="daily_challenge_question",
        entity_ids=[q_id],
        fields=["question_text", "explanation"],
    )
    o_rows = _active_cv_rows(
        db,
        entity_type="daily_challenge_option",
        entity_ids=option_ids,
        fields=["option_text"],
    )

    def cell(rows: dict[tuple[str, str, str], ContentVersion], *, eid: str, field: str, locale: str) -> CvCellView:
        row = rows.get((eid, field, locale))
        if row is None:
            return _empty_cell(locale)
        return CvCellView(
            cv_id=row.id,
            text=row.text,
            origin=row.origin,
            locale=locale,
            updated_at=row.updated_at,
        )

    return BilingualView(
        question=question,
        question_text={
            "en": cell(q_rows, eid=q_id, field="question_text", locale="en"),
            "ru": cell(q_rows, eid=q_id, field="question_text", locale="ru"),
        },
        explanation={
            "en": cell(q_rows, eid=q_id, field="explanation", locale="en"),
            "ru": cell(q_rows, eid=q_id, field="explanation", locale="ru"),
        },
        options=[
            BilingualOption(
                id=o.id,
                order_index=o.order_index,
                is_correct=o.is_correct,
                en=cell(o_rows, eid=str(o.id), field="option_text", locale="en"),
                ru=cell(o_rows, eid=str(o.id), field="option_text", locale="ru"),
            )
            for o in sorted(question.options, key=lambda o: o.order_index)
        ],
    )


def upsert_cv_for_question(
    db: Session,
    *,
    question: DailyChallengeQuestion,
    field: str,
    locale: str,
    text: str,
    option_id: uuid.UUID | None,
    actor_id: uuid.UUID,
) -> ContentVersion:
    """Write/supersede a cv row from the bilingual review UI.

    Refuses when the question is rejected (the editor must un-reject
    or clone first). ``field == 'option_text'`` requires ``option_id``
    pointing at a child option of ``question``.
    """
    if question.rejected:
        raise QuestionRejectedError(f"question {question.id} is rejected; cannot edit")

    # Pydantic's ``min_length=1`` counts characters, not non-whitespace
    # ones, so ``"   "`` slips past the schema. Strip-check here so a
    # whitespace-only "translation" can't quietly land in cv.
    if not text.strip():
        raise ValueError("text must not be empty or whitespace-only")

    if field == "option_text":
        if option_id is None:
            raise ValueError("option_id is required for field='option_text'")
        option = next((o for o in question.options if o.id == option_id), None)
        if option is None:
            raise ValueError(f"option {option_id} does not belong to question {question.id}")
        entity_type = "daily_challenge_option"
        entity_id = str(option.id)
    else:
        entity_type = "daily_challenge_question"
        entity_id = str(question.id)

    cv = record_human_version(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        locale=locale,
        text=text,
        authored_by=actor_id,
    )
    _log_event(
        db,
        question_id=question.id,
        event_type="bilingual_edit",
        actor_id=actor_id,
        details={
            "field": field,
            "locale": locale,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "cv_id": str(cv.id),
        },
    )
    db.commit()
    db.refresh(cv)
    return cv


@dataclass(frozen=True, slots=True)
class QueueItem:
    """One row in the bilingual review queue list. ``has_en``/``has_ru``
    are precomputed booleans over the question_text + explanation cv
    rows so a "needs RU" filter on the UI doesn't have to fan out into
    N+1 cv queries."""

    question: DailyChallengeQuestion
    has_en: bool
    has_ru: bool


def list_review_queue(
    db: Session,
    *,
    status_filter: str | None = None,
    only_missing_ru: bool = False,
    rejected: bool = False,
    limit: int = 25,
    offset: int = 0,
) -> tuple[list[QueueItem], int]:
    """Paginated list of editorial questions, with EN/RU presence
    annotation per row. ``only_missing_ru`` filters in Python rather
    than via SQL so the helper stays simple — the queue size is
    capped at ~hundreds, the join cost is trivial."""
    q = db.query(DailyChallengeQuestion).filter(
        DailyChallengeQuestion.rejected.is_(rejected),
    )
    if status_filter:
        q = q.filter(DailyChallengeQuestion.status == status_filter)
    total = q.count()
    rows = q.order_by(DailyChallengeQuestion.updated_at.desc()).offset(offset).limit(limit).all()
    if not rows:
        return [], total

    q_ids = [str(r.id) for r in rows]
    cv_rows = _active_cv_rows(
        db,
        entity_type="daily_challenge_question",
        entity_ids=q_ids,
        fields=["question_text", "explanation"],
    )
    items: list[QueueItem] = []
    for r in rows:
        has_en = (str(r.id), "question_text", "en") in cv_rows
        has_ru = (str(r.id), "question_text", "ru") in cv_rows
        if only_missing_ru and has_ru:
            continue
        items.append(QueueItem(question=r, has_en=has_en, has_ru=has_ru))
    return items, total
