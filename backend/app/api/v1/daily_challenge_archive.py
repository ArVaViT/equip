"""Archive surface for the Daily Challenge.

Three student-facing endpoints, all gated by ``get_current_user``:

* ``GET /daily-challenge/archive`` — paginated list of past UTC dates
  with a scheduled question + the user's per-date attempt status.
  Powers the calendar-grid view.
* ``GET /daily-challenge/archive/{challenge_date}`` — one past day's
  question + reveal payload if the user has attempted it before.
* ``POST /daily-challenge/archive/{challenge_date}/attempt`` — submit
  a replay attempt. Writes ``is_archive=True`` so the streak service
  isn't called. Multiple replays per date are allowed.

Date semantics: the routes refuse today and any future date — the
live ``/today`` surface owns those. The 422 carries
``daily_challenge.archive_date_not_allowed`` so the client redirects.
"""

from __future__ import annotations

from datetime import date  # noqa: TC003 — FastAPI runtime resolution
from typing import cast

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session  # noqa: TC002 — FastAPI Depends runtime use

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.user import User  # noqa: TC001 — FastAPI Depends runtime use
from app.schemas.daily_challenge import (
    DailyChallengeArchiveAttemptResponse,
    DailyChallengeArchiveEntry,
    DailyChallengeArchiveListResponse,
    DailyChallengeArchiveQuestionResponse,
    DailyChallengeArchiveRevealView,
    DailyChallengeAttemptCreate,
    DailyChallengeOptionStudentView,
    DailyChallengeQuestionType,
)
from app.schemas.locale import normalize_locale
from app.services.bible.books import display_book_name, find_book
from app.services.daily_challenge import (
    ArchiveDateNotAllowedError,
    ArchiveNotScheduledError,
    InvalidOptionError,
    fetch_question_text_bundle,
    get_archive_question,
    list_archive_entries,
    submit_archive_attempt,
)
from app.services.daily_challenge.attempt import _correct_option_for

router = APIRouter(prefix="/daily-challenge/archive", tags=["daily-challenge"])


def _book_label(book: str, locale: str) -> str:
    slug = find_book(book)
    return (display_book_name(slug, locale) if slug is not None else None) or book


@router.get(
    "",
    response_model=DailyChallengeArchiveListResponse,
    summary="Paginated past dates with attempt status",
)
def list_archive(
    response: Response,
    before: date | None = Query(default=None),
    limit: int = Query(default=90, ge=1, le=180),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailyChallengeArchiveListResponse:
    response.headers["Vary"] = "Accept-Language"
    locale = normalize_locale(accept_language)
    entries, cursor = list_archive_entries(
        db,
        user_id=current_user.id,
        before=before,
        limit=limit,
    )
    return DailyChallengeArchiveListResponse(
        entries=[
            DailyChallengeArchiveEntry(
                challenge_date=e.challenge_date,
                question_id=e.question_id,
                bible_book=e.bible_book,
                bible_book_label=_book_label(e.bible_book, locale),
                bible_chapter=e.bible_chapter,
                bible_verse_from=e.bible_verse_from,
                bible_verse_to=e.bible_verse_to,
                attempted_is_correct=e.attempted_is_correct,
                archive_only_attempt=e.archive_only_attempt,
            )
            for e in entries
        ],
        next_cursor=cursor,
    )


@router.get(
    "/{challenge_date}",
    response_model=DailyChallengeArchiveQuestionResponse,
    summary="One past day's question (with reveal if previously attempted)",
    responses={
        200: {"description": "Question + (when previously attempted) reveal."},
        404: {"description": "No question was scheduled for that date."},
        422: {"description": "Date is today or in the future."},
    },
)
def get_archive(
    challenge_date: date,
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailyChallengeArchiveQuestionResponse:
    response.headers["Vary"] = "Accept-Language"
    try:
        schedule, question, attempt = get_archive_question(db, user_id=current_user.id, on_date=challenge_date)
    except ArchiveDateNotAllowedError:
        raise equip_error(
            ErrorCode.DAILY_CHALLENGE_ARCHIVE_DATE_NOT_ALLOWED,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            message="Archive endpoints only accept dates strictly before today",
            context={"challenge_date": challenge_date.isoformat()},
        ) from None
    except ArchiveNotScheduledError:
        raise equip_error(
            ErrorCode.DAILY_CHALLENGE_NOT_SCHEDULED,
            status_code=status.HTTP_404_NOT_FOUND,
            message="No Daily Challenge is scheduled for that date",
            context={"challenge_date": challenge_date.isoformat()},
        ) from None

    locale = normalize_locale(accept_language)
    bundle = fetch_question_text_bundle(db, question=question, display_locale=locale)
    if not bundle.is_servable:
        # Same rule as the live card: no substitute language, and an
        # empty question is not an answer. An archive day that has not
        # been translated reads as missing rather than as broken.
        raise equip_error(
            ErrorCode.DAILY_CHALLENGE_NOT_TRANSLATED,
            status_code=status.HTTP_404_NOT_FOUND,
            message="That Daily Challenge is not available in this language yet",
            context={"challenge_date": challenge_date.isoformat(), "locale": locale},
        )
    options_view = [
        DailyChallengeOptionStudentView(
            id=o.id,
            option_text=bundle.options.get(o.id, ""),
            order_index=o.order_index,
        )
        for o in sorted(question.options, key=lambda o: o.order_index)
    ]

    reveal: DailyChallengeArchiveRevealView | None = None
    if attempt is not None:
        correct = _correct_option_for(question)
        reveal = DailyChallengeArchiveRevealView(
            correct_option_id=correct.id,
            explanation=bundle.explanation,
            last_attempt_was_correct=bool(attempt.is_correct),
        )

    return DailyChallengeArchiveQuestionResponse(
        challenge_date=schedule.challenge_date,
        question_id=question.id,
        question_type=cast("DailyChallengeQuestionType", question.question_type),
        question_text=bundle.question_text,
        options=options_view,
        bible_book=question.bible_book,
        bible_book_label=_book_label(question.bible_book, locale),
        bible_chapter=question.bible_chapter,
        bible_verse_from=question.bible_verse_from,
        bible_verse_to=question.bible_verse_to,
        reveal=reveal,
    )


@router.post(
    "/{challenge_date}/attempt",
    response_model=DailyChallengeArchiveAttemptResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a replay attempt for a past day",
)
def submit_archive(
    challenge_date: date,
    data: DailyChallengeAttemptCreate,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailyChallengeArchiveAttemptResponse:
    try:
        outcome = submit_archive_attempt(
            db,
            user_id=current_user.id,
            on_date=challenge_date,
            selected_option_id=data.selected_option_id,
        )
    except ArchiveDateNotAllowedError:
        raise equip_error(
            ErrorCode.DAILY_CHALLENGE_ARCHIVE_DATE_NOT_ALLOWED,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            message="Archive endpoints only accept dates strictly before today",
            context={"challenge_date": challenge_date.isoformat()},
        ) from None
    except ArchiveNotScheduledError:
        raise equip_error(
            ErrorCode.DAILY_CHALLENGE_NOT_SCHEDULED,
            status_code=status.HTTP_404_NOT_FOUND,
            message="No Daily Challenge is scheduled for that date",
            context={"challenge_date": challenge_date.isoformat()},
        ) from None
    except InvalidOptionError as exc:
        raise equip_error(
            ErrorCode.DAILY_CHALLENGE_INVALID_OPTION,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            message="The selected option does not belong to that question",
            context={
                "selected_option_id": str(exc.selected_option_id),
                "question_id": str(exc.question_id),
            },
        ) from None

    locale = normalize_locale(accept_language)
    bundle = fetch_question_text_bundle(db, question=outcome.question, display_locale=locale)
    return DailyChallengeArchiveAttemptResponse(
        id=outcome.attempt.id,
        challenge_date=outcome.attempt.challenge_date,
        selected_option_id=outcome.attempt.selected_option_id or data.selected_option_id,
        correct_option_id=outcome.correct_option_id,
        is_correct=outcome.attempt.is_correct,
        explanation=bundle.explanation,
        submitted_at=outcome.attempt.submitted_at,
    )
