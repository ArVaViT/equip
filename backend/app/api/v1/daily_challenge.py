"""Daily Challenge API routes.

Sprint 2 ships three student-facing endpoints. Authoring + scheduling
admin routes land in Sprint 3 with the editorial pipeline.

Authentication: all routes require an authenticated user. There's no
role gate — every authenticated user, including students, can read
today's question, submit an attempt, and check their streak.
"""

from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy.orm import Session  # noqa: TC002 — FastAPI Depends runtime use

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.daily_challenge import DailyChallengeAttempt
from app.models.user import User  # noqa: TC001 — FastAPI Depends runtime use
from app.schemas.daily_challenge import (
    DailyChallengeAttemptCreate,
    DailyChallengeAttemptResponse,
    DailyChallengeAttemptSummary,
    DailyChallengeOptionStudentView,
    DailyChallengeQuestionType,
    DailyChallengeStreakResponse,
    DailyChallengeTodayResponse,
)
from app.schemas.locale import normalize_locale
from app.services.bible.books import display_book_name, find_book
from app.services.daily_challenge import (
    InvalidOptionError,
    NoScheduleError,
    fetch_question_text_bundle,
    get_today_question,
    get_user_streak,
    submit_today_attempt,
)
from app.services.daily_challenge.schedule import utc_today

router = APIRouter(prefix="/daily-challenge", tags=["daily-challenge"])


@router.get(
    "/today",
    response_model=DailyChallengeTodayResponse,
    summary="Today's question + the user's existing attempt (if any)",
    responses={
        200: {"description": "Today's question. ``user_attempt`` populated when the user already submitted."},
        404: {"description": "No question scheduled for today. Frontend should hide the daily card."},
    },
)
def get_today(
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailyChallengeTodayResponse:
    """Return today's question + the user's existing attempt (if any).

    Answer key (``is_correct`` on options, the correct option id, the
    explanation) is NOT included. Those reveal on the submit response.
    """
    response.headers["Vary"] = "Accept-Language"
    today = utc_today()

    schedule_q = get_today_question(db, on_date=today)
    if schedule_q is None:
        raise equip_error(
            ErrorCode.DAILY_CHALLENGE_NOT_SCHEDULED,
            status_code=status.HTTP_404_NOT_FOUND,
            message="No Daily Challenge is scheduled for today",
            context={"challenge_date": today.isoformat()},
        )
    schedule, question = schedule_q

    display_locale = normalize_locale(accept_language)
    bundle = fetch_question_text_bundle(
        db,
        question=question,
        display_locale=display_locale,
    )

    options_view = [
        DailyChallengeOptionStudentView(
            id=o.id,
            option_text=bundle.options.get(o.id, ""),
            order_index=o.order_index,
        )
        for o in sorted(question.options, key=lambda o: o.order_index)
    ]

    existing = (
        db.query(DailyChallengeAttempt)
        .filter(
            DailyChallengeAttempt.user_id == current_user.id,
            DailyChallengeAttempt.challenge_date == today,
            DailyChallengeAttempt.is_archive.is_(False),
        )
        .one_or_none()
    )
    user_attempt_view: DailyChallengeAttemptSummary | None = None
    if existing is not None:
        user_attempt_view = DailyChallengeAttemptSummary(
            id=existing.id,
            selected_option_id=existing.selected_option_id,
            is_correct=existing.is_correct,
            streak_after=existing.streak_after,
            submitted_at=existing.submitted_at,
        )

    # Localize the book name server-side so the client doesn't need
    # to ship a 66-entry vocabulary. Fall back to the canonical English
    # book name when the locale isn't bundled or the slug is unknown
    # (defensive — the editorial pipeline only accepts canonical
    # references, but a future ingest path might not).
    slug = find_book(question.bible_book)
    bible_book_label = (display_book_name(slug, display_locale) if slug is not None else None) or question.bible_book

    return DailyChallengeTodayResponse(
        challenge_date=schedule.challenge_date,
        question_id=question.id,
        # ORM column is plain ``str`` (enum lives only in Python land);
        # cast to satisfy the Pydantic Literal. CHECK constraint on the
        # DB guarantees the runtime value is in the literal set.
        question_type=cast("DailyChallengeQuestionType", question.question_type),
        question_text=bundle.question_text,
        options=options_view,
        bible_book=question.bible_book,
        bible_book_label=bible_book_label,
        bible_chapter=question.bible_chapter,
        bible_verse_from=question.bible_verse_from,
        bible_verse_to=question.bible_verse_to,
        already_attempted=existing is not None,
        user_attempt=user_attempt_view,
    )


@router.post(
    "/today/attempt",
    response_model=DailyChallengeAttemptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit today's attempt",
    responses={
        201: {
            "description": "Attempt persisted. Returns the reveal payload (correct option + explanation + new streak)."
        },
        404: {"description": "No question scheduled for today."},
        422: {"description": "``selected_option_id`` does not belong to today's question."},
    },
)
def submit_attempt(
    data: DailyChallengeAttemptCreate,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailyChallengeAttemptResponse:
    """Submit the user's answer for today's question.

    Idempotent — a repeat submit with the same option returns the
    existing attempt verbatim. The streak service is called once per
    real attempt.

    Race-safe — the partial unique constraint catches the two-tab
    race; the service layer re-reads and returns the winning attempt.
    """
    try:
        outcome = submit_today_attempt(
            db,
            user_id=current_user.id,
            selected_option_id=data.selected_option_id,
        )
    except NoScheduleError:
        today = utc_today()
        raise equip_error(
            ErrorCode.DAILY_CHALLENGE_NOT_SCHEDULED,
            status_code=status.HTTP_404_NOT_FOUND,
            message="No Daily Challenge is scheduled for today",
            context={"challenge_date": today.isoformat()},
        ) from None
    except InvalidOptionError as exc:
        raise equip_error(
            ErrorCode.DAILY_CHALLENGE_INVALID_OPTION,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            message="The selected option does not belong to today's question",
            context={
                "selected_option_id": str(exc.selected_option_id),
                "question_id": str(exc.question_id),
            },
        ) from None

    # Fetch the explanation in the caller's display locale so the
    # post-submit reveal renders the right text without a second
    # round-trip.
    display_locale = normalize_locale(accept_language)
    bundle = fetch_question_text_bundle(
        db,
        question=outcome.question,
        display_locale=display_locale,
    )

    # ``selected_option_id`` is nullable on the ORM (ON DELETE SET NULL
    # for archival safety), but a freshly-created attempt always has it
    # set — we wrote it in this same transaction. Fall back to the
    # caller's submitted id rather than risking a Pydantic None.
    selected_id = outcome.attempt.selected_option_id or data.selected_option_id

    return DailyChallengeAttemptResponse(
        id=outcome.attempt.id,
        challenge_date=outcome.attempt.challenge_date,
        selected_option_id=selected_id,
        correct_option_id=outcome.correct_option_id,
        is_correct=outcome.attempt.is_correct,
        explanation=bundle.explanation,
        streak_after=outcome.streak_after,
        submitted_at=outcome.attempt.submitted_at,
    )


@router.get(
    "/streak",
    response_model=DailyChallengeStreakResponse,
    summary="Current user's streak",
    responses={
        200: {"description": "Zero counters returned for users who have never engaged."},
    },
)
def get_streak(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailyChallengeStreakResponse:
    """Return the caller's streak counters. Users with no engagement
    history get zeros — the route does NOT 404 for the empty case so
    the client doesn't have to special-case it."""
    streak = get_user_streak(db, user_id=current_user.id)
    if streak is None:
        return DailyChallengeStreakResponse(
            current_streak=0,
            longest_streak=0,
            last_engaged_date=None,
        )
    return DailyChallengeStreakResponse(
        current_streak=streak.current_streak,
        longest_streak=streak.longest_streak,
        last_engaged_date=streak.last_engaged_date,
    )
