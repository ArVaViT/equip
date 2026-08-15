"""Admin / editorial routes for the Daily Challenge.

Sprint 3 — manual editorial flow. Six endpoints cover the lifecycle:

* ``POST /admin/daily-challenge/questions`` — create DRAFT
* ``GET /admin/daily-challenge/questions/{id}`` — full editorial view
* ``POST /admin/daily-challenge/questions/{id}/promote`` — advance status
* ``POST /admin/daily-challenge/questions/{id}/reject`` — kill (rejected=true)
* ``POST /admin/daily-challenge/questions/{id}/publish`` — pilot_passed → published
* ``POST /admin/daily-challenge/schedule`` — attach a published question to a UTC date

The AI generation orchestrator + bulk editorial UI lands later. These
endpoints are sufficient for a human editor to manually seed the
initial 60-90 question bank Vadym wants before public launch.

Role gate: every route requires ``require_teacher`` — i.e. teacher OR
admin. The editorial team is staffed from teacher-role users; the
admin role inherits.
"""

from __future__ import annotations

from typing import Literal, cast
from uuid import UUID  # noqa: TC003 — FastAPI runtime resolution

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import require_teacher
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.daily_challenge import DailyChallengeQuestion
from app.models.user import User  # noqa: TC001 — FastAPI Depends
from app.schemas.daily_challenge import (
    DailyChallengeBilingualOption,
    DailyChallengeBilingualView,
    DailyChallengeCvCell,
    DailyChallengeCvUpsertRequest,
    DailyChallengeGenerateRequest,
    DailyChallengeGenerateResponse,
    DailyChallengeOptionEditorial,
    DailyChallengeQuestionCreate,
    DailyChallengeQuestionEditorial,
    DailyChallengeQuestionQueueItem,
    DailyChallengeQuestionQueueResponse,
    DailyChallengeQuestionType,
    DailyChallengeRejectRequest,
    DailyChallengeScheduleCreate,
    DailyChallengeScheduleResponse,
    DailyChallengeStatus,
)
from app.schemas.locale import LocaleCode, normalize_locale
from app.services.daily_challenge import (
    CvCellView,
    GeminiPromptClient,
    GenerationRequest,
    NotPublishableError,
    OptionDraft,
    QuestionRejectedError,
    StatusTransitionError,
    create_question,
    fetch_bilingual_view,
    fetch_question_text_bundle,
    list_review_queue,
    promote_status,
    publish_question,
    reject_question,
    run_generation,
    schedule_for_date,
    upsert_cv_for_question,
)
from app.services.daily_challenge.admin import QuestionRejectedError as _QRRejectedError

router = APIRouter(prefix="/admin/daily-challenge", tags=["admin-daily-challenge"])


def _question_or_404(db: Session, question_id: UUID) -> DailyChallengeQuestion:
    q = (
        db.query(DailyChallengeQuestion)
        .options(selectinload(DailyChallengeQuestion.options))
        .filter(DailyChallengeQuestion.id == question_id)
        .one_or_none()
    )
    if q is None:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Daily Challenge question not found",
            context={"resource_type": "daily_challenge_question", "resource_id": str(question_id)},
        )
    return q


def _serialize_editorial(db: Session, q: DailyChallengeQuestion) -> DailyChallengeQuestionEditorial:
    """Build the full editorial view — INCLUDES the answer key. Caller
    is responsible for gating this behind a teacher/admin role check."""
    source_locale = normalize_locale(q.source_locale)
    bundle = fetch_question_text_bundle(
        db,
        question=q,
        display_locale=source_locale,
        prefer_human=True,
    )
    return DailyChallengeQuestionEditorial(
        id=q.id,
        # ORM columns are plain ``str``; cast to satisfy Pydantic
        # Literals. CHECK constraints on the DB guarantee the runtime
        # values are in the literal sets.
        question_type=cast("DailyChallengeQuestionType", q.question_type),
        status=cast("DailyChallengeStatus", q.status),
        rejected=q.rejected,
        rejection_reason=q.rejection_reason,
        published_at=q.published_at,
        bible_book=q.bible_book,
        bible_chapter=q.bible_chapter,
        bible_verse_from=q.bible_verse_from,
        bible_verse_to=q.bible_verse_to,
        category=q.category,
        source_locale=q.source_locale,
        question_text=bundle.question_text,
        explanation=bundle.explanation,
        options=[
            DailyChallengeOptionEditorial(
                id=o.id,
                option_text=bundle.options.get(o.id, ""),
                is_correct=o.is_correct,
                order_index=o.order_index,
            )
            for o in sorted(q.options, key=lambda o: o.order_index)
        ],
        created_at=q.created_at,
        updated_at=q.updated_at,
    )


@router.post(
    "/questions",
    response_model=DailyChallengeQuestionEditorial,
    status_code=status.HTTP_201_CREATED,
    summary="Create a DRAFT question with options",
)
def create_question_route(
    data: DailyChallengeQuestionCreate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> DailyChallengeQuestionEditorial:
    try:
        q = create_question(
            db,
            question_type=data.question_type,
            bible_book=data.bible_book,
            bible_chapter=data.bible_chapter,
            bible_verse_from=data.bible_verse_from,
            bible_verse_to=data.bible_verse_to,
            question_text=data.question_text,
            options=[OptionDraft(text=o.text, is_correct=o.is_correct) for o in data.options],
            explanation=data.explanation,
            category=data.category,
            created_by=teacher.id,
            fallback_locale=teacher.preferred_locale,
        )
    except ValueError as exc:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message=str(exc),
            context={"resource_type": "daily_challenge_question"},
        ) from None
    # Re-query with options loaded for the editorial response.
    q = _question_or_404(db, q.id)
    return _serialize_editorial(db, q)


@router.get(
    "/questions/{question_id}",
    response_model=DailyChallengeQuestionEditorial,
    summary="Full editorial view — includes the answer key",
)
def get_question_editorial(
    question_id: UUID,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> DailyChallengeQuestionEditorial:
    q = _question_or_404(db, question_id)
    return _serialize_editorial(db, q)


@router.post(
    "/questions/{question_id}/promote",
    response_model=DailyChallengeQuestionEditorial,
    summary="Advance question one stage forward through the editorial DAG",
)
def promote_question_route(
    question_id: UUID,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> DailyChallengeQuestionEditorial:
    q = _question_or_404(db, question_id)
    try:
        q = promote_status(db, question=q, actor_id=teacher.id)
    except QuestionRejectedError as exc:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_409_CONFLICT,
            message=str(exc),
            context={"resource_type": "daily_challenge_question", "resource_id": str(question_id)},
        ) from None
    except StatusTransitionError as exc:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_409_CONFLICT,
            message=str(exc),
            context={
                "resource_type": "daily_challenge_question",
                "resource_id": str(question_id),
                "current_status": q.status,
            },
        ) from None
    q = _question_or_404(db, question_id)
    return _serialize_editorial(db, q)


@router.post(
    "/questions/{question_id}/reject",
    response_model=DailyChallengeQuestionEditorial,
    summary="Reject — sets rejected=true, leaves status at the killing stage",
)
def reject_question_route(
    question_id: UUID,
    body: DailyChallengeRejectRequest,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> DailyChallengeQuestionEditorial:
    q = _question_or_404(db, question_id)
    q = reject_question(db, question=q, actor_id=teacher.id, reason=body.reason)
    q = _question_or_404(db, question_id)
    return _serialize_editorial(db, q)


@router.post(
    "/questions/{question_id}/publish",
    response_model=DailyChallengeQuestionEditorial,
    summary="Move pilot_passed → published, stamp published_at",
)
def publish_question_route(
    question_id: UUID,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> DailyChallengeQuestionEditorial:
    q = _question_or_404(db, question_id)
    try:
        q = publish_question(db, question=q, actor_id=teacher.id)
    except QuestionRejectedError as exc:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_409_CONFLICT,
            message=str(exc),
            context={"resource_type": "daily_challenge_question", "resource_id": str(question_id)},
        ) from None
    except StatusTransitionError as exc:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_409_CONFLICT,
            message=str(exc),
            context={
                "resource_type": "daily_challenge_question",
                "resource_id": str(question_id),
                "current_status": q.status,
            },
        ) from None
    q = _question_or_404(db, question_id)
    return _serialize_editorial(db, q)


@router.post(
    "/schedule",
    response_model=DailyChallengeScheduleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule a published question for a UTC date",
)
def schedule_route(
    data: DailyChallengeScheduleCreate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> DailyChallengeScheduleResponse:
    q = _question_or_404(db, data.question_id)
    try:
        schedule = schedule_for_date(
            db,
            question=q,
            on_date=data.challenge_date,
            actor_id=teacher.id,
        )
    except QuestionRejectedError as exc:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_409_CONFLICT,
            message=str(exc),
            context={"resource_type": "daily_challenge_question", "resource_id": str(data.question_id)},
        ) from None
    except NotPublishableError as exc:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_409_CONFLICT,
            message=str(exc),
            context={
                "resource_type": "daily_challenge_schedule",
                "challenge_date": data.challenge_date.isoformat(),
                "question_id": str(data.question_id),
            },
        ) from None
    return DailyChallengeScheduleResponse(
        challenge_date=schedule.challenge_date,
        question_id=schedule.question_id,
        scheduled_at=schedule.scheduled_at,
    )


@router.post(
    "/generate",
    response_model=DailyChallengeGenerateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run the 6-round AI orchestrator for one passage; persists drafts",
    responses={
        201: {"description": "Generation complete; survivors persisted as DRAFT rows."},
        503: {"description": "GEMINI_API_KEY not configured on this deployment."},
    },
)
def generate_route(
    data: DailyChallengeGenerateRequest,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> DailyChallengeGenerateResponse:
    """Kick off the 6-round confrontation flow on a single passage.

    Synchronous because each run is short (~7 LLM round-trips, well
    under the Vercel function budget) and the editor wants the
    result immediately. Heavy-volume batch seeding (Sprint 6) should
    invoke ``run_generation`` from a script, not this endpoint."""
    from app.core.config import settings

    api_key = settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else ""
    if not api_key:
        raise equip_error(
            ErrorCode.TRANSLATION_WORKER_UNCONFIGURED,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            message="GEMINI_API_KEY is not configured on this deployment",
            context={"resource_type": "daily_challenge_generate"},
        )

    request = GenerationRequest(
        book=data.bible_book,
        chapter=data.bible_chapter,
        verse_from=data.bible_verse_from,
        verse_to=data.bible_verse_to,
        n_candidates_per_agent=data.n_candidates_per_agent,
        max_survivors=data.max_survivors,
        created_by=teacher.id,
    )
    with GeminiPromptClient(api_key=api_key) as client:
        outcome = run_generation(db, client=client, request=request)
    return DailyChallengeGenerateResponse(
        generation_run_id=outcome.generation_run_id,
        created_question_ids=outcome.created_question_ids,
        rejected_at_scripture=outcome.rejected_at_scripture,
        rejected_at_doctrinal=outcome.rejected_at_doctrinal,
        rejected_at_bilingual=outcome.rejected_at_bilingual,
        rounds_executed=outcome.rounds_executed,
        errors=outcome.errors,
    )


# ---------------------------------------------------------------------------
# Bilingual review surface (Sprint 7)
# ---------------------------------------------------------------------------


def _cv_cell(view: CvCellView) -> DailyChallengeCvCell:
    return DailyChallengeCvCell(
        cv_id=view.cv_id,
        text=view.text,
        origin=cast("Literal['human','mt'] | None", view.origin),
        locale=cast("Literal['en','ru']", view.locale),
        updated_at=view.updated_at,
    )


@router.get(
    "/questions",
    response_model=DailyChallengeQuestionQueueResponse,
    summary="List questions for the editorial review queue",
)
def list_questions_route(
    status_filter: DailyChallengeStatus | None = Query(default=None, alias="status"),
    # "What is still missing in German?" — the reviewer's actual question.
    # Was ``only_missing_ru``, a boolean that could only ever ask it about
    # Russian.
    missing_locale: LocaleCode | None = Query(default=None),
    rejected: bool = Query(default=False),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> DailyChallengeQuestionQueueResponse:
    items, total = list_review_queue(
        db,
        status_filter=status_filter,
        missing_locale=missing_locale,
        rejected=rejected,
        limit=limit,
        offset=offset,
    )
    return DailyChallengeQuestionQueueResponse(
        items=[
            DailyChallengeQuestionQueueItem(
                id=i.question.id,
                status=cast("DailyChallengeStatus", i.question.status),
                rejected=i.question.rejected,
                bible_book=i.question.bible_book,
                bible_chapter=i.question.bible_chapter,
                bible_verse_from=i.question.bible_verse_from,
                bible_verse_to=i.question.bible_verse_to,
                source_locale=i.question.source_locale,
                has_locale=i.has_locale,
                created_at=i.question.created_at,
                updated_at=i.question.updated_at,
            )
            for i in items
        ],
        total=total,
    )


@router.get(
    "/questions/{question_id}/bilingual",
    response_model=DailyChallengeBilingualView,
    summary="Bilingual view (parallel EN/RU cv cells) for editor side-by-side editing",
)
def get_bilingual_view_route(
    question_id: UUID,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> DailyChallengeBilingualView:
    q = _question_or_404(db, question_id)
    view = fetch_bilingual_view(db, question=q)
    return DailyChallengeBilingualView(
        id=q.id,
        status=cast("DailyChallengeStatus", q.status),
        rejected=q.rejected,
        rejection_reason=q.rejection_reason,
        bible_book=q.bible_book,
        bible_chapter=q.bible_chapter,
        bible_verse_from=q.bible_verse_from,
        bible_verse_to=q.bible_verse_to,
        source_locale=q.source_locale,
        question_text={locale: _cv_cell(cell) for locale, cell in view.question_text.items()},
        explanation={locale: _cv_cell(cell) for locale, cell in view.explanation.items()},
        options=[
            DailyChallengeBilingualOption(
                id=o.id,
                order_index=o.order_index,
                is_correct=o.is_correct,
                texts={locale: _cv_cell(cell) for locale, cell in o.texts.items()},
            )
            for o in view.options
        ],
    )


@router.post(
    "/questions/{question_id}/cv",
    response_model=DailyChallengeCvCell,
    summary="Upsert a single cv field/locale value for the question or one of its options",
)
def upsert_cv_route(
    question_id: UUID,
    data: DailyChallengeCvUpsertRequest,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> DailyChallengeCvCell:
    q = _question_or_404(db, question_id)
    try:
        cv = upsert_cv_for_question(
            db,
            question=q,
            field=data.field,
            locale=data.locale,
            text=data.text,
            option_id=data.option_id,
            actor_id=teacher.id,
        )
    except _QRRejectedError as exc:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_409_CONFLICT,
            message=str(exc),
            context={"resource_type": "daily_challenge_question", "resource_id": str(question_id)},
        ) from None
    except ValueError as exc:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message=str(exc),
            context={"resource_type": "daily_challenge_cv"},
        ) from None
    return DailyChallengeCvCell(
        cv_id=cv.id,
        text=cv.text,
        origin=cast("Literal['human','mt']", cv.origin),
        locale=cast("Literal['en','ru']", cv.locale),
        updated_at=cv.updated_at,
    )
