"""Admin tooling for the translation pipeline.

The orchestrator is fire-and-forget per spec: when Gemini fails a row
hits ``status='failed'`` and increments ``attempts``. After
``CONTENT_VERSION_MAX_ATTEMPTS`` (5) it promotes to
``failed_permanent`` — a terminal state where the auto-pipeline
refuses further retries. That's correct for the common case (a true
permanent failure: safety filter, oversize input) but trap-shaped for
the operator: a transient outage that ran out the budget leaves rows
stuck until someone touches the DB directly.

This module exposes the admin-only escape hatches. One resets
``failed_permanent`` rows back to ``failed`` with ``attempts=0`` so the
next reconcile pass picks them up. The other re-opens rows parked at
``needs_review`` — same mechanism, different reason: those are not
retried by design, and that design assumes the pipeline has not
changed. When a validator rule is corrected or the prompt rewritten,
every row parked under the old behaviour needs asking again, and
"UPDATE production by hand" is not an answer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003 — used by Pydantic schema at runtime

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session  # noqa: TC002 — used by FastAPI Depends at runtime

from app.api.dependencies import require_admin
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.content_version import ContentVersion
from app.models.translation_job import TranslationJob, TranslationJobStatus
from app.services.audit_service import log_action

if TYPE_CHECKING:
    from app.models.user import User


router = APIRouter(prefix="/admin/translations", tags=["admin-translations"])


class ResetByIdsRequest(BaseModel):
    """Reset a specific set of cv rows by primary key.

    Use this when the operator already knows which rows are stuck
    (e.g., from a Datadog alert that named the offending ids).
    """

    ids: list[UUID] = Field(..., min_length=1, max_length=500)


class ResetByEntityRequest(BaseModel):
    """Reset every failed row matching one ``(entity_type, entity_id,
    field, locale)`` selector — useful when the operator wants to
    unstick a whole entity without listing each row.
    """

    entity_type: str = Field(..., max_length=64)
    entity_id: str = Field(..., max_length=64)
    field: str = Field(..., max_length=64)
    locale: str = Field(..., max_length=10)


class ResetResponse(BaseModel):
    reset: int


class AcceptReviewedRequest(BaseModel):
    """Accept specific ``needs_review`` rows as servable, by primary key.

    By id and not by selector, deliberately: accepting is the operator
    saying "I read this one and it is fine", and that claim cannot be
    made about a set nobody enumerated. The ids come from the review
    queue, which shows the text and the reason beside each row.
    """

    ids: list[UUID] = Field(..., min_length=1, max_length=200)


@router.post(
    "/reset-by-ids",
    response_model=ResetResponse,
    summary="Reset failed_permanent cv rows by primary key",
    responses={
        200: {"description": "Rows reset; ``reset`` counts those actually touched."},
        404: {"description": "None of the supplied ids matched a failed_permanent row."},
    },
)
def reset_by_ids(
    payload: ResetByIdsRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ResetResponse:
    """Flip the listed rows from ``failed_permanent`` to ``failed`` and
    zero their ``attempts`` so the next orchestrator pass retries them.

    Rows in any other status are ignored — the endpoint is idempotent
    and refuses to silently mutate ``ok`` rows. Audit-logged.
    """
    try:
        affected = (
            db.query(ContentVersion)
            .filter(
                ContentVersion.id.in_(payload.ids),
                ContentVersion.status == "failed_permanent",
            )
            .update(
                {
                    ContentVersion.status: "failed",
                    ContentVersion.attempts: 0,
                },
                synchronize_session=False,
            )
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    if affected == 0:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="No failed_permanent rows matched the supplied ids.",
            context={"resource_type": "content_version"},
        )
    log_action(
        db,
        admin.id,
        "reset_failed_permanent",
        "content_version",
        ",".join(str(i) for i in payload.ids[:10]),
        details={"count": affected, "total_requested": len(payload.ids)},
        request=request,
    )
    return ResetResponse(reset=affected)


@router.post(
    "/reset-by-entity",
    response_model=ResetResponse,
    summary="Reset failed_permanent cv rows matching one (entity, field, locale)",
    responses={
        200: {"description": "Rows reset; ``reset`` counts those actually touched."},
        404: {"description": "No failed_permanent row matched the selector."},
    },
)
def reset_by_entity(
    payload: ResetByEntityRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ResetResponse:
    """Flip every ``failed_permanent`` row matching the selector back
    to ``failed`` with ``attempts=0``. Audit-logged.
    """
    try:
        affected = (
            db.query(ContentVersion)
            .filter(
                ContentVersion.entity_type == payload.entity_type,
                ContentVersion.entity_id == payload.entity_id,
                ContentVersion.field == payload.field,
                ContentVersion.locale == payload.locale,
                ContentVersion.status == "failed_permanent",
            )
            .update(
                {
                    ContentVersion.status: "failed",
                    ContentVersion.attempts: 0,
                },
                synchronize_session=False,
            )
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    if affected == 0:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="No failed_permanent row matched the selector.",
            context={"resource_type": "content_version"},
        )
    log_action(
        db,
        admin.id,
        "reset_failed_permanent",
        "content_version",
        f"{payload.entity_type}:{payload.entity_id}:{payload.field}:{payload.locale}",
        details={"count": affected},
        request=request,
    )
    return ResetResponse(reset=affected)


class RetryReviewedRequest(BaseModel):
    """Re-open rows parked at ``needs_review`` so the pipeline redoes them.

    The selector is deliberately coarse — a whole entity type, optionally
    one locale — because the case this exists for is coarse: the
    validator or the prompt changed, and everything parked under the old
    behaviour should be asked again.
    """

    entity_type: str = Field(..., max_length=64)
    locale: str | None = Field(default=None, max_length=10)
    limit: int = Field(default=200, ge=1, le=2000)


@router.post(
    "/retry-reviewed",
    response_model=ResetResponse,
    summary="Re-open needs_review cv rows so the next pass redoes them",
    responses={
        200: {"description": "Rows re-opened; ``reset`` counts those actually touched."},
        404: {"description": "No needs_review row matched the selector."},
    },
)
def retry_reviewed(
    payload: RetryReviewedRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ResetResponse:
    """Flip ``needs_review`` rows to ``failed`` with ``attempts=0``.

    A row parked for review is never retried on its own, and that is
    right: the model runs at temperature 0, so the same source produces
    the same text and the same verdict, and re-asking would burn quota
    to arrive back where we are. It stops being right the moment the
    *pipeline* changes. When a validator rule is corrected or the prompt
    is rewritten, every row parked under the old behaviour is a row
    nobody will ever look at again — the reader sees nothing, and the
    only tooling was a hand-written UPDATE against production.

    ``failed`` rather than deleting the row: the text and its
    ``review_reason`` stay readable in the audit trail, and ``failed``
    is the one status the orchestrator retries.

    Never touches ``origin='human'``. A person's own translation is not
    the pipeline's to redo.
    """
    query = db.query(ContentVersion).filter(
        ContentVersion.entity_type == payload.entity_type,
        ContentVersion.status == "needs_review",
        ContentVersion.origin != "human",
        ContentVersion.superseded_by.is_(None),
    )
    if payload.locale is not None:
        query = query.filter(ContentVersion.locale == payload.locale)

    ids = [row.id for row in query.order_by(ContentVersion.created_at).limit(payload.limit).all()]
    if not ids:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="No needs_review row matched the selector.",
            context={"resource_type": "content_version"},
        )

    try:
        affected = (
            db.query(ContentVersion)
            .filter(ContentVersion.id.in_(ids))
            .update(
                {ContentVersion.status: "failed", ContentVersion.attempts: 0},
                synchronize_session=False,
            )
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    log_action(
        db,
        admin.id,
        "retry_needs_review",
        "content_version",
        f"{payload.entity_type}:{payload.locale or 'all'}",
        details={"count": affected, "limit": payload.limit},
        request=request,
    )
    return ResetResponse(reset=affected)


@router.post(
    "/accept-reviewed",
    response_model=ResetResponse,
    summary="Accept needs_review cv rows as servable",
    responses={
        200: {"description": "Rows accepted; ``reset`` counts those actually flipped."},
        404: {"description": "No needs_review row matched the given ids."},
    },
)
def accept_reviewed(
    payload: AcceptReviewedRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ResetResponse:
    """Flip ``needs_review`` rows to ``ok`` — a person looked, and the
    check was wrong about this one.

    The structural check is deliberately strict, and strictness has a
    cost that lands entirely on the reader: a row it parks is invisible
    until somebody acts, and until now the only actions were "redo it"
    (which at temperature 0 returns the same text and the same verdict)
    and "edit production by hand". So a correct translation the checker
    misread stayed unreadable forever.

    That is not hypothetical. The language rule reports a short
    Ukrainian answer option as Russian — the two share most of a short
    phrase's letters, and on four words there is not enough evidence to
    tell them apart. Measured across production the detector is right
    to about one error in thirteen thousand lines, which is excellent
    and still means a handful of rows a person has to overrule.

    Accepting keeps ``review_reason`` on the row. The audit entry
    records who accepted what, because "a human decided this was fine"
    is exactly the kind of claim that should have a name attached.

    Never touches ``origin='human'``: those are not parked in the first
    place, and the guard costs nothing.
    """
    rows = (
        db.query(ContentVersion)
        .filter(
            ContentVersion.id.in_(payload.ids),
            ContentVersion.status == "needs_review",
            ContentVersion.origin != "human",
            ContentVersion.superseded_by.is_(None),
        )
        .all()
    )
    if not rows:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="No needs_review row matched the given ids.",
            context={"resource_type": "content_version"},
        )

    accepted = [(str(row.id), row.entity_type, row.locale, row.review_reason) for row in rows]
    try:
        affected = (
            db.query(ContentVersion)
            .filter(ContentVersion.id.in_([row.id for row in rows]))
            .update({ContentVersion.status: "ok"}, synchronize_session=False)
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    log_action(
        db,
        admin.id,
        "accept_needs_review",
        "content_version",
        ",".join(item[0] for item in accepted)[:200],
        details={
            "count": affected,
            "rows": [
                {"id": rid, "entity_type": etype, "locale": locale, "reason": reason}
                for rid, etype, locale, reason in accepted
            ],
        },
        request=request,
    )
    return ResetResponse(reset=affected)


class QueueStatusByState(BaseModel):
    """Count of jobs in each lifecycle state. Surfaced to the admin
    dashboard so the operator can spot a queue back-up at a glance."""

    queued: int
    processing: int
    done_last_hour: int
    failed: int
    failed_permanent: int


class StuckJobSummary(BaseModel):
    """A claimed job that hasn't reported back in a while. A growing
    list means the worker is hanging mid-process — either the Vercel
    function timed out and never wrote back, or a janitor pass is
    overdue."""

    id: str
    course_id: str
    started_at: datetime
    attempts: int


class QueueStatusResponse(BaseModel):
    by_state: QueueStatusByState
    oldest_queued_age_seconds: float | None = Field(
        default=None,
        description=(
            "Age of the oldest unstarted job. None when the queue is empty. "
            "Climbing means the cron tick is too slow for the publish volume."
        ),
    )
    stuck_jobs: list[StuckJobSummary] = Field(
        default_factory=list,
        description=(
            "Jobs in 'processing' for longer than 5 minutes. Suggests the "
            "Vercel function timed out mid-orchestrator without writing back; "
            "a janitor pass should re-queue them."
        ),
    )


@router.get(
    "/queue-status",
    response_model=QueueStatusResponse,
    summary="Translation queue health summary for the admin dashboard",
    responses={
        200: {"description": "Per-state counts + oldest-queued age + stuck-job summary."},
    },
)
def get_queue_status(
    stuck_threshold_seconds: int = Query(300, ge=10, le=3600),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> QueueStatusResponse:
    """Snapshot of queue health. Used by the operator before flipping
    ``TRANSLATION_QUEUE_ENABLED`` and to monitor live throughput once
    the cron is running.

    Counts are point-in-time — no smoothing. The ``done_last_hour``
    column gives a throughput proxy without paginating a huge
    completed-jobs list.
    """
    now = datetime.now(UTC)
    one_hour_ago = now.timestamp() - 3600
    stuck_cutoff = now.timestamp() - stuck_threshold_seconds

    by_status: dict[str, int] = {
        row[0]: row[1]
        for row in db.query(TranslationJob.status, func.count(TranslationJob.id)).group_by(TranslationJob.status).all()
    }

    done_recent = (
        db.query(func.count(TranslationJob.id))
        .filter(TranslationJob.status == TranslationJobStatus.DONE)
        .filter(TranslationJob.finished_at >= datetime.fromtimestamp(one_hour_ago, UTC))
        .scalar()
        or 0
    )

    oldest_queued = (
        db.query(TranslationJob.enqueued_at)
        .filter(TranslationJob.status == TranslationJobStatus.QUEUED)
        .order_by(TranslationJob.enqueued_at)
        .limit(1)
        .scalar()
    )
    # SQLite (test path) loses tz info on round-trip; coerce both sides
    # so the subtraction works regardless of dialect.
    if oldest_queued is not None and oldest_queued.tzinfo is None:
        oldest_queued = oldest_queued.replace(tzinfo=UTC)
    oldest_age = (now - oldest_queued).total_seconds() if oldest_queued else None

    stuck_rows = (
        db.query(TranslationJob)
        .filter(TranslationJob.status == TranslationJobStatus.PROCESSING)
        .filter(TranslationJob.started_at <= datetime.fromtimestamp(stuck_cutoff, UTC))
        .order_by(TranslationJob.started_at)
        .limit(50)
        .all()
    )

    return QueueStatusResponse(
        by_state=QueueStatusByState(
            queued=by_status.get(TranslationJobStatus.QUEUED, 0),
            processing=by_status.get(TranslationJobStatus.PROCESSING, 0),
            done_last_hour=done_recent,
            failed=by_status.get(TranslationJobStatus.FAILED, 0),
            failed_permanent=by_status.get(TranslationJobStatus.FAILED_PERMANENT, 0),
        ),
        oldest_queued_age_seconds=oldest_age,
        stuck_jobs=[
            StuckJobSummary(
                id=str(row.id),
                course_id=row.course_id,
                started_at=row.started_at if row.started_at.tzinfo else row.started_at.replace(tzinfo=UTC),
                attempts=row.attempts,
            )
            for row in stuck_rows
            if row.started_at is not None
        ],
    )
