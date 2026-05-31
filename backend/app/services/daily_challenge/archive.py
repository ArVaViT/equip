"""Archive surface for the Daily Challenge.

Three service entry points back the three archive routes:

* ``list_archive_entries`` — paginated list of past UTC dates with a
  scheduled question, annotated with whether the user has attempted
  and (if so) whether they got it right. Drives the calendar grid.
* ``get_archive_question`` — fetches a single past day's question +
  reveal payload if the user has attempted it before.
* ``submit_archive_attempt`` — writes an ``is_archive=True`` attempt.
  Bypasses the streak service (archive attempts don't impact streak)
  and satisfies the ``dc_attempts_archive_null_streak`` CHECK by
  leaving ``streak_after`` NULL.

Date semantics: archive is strictly the past. Today and any future
date raises ``ArchiveDateNotAllowedError``; the route maps that to a
422 with ``daily_challenge.archive_date_not_allowed`` so the client
redirects to the live ``/today`` card.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.daily_challenge import (
    DailyChallengeAttempt,
    DailyChallengeOption,
    DailyChallengeQuestion,
    DailyChallengeSchedule,
)
from app.services.daily_challenge.attempt import (
    InvalidOptionError,
    _correct_option_for,
)
from app.services.daily_challenge.schedule import utc_today

if TYPE_CHECKING:
    import uuid
    from datetime import date

    from sqlalchemy.orm import Session


class ArchiveDateNotAllowedError(Exception):
    """Caller tried to reach an archive surface with today's date or a
    future date. Those are owned by the live ``/today`` route."""


class ArchiveNotScheduledError(Exception):
    """No question was scheduled for the requested past date — the
    editorial pipeline had a gap. Mapped to 404 by the route."""


@dataclass(frozen=True, slots=True)
class ArchiveEntry:
    """One row in the calendar grid."""

    challenge_date: date
    question_id: uuid.UUID
    bible_book: str
    bible_chapter: int
    bible_verse_from: int | None
    bible_verse_to: int | None
    # None = never attempted; True/False = last attempt's correctness.
    attempted_is_correct: bool | None
    # True when the user's only attempt on this date is an archive
    # replay (no live attempt). Drives the "Replay" badge in the UI.
    archive_only_attempt: bool


@dataclass(frozen=True, slots=True)
class ArchiveAttemptOutcome:
    """Service-level result of ``submit_archive_attempt``."""

    attempt: DailyChallengeAttempt
    question: DailyChallengeQuestion
    correct_option_id: uuid.UUID


def _ensure_past(on_date: date) -> None:
    """Reject today or any future date. Live ``/today`` is the only
    surface allowed to serve those."""
    if on_date >= utc_today():
        raise ArchiveDateNotAllowedError(
            f"archive endpoints only accept dates strictly before today; got {on_date.isoformat()}"
        )


def list_archive_entries(
    db: Session,
    *,
    user_id: uuid.UUID,
    before: date | None = None,
    limit: int = 90,
) -> tuple[list[ArchiveEntry], date | None]:
    """Return up to ``limit`` past scheduled dates ordered most-recent
    first, optionally paginating via ``before`` (exclusive cursor).

    ``before=None`` starts at ``utc_today() - 1``. The returned cursor
    is the date of the oldest entry minus one day, or ``None`` when
    the list ran out of rows (no more pages)."""
    today = utc_today()
    upper_exclusive = before if before is not None else today
    # Cap defensively — a misbehaving client could ask for a huge limit.
    safe_limit = max(1, min(limit, 180))

    stmt = (
        select(
            DailyChallengeSchedule.challenge_date,
            DailyChallengeQuestion.id,
            DailyChallengeQuestion.bible_book,
            DailyChallengeQuestion.bible_chapter,
            DailyChallengeQuestion.bible_verse_from,
            DailyChallengeQuestion.bible_verse_to,
        )
        .join(
            DailyChallengeQuestion,
            DailyChallengeQuestion.id == DailyChallengeSchedule.question_id,
        )
        .where(DailyChallengeSchedule.challenge_date < upper_exclusive)
        .order_by(DailyChallengeSchedule.challenge_date.desc())
        .limit(safe_limit)
    )
    schedule_rows = db.execute(stmt).all()

    if not schedule_rows:
        return [], None

    dates = [row[0] for row in schedule_rows]
    attempt_rows = (
        db.query(
            DailyChallengeAttempt.challenge_date,
            DailyChallengeAttempt.is_correct,
            DailyChallengeAttempt.is_archive,
        )
        .filter(
            DailyChallengeAttempt.user_id == user_id,
            DailyChallengeAttempt.challenge_date.in_(dates),
        )
        .order_by(
            DailyChallengeAttempt.challenge_date,
            DailyChallengeAttempt.is_archive.asc(),
            DailyChallengeAttempt.submitted_at.desc(),
        )
        .all()
    )
    # Per-date picker: prefer the live attempt over an archive
    # replay; among archive-only attempts, prefer the most recent.
    by_date: dict[date, tuple[bool, bool]] = {}
    for d, is_correct, is_archive in attempt_rows:
        existing = by_date.get(d)
        if existing is not None and not existing[1]:
            # A non-archive (live) attempt already wins.
            continue
        by_date[d] = (bool(is_correct), bool(is_archive))

    entries: list[ArchiveEntry] = []
    for d, qid, book, chap, vf, vt in schedule_rows:
        attempt = by_date.get(d)
        entries.append(
            ArchiveEntry(
                challenge_date=d,
                question_id=qid,
                bible_book=book,
                bible_chapter=chap,
                bible_verse_from=vf,
                bible_verse_to=vt,
                attempted_is_correct=attempt[0] if attempt else None,
                archive_only_attempt=bool(attempt[1]) if attempt else False,
            )
        )

    # next_cursor: oldest returned date — call with ``before=<this>``
    # to get the prior page. ``None`` when we returned fewer rows than
    # the cap (no more history).
    next_cursor = entries[-1].challenge_date if len(entries) == safe_limit else None
    return entries, next_cursor


def get_archive_question(
    db: Session,
    *,
    user_id: uuid.UUID,
    on_date: date,
) -> tuple[DailyChallengeSchedule, DailyChallengeQuestion, DailyChallengeAttempt | None]:
    """Fetch the past scheduled question for ``on_date`` and the
    user's most-recent attempt (live preferred, otherwise archive).

    Raises:
    * ``ArchiveDateNotAllowedError`` for today / future dates.
    * ``ArchiveNotScheduledError`` for past dates with no schedule.
    """
    _ensure_past(on_date)

    row = (
        db.query(DailyChallengeSchedule, DailyChallengeQuestion)
        .join(
            DailyChallengeQuestion,
            DailyChallengeQuestion.id == DailyChallengeSchedule.question_id,
        )
        .filter(DailyChallengeSchedule.challenge_date == on_date)
        .one_or_none()
    )
    if row is None:
        raise ArchiveNotScheduledError(f"no question scheduled for {on_date.isoformat()}")

    schedule, question = row

    attempt = (
        db.query(DailyChallengeAttempt)
        .filter(
            DailyChallengeAttempt.user_id == user_id,
            DailyChallengeAttempt.challenge_date == on_date,
        )
        .order_by(
            # Live before archive; among archive, the most recent submission.
            DailyChallengeAttempt.is_archive.asc(),
            DailyChallengeAttempt.submitted_at.desc(),
        )
        .first()
    )
    return schedule, question, attempt


def submit_archive_attempt(
    db: Session,
    *,
    user_id: uuid.UUID,
    on_date: date,
    selected_option_id: uuid.UUID,
) -> ArchiveAttemptOutcome:
    """Persist an ``is_archive=True`` attempt for a past date.

    Same option-validation rules as the live attempt; archive attempts
    do NOT touch the streak (and the CHECK constraint requires
    ``streak_after`` to be NULL for archive rows). Multiple replays
    per date are allowed — no partial-unique guard.
    """
    _ensure_past(on_date)

    row = (
        db.query(DailyChallengeSchedule, DailyChallengeQuestion)
        .join(
            DailyChallengeQuestion,
            DailyChallengeQuestion.id == DailyChallengeSchedule.question_id,
        )
        .filter(DailyChallengeSchedule.challenge_date == on_date)
        .one_or_none()
    )
    if row is None:
        raise ArchiveNotScheduledError(f"no question scheduled for {on_date.isoformat()}")
    _, question = row

    selected = (
        db.query(DailyChallengeOption)
        .filter(
            DailyChallengeOption.id == selected_option_id,
            DailyChallengeOption.question_id == question.id,
        )
        .one_or_none()
    )
    if selected is None:
        raise InvalidOptionError(selected_option_id=selected_option_id, question_id=question.id)

    correct_option = _correct_option_for(question)

    attempt = DailyChallengeAttempt(
        user_id=user_id,
        question_id=question.id,
        challenge_date=on_date,
        is_archive=True,
        selected_option_id=selected.id,
        is_correct=selected.is_correct,
        streak_after=None,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)

    return ArchiveAttemptOutcome(
        attempt=attempt,
        question=question,
        correct_option_id=correct_option.id,
    )


__all__ = [
    "ArchiveAttemptOutcome",
    "ArchiveDateNotAllowedError",
    "ArchiveEntry",
    "ArchiveNotScheduledError",
    "get_archive_question",
    "list_archive_entries",
    "submit_archive_attempt",
]
