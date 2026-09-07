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

It also exposes the queue those escape hatches act on. Deciding
whether a parked translation is fine takes reading it beside its
source, and for a long time there was nowhere to read it: the ids the
accept endpoint asks for could only come from a hand-written SELECT.
An operator surface whose only input is a production query is not an
operator surface, so nothing was ever accepted and courses waited.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, tuple_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session  # noqa: TC002 — used by FastAPI Depends at runtime

from app.api.dependencies import require_admin
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.content_version import ContentVersion
from app.models.course import CourseStatus
from app.models.translation_job import TranslationJob, TranslationJobStatus
from app.schemas.locale import LocaleCode  # noqa: TC001 — used by FastAPI Query at runtime
from app.services.audit_service import log_action
from app.services.course_service import get_course
from app.services.translation.completeness import promote_if_complete
from app.services.translation.course_tree import iter_course_entities
from app.services.translation.queue import enqueue_course_translation
from app.services.translation.registry import ENTITY_MODEL, REGISTRY, EntityRegistration
from app.services.translation.resolve_for_display import populate_spine_texts

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.user import User

logger = logging.getLogger(__name__)

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


class PurgeOrphansRequest(BaseModel):
    """Remove translation rows whose entity no longer exists.

    Counting is free and always safe, so it is the default: without
    ``confirm`` this reports what it would remove and changes nothing.
    """

    confirm: bool = False


class RestoreLastGoodRequest(BaseModel):
    """Put a previously servable translation back in front of readers.

    By id, like accepting: the ids come from the queue or from a report,
    and the operator is saying "this row is not fit to serve and the one
    it replaced was".
    """

    ids: list[UUID] = Field(..., min_length=1, max_length=200)


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

    Two shapes, because there are two cases and they are not the same
    size. The selector — a whole entity type, optionally one locale — is
    for the coarse one this endpoint was written for: the validator or
    the prompt changed, and everything parked under the old behaviour
    should be asked again.

    ``ids`` is for the other one, which only became reachable once the
    review queue existed: a person reading a single row decides the
    translation is wrong rather than misjudged, and asks for that row
    again. Re-opening its whole entity type because the request had no
    way to name one row would be a surprising amount of collateral for
    pressing "retry" beside a line of text.
    """

    entity_type: str | None = Field(default=None, max_length=64)
    ids: list[UUID] | None = Field(default=None, min_length=1, max_length=200)
    locale: str | None = Field(default=None, max_length=10)
    limit: int = Field(default=200, ge=1, le=2000)

    @model_validator(mode="after")
    def require_a_selector(self) -> RetryReviewedRequest:
        """One of the two shapes, not neither.

        Without this an empty body would mean "every parked row on the
        platform", which is not a request anybody makes on purpose.
        """
        if self.entity_type is None and self.ids is None:
            raise ValueError("Supply either 'ids' or 'entity_type'.")
        return self


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
        ContentVersion.status == "needs_review",
        ContentVersion.origin != "human",
        ContentVersion.superseded_by.is_(None),
    )
    if payload.ids is not None:
        query = query.filter(ContentVersion.id.in_(payload.ids))
    if payload.entity_type is not None:
        query = query.filter(ContentVersion.entity_type == payload.entity_type)
    if payload.locale is not None:
        query = query.filter(ContentVersion.locale == payload.locale)

    rows = query.order_by(ContentVersion.created_at).limit(payload.limit).all()
    ids = [row.id for row in rows]
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

    # A re-opened row is ``failed``, and ``failed`` is retried — by the
    # next pass, if there is one. The sweep would find it eventually,
    # one cycle from now; the operator who just pressed the button is
    # owed sooner than that, and so is the course waiting on the row.
    queued = _requeue_courses_of(db, rows, requested_by=admin.id)

    log_action(
        db,
        admin.id,
        "retry_needs_review",
        "content_version",
        # Name what was actually asked for: the rows when the operator
        # listed them, the selector when they described a set. An audit
        # entry reading "quiz_option:all" for a one-row retry from the
        # queue would misrepresent the size of what happened.
        ",".join(str(i) for i in payload.ids[:10])
        if payload.ids is not None
        else f"{payload.entity_type}:{payload.locale or 'all'}",
        details={"count": affected, "limit": payload.limit, "queued_courses": queued},
        request=request,
    )
    return ResetResponse(reset=affected)


def _courses_touched_by(db: Session, rows: list[ContentVersion]) -> list[Course]:
    """The distinct courses the given rows hang off, in a stable order.

    Daily Challenge rows belong to no course and resolve to nothing;
    that is not an error, there is simply no course to move.
    """
    by_id = {course.id: course for course in _courses_for_rows(db, rows).values()}
    return [by_id[key] for key in sorted(by_id)]


def _promote_courses_of(db: Session, rows: list[ContentVersion]) -> list[str]:
    """After rows were accepted: let every course they completed out.

    Accepting the last parked row makes a course whole, and until
    2026-09-05 nothing then acted on that. ``promote_if_complete`` had
    one caller — the worker, after its own pass — and no pass follows
    an accept: the executor skips a parked row whose source is
    unchanged, the sweep queues no job for a course whose only gaps
    were a person's to close, and the course sat in ``publishing``,
    complete and invisible, until somebody happened to PATCH it. The
    teacher meanwhile lost the "prepare for publication" button, which
    the card hides once ``is_complete`` is true. Returns the ids of the
    courses that went out.

    A failure to promote never undoes the accept: the rows are already
    committed and correct, and the sweep now promotes a whole
    ``publishing`` course on its own cycle, so this is the fast path,
    not the only path.
    """
    promoted: list[str] = []
    for course in _courses_touched_by(db, rows):
        if course.status != CourseStatus.PUBLISHING:
            continue
        try:
            if promote_if_complete(db, course):
                promoted.append(str(course.id))
        except SQLAlchemyError:
            db.rollback()
            logger.exception("accept_reviewed: could not promote course %s after accepting its rows", course.id)
    return promoted


def _requeue_courses_of(db: Session, rows: list[ContentVersion], *, requested_by: UUID) -> list[str]:
    """After rows were re-opened: queue a pass for every live course
    they belong to, so the retry the operator asked for happens now
    rather than whenever the sweep's cycle comes round.

    ``enqueue_course_translation`` is idempotent and a redundant job
    costs one plan and no provider calls, so queueing a course that
    already has a job is free. Drafts are left alone, as everywhere:
    their author translates them when ready. Only meaningful with the
    queue on — without it there is no worker to drain what is queued.
    """
    if not settings.TRANSLATION_QUEUE_ENABLED:
        return []
    queued: list[str] = []
    for course in _courses_touched_by(db, rows):
        if course.status not in (CourseStatus.PUBLISHING, CourseStatus.PUBLISHED):
            continue
        try:
            enqueue_course_translation(db, str(course.id), requested_by=requested_by)
            queued.append(str(course.id))
        except SQLAlchemyError:
            db.rollback()
            logger.exception("retry_reviewed: could not queue course %s after re-opening its rows", course.id)
    return queued


class OrphanReport(BaseModel):
    removed: int
    by_entity_type: dict[str, int]
    dry_run: bool


@router.post(
    "/purge-orphans",
    response_model=OrphanReport,
    summary="Remove translation rows whose entity no longer exists",
    responses={200: {"description": "Counts per entity type; ``removed`` is 0 unless ``confirm`` was set."}},
)
def purge_orphans(
    payload: PurgeOrphansRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> OrphanReport:
    """Find and, on ``confirm``, delete rows pointing at ids that are gone.

    ``content_versions.entity_id`` is polymorphic text with no foreign
    key behind it, so no database constraint can notice when the row it
    names is deleted. Every delete path sweeps its own translations, and
    when one of them has a bug the rows it should have taken simply stay
    — on no screen, in every count, forever.

    That happened: until 2026-08-25 the course sweep queried uuid columns
    with stringified ids, and production accumulated 731 rows across six
    entity types between May and August. Nothing was wrong with the data
    in them; there was simply nothing left to attach them to.

    Counting is the default. A dry run answers the same shape with
    ``removed: 0``, which makes "how much is there" a question anyone can
    ask without deciding anything.
    """
    from app.services.translation.registry import ENTITY_MODEL

    by_type: dict[str, int] = {}
    removed = 0
    try:
        for entity_type, model in ENTITY_MODEL.items():
            # Compared in Python, not in SQL. ``entity_id`` is text and a
            # model's key is usually uuid: Postgres refuses that
            # comparison outright, and casting to text papers over a
            # difference in how each database spells a uuid — SQLite
            # stores 32 hex characters where Postgres writes the hyphens.
            # A cast-based query looked right and deleted rows whose
            # entity was sitting right there.
            #
            # ``ENTITY_MODEL`` is typed as ``type``; every value in it is
            # a mapped class with an ``id``, which the type does not say.
            live = {str(pk) for (pk,) in db.query(model.id)}  # type: ignore[attr-defined]
            referenced = {
                eid
                for (eid,) in db.query(ContentVersion.entity_id)
                .filter(ContentVersion.entity_type == entity_type)
                .distinct()
            }
            gone = sorted(referenced - live)
            if not gone:
                continue
            orphaned = db.query(ContentVersion).filter(
                ContentVersion.entity_type == entity_type,
                ContentVersion.entity_id.in_(gone),
            )
            count = orphaned.count()
            by_type[entity_type] = count
            if payload.confirm:
                orphaned.delete(synchronize_session=False)
                removed += count
        if payload.confirm:
            db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    if payload.confirm and removed:
        log_action(
            db,
            admin.id,
            "purge_orphan_translations",
            "content_version",
            "orphans",
            details={"removed": removed, "by_entity_type": by_type},
            request=request,
        )
    return OrphanReport(removed=removed, by_entity_type=by_type, dry_run=not payload.confirm)


@router.post(
    "/restore-last-good",
    response_model=ResetResponse,
    summary="Put the last servable translation back in front of readers",
    responses={
        200: {"description": "Rows restored; ``reset`` counts those actually swapped."},
        404: {"description": "No listed row was both unservable and standing on a good one."},
    },
)
def restore_last_good(
    payload: RestoreLastGoodRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ResetResponse:
    """Make the newest superseded ``ok`` row active again, behind an
    unservable one that replaced it.

    Until 2026-08-24 a rejected retry superseded the row it failed to
    improve on, and readers lost a translation they already had. The
    write path no longer does that — but the rows it already did it to
    are still in production, and the only way to correct one was an
    UPDATE typed against the live database, which is exactly the thing
    this project does not do.

    So: for each listed row that is active and not ``ok``, find the
    newest row it superseded that is ``ok`` and has text, and swap them.
    The unservable row is kept, now pointing at the row it used to
    replace, so nothing is deleted and the audit trail still shows what
    the model said.

    Rows that are already servable, that never superseded anything, or
    whose predecessor is human-authored are left alone — a human row is
    not the pipeline's to reinstate, and it would not have been
    superseded by a machine one in the first place.
    """
    restored = 0
    try:
        for row in (
            db.query(ContentVersion)
            .filter(
                ContentVersion.id.in_(payload.ids),
                ContentVersion.superseded_by.is_(None),
                ContentVersion.status != "ok",
            )
            .all()
        ):
            predecessor = (
                db.query(ContentVersion)
                .filter(
                    ContentVersion.superseded_by == row.id,
                    ContentVersion.status == "ok",
                    ContentVersion.origin == "mt",
                    ContentVersion.text != "",
                )
                .order_by(ContentVersion.updated_at.desc())
                .first()
            )
            if predecessor is None:
                continue
            # Occupy the key before freeing it: one active row per
            # (entity, field, locale) is a unique index, not a
            # convention, and doing this the other way round trips it.
            row.superseded_by = predecessor.id
            db.flush()
            predecessor.superseded_by = None
            db.flush()
            restored += 1
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    if restored == 0:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="No listed row was both unservable and standing on a translation that could be restored.",
            context={"resource_type": "content_version"},
        )
    log_action(
        db,
        admin.id,
        "restore_last_good_translation",
        "content_version",
        ",".join(str(i) for i in payload.ids[:10]),
        details={"count": restored, "total_requested": len(payload.ids)},
        request=request,
    )
    return ResetResponse(reset=restored)


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

    # The row is servable; now the course it may have completed.
    promoted = _promote_courses_of(db, rows)

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
            "promoted_courses": promoted,
        },
        request=request,
    )
    return ResetResponse(reset=affected)


# ---------------------------------------------------------------------------
# The queue the two endpoints above were written against.
# ---------------------------------------------------------------------------
#
# ``AcceptReviewedRequest`` says the ids "come from the review queue,
# which shows the text and the reason beside each row". They did not:
# the queue was never built. The only way to obtain an id was a
# hand-written SELECT against production — the exact thing this
# subsystem exists to replace — so in practice nobody accepted or
# retried anything, and every row the structural check parked stayed
# parked. A course with one such row stays out of the catalogue; a
# staged edit waiting on one stays unpublished. This is the read half.


class NeedsReviewRow(BaseModel):
    """One parked translation, with enough beside it to judge it.

    A reviewer cannot decide from an id and a status. They need the
    text that came back, the text it was made from, the reason the
    check refused it, and — the part that turns a list of UUIDs into a
    page a person can work through — what the row actually *is*: which
    course it belongs to, or that it belongs to none because it is
    Daily Challenge content, which is platform-wide.
    """

    id: UUID
    entity_type: str
    entity_id: str
    field: str
    locale: str
    source_locale: str | None
    review_reason: str | None
    #: What the provider returned. Kept on the row precisely so a person
    #: can read it — it is stored but not served (see ContentVersionStatus).
    text: str
    #: The text this was translated from. ``None`` when the source row
    #: has since been superseded away and the link did not survive.
    source_text: str | None
    created_at: datetime
    #: ``None`` for entities that belong to no course. That is not an
    #: error and not missing data — see ``is_daily_challenge``.
    course_id: str | None
    course_title: str | None
    #: Platform-wide content (the Daily Challenge rotation) has no owning
    #: course. Flagged explicitly so the UI can say "Daily Challenge"
    #: rather than render an empty course column and look broken.
    is_daily_challenge: bool


class NeedsReviewPage(BaseModel):
    items: list[NeedsReviewRow]
    total: int
    limit: int
    offset: int


# ``content_versions.entity_type`` is Text, not the Literal — by design,
# so a new entity type is an INSERT and not a migration. The flip side is
# that a row can name an entity this build no longer knows about, and a
# KeyError while resolving one row would take out the whole page. Keyed
# by plain ``str`` so the lookup can simply miss.
_REGISTRATION_BY_NAME: dict[str, EntityRegistration] = {str(name): reg for name, reg in REGISTRY.items()}
_MODEL_BY_NAME: dict[str, type] = {str(name): model for name, model in ENTITY_MODEL.items()}


def _load_entities(db: Session, entity_type: str, entity_ids: set[str]) -> dict[str, Any]:
    """Bulk-load the entities behind one page's worth of rows, by type.

    ``entity_id`` is Text on every row while the entities themselves are
    keyed by str (courses, modules, chapters) or by UUID (quizzes,
    questions, Daily Challenge content). Coerce per model rather than
    guessing from the string: an id that will not parse belongs to no
    row we can load, and dropping it silently is right — the queue still
    shows the translation, just without course context.
    """
    model: Any = _MODEL_BY_NAME.get(entity_type)
    if model is None or not entity_ids:
        return {}
    try:
        python_type = model.id.type.python_type
    except NotImplementedError:  # pragma: no cover — no such column type today
        python_type = str
    keys: list[Any]
    if python_type is UUID:
        keys = []
        for value in entity_ids:
            try:
                keys.append(UUID(value))
            except ValueError:
                continue
    else:
        keys = list(entity_ids)
    if not keys:
        return {}
    return {str(entity.id): entity for entity in db.query(model).filter(model.id.in_(keys)).all()}


def _courses_for_rows(db: Session, rows: list[ContentVersion]) -> dict[tuple[str, str], Course]:
    """Resolve each row's owning course, keyed by ``(entity_type, entity_id)``.

    Through the registry's own ``resolve_course``, not a second copy of
    the walk: the registry is where "what does this entity hang off"
    lives, and a private reimplementation here would be a fifth place to
    update when a new entity type lands.

    Resolution is per entity and costs a query or two, so it is done for
    one page at a time and keyed by entity rather than by row — the same
    chapter typically shows up several times over (one row per field per
    locale), and it should be resolved once.
    """
    ids_by_type: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        ids_by_type[row.entity_type].add(row.entity_id)

    resolved: dict[tuple[str, str], Course] = {}
    for entity_type, entity_ids in ids_by_type.items():
        registration = _REGISTRATION_BY_NAME.get(entity_type)
        if registration is None:
            continue
        entities = _load_entities(db, entity_type, entity_ids)
        for entity_id, entity in entities.items():
            course = registration.resolve_course(db, entity)
            if course is not None:
                resolved[(entity_type, entity_id)] = course

    # Titles live in content_versions — reading
    # ``course.title`` off an un-hydrated instance raises. Hydrate the
    # distinct courses once, at their own source locale (this is an
    # operator screen; the author's wording is the useful label), and
    # skip the module tree nobody here serialises.
    unique_courses = list({course.id: course for course in resolved.values()}.values())
    populate_spine_texts(db, unique_courses, hydrate_modules=False)
    return resolved


def _source_texts_for_rows(db: Session, rows: list[ContentVersion]) -> dict[UUID, str]:
    """The text each row was translated from, keyed by row id.

    ``source_version_id`` names the exact version the provider was given,
    which is the honest answer and the one to prefer. It is nullable and
    ``ON DELETE SET NULL``, so rows written before the link existed — and
    rows whose source was deleted — fall back to whatever is active at
    the row's ``source_locale`` today. That is a slightly different claim
    ("this is the source now" rather than "this is what it saw"), and it
    is still what a reviewer needs to see.
    """
    wanted_versions = {row.source_version_id for row in rows if row.source_version_id is not None}
    text_by_version: dict[UUID, str] = {}
    if wanted_versions:
        text_by_version = {
            version.id: version.text
            for version in db.query(ContentVersion).filter(ContentVersion.id.in_(wanted_versions)).all()
        }

    texts: dict[UUID, str] = {}
    fallback_keys: list[tuple[str, str, str, str]] = []
    for row in rows:
        linked = text_by_version.get(row.source_version_id) if row.source_version_id else None
        if linked is not None:
            texts[row.id] = linked
        elif row.source_locale:
            fallback_keys.append((row.entity_type, row.entity_id, row.field, row.source_locale))

    if fallback_keys:
        active = (
            db.query(ContentVersion)
            .filter(
                tuple_(
                    ContentVersion.entity_type,
                    ContentVersion.entity_id,
                    ContentVersion.field,
                    ContentVersion.locale,
                ).in_(fallback_keys),
                ContentVersion.superseded_by.is_(None),
            )
            .all()
        )
        by_key = {(row.entity_type, row.entity_id, row.field, row.locale): row.text for row in active}
        for row in rows:
            if row.id in texts or not row.source_locale:
                continue
            found = by_key.get((row.entity_type, row.entity_id, row.field, row.source_locale))
            if found is not None:
                texts[row.id] = found
    return texts


@router.get(
    "/needs-review",
    response_model=NeedsReviewPage,
    summary="List the translations parked for human review",
    responses={
        200: {"description": "One page of parked rows, oldest first. Empty when nothing is parked."},
        404: {"description": "The ``course_id`` filter named a course that does not exist."},
    },
)
def list_needs_review(
    locale: LocaleCode | None = Query(default=None, description="Only rows in this target language."),
    course_id: str | None = Query(default=None, description="Only rows belonging to this course."),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> NeedsReviewPage:
    """What is waiting on a person, with the text and the reason attached.

    The filters are the same three predicates ``accept-reviewed`` and
    ``retry-reviewed`` apply — parked, machine-made, still active — and
    that is deliberate rather than tidy: a queue that listed a row the
    buttons beside it would refuse to touch is worse than no queue.
    ``origin='human'`` rows never appear, because a person's own
    translation is not the pipeline's to second-guess.

    An empty page is a 200 with ``total: 0``. The mutators answer 404
    for nothing-matched because they were asked to change something and
    could not; being asked what is waiting, and answering "nothing", is
    a success.

    Filtering by course cannot be a WHERE clause — a
    ``content_versions`` row knows its entity, not the course above it —
    so it walks the course tree and matches on what the walk yields.
    That is the same walk the readiness panel counts through, which is
    the point: the number on the card and the rows on this page cannot
    disagree about which course a chapter belongs to.
    """
    query = db.query(ContentVersion).filter(
        ContentVersion.status == "needs_review",
        ContentVersion.origin != "human",
        ContentVersion.superseded_by.is_(None),
    )
    if locale is not None:
        query = query.filter(ContentVersion.locale == locale)

    if course_id is not None:
        course = get_course(db, course_id)
        if course is None:
            raise equip_error(
                ErrorCode.RESOURCE_NOT_FOUND,
                status_code=status.HTTP_404_NOT_FOUND,
                message=f"Course '{course_id}' not found",
                context={"resource_type": "course", "resource_id": course_id},
            )
        entity_keys = [
            (entity_type, str(entity.id))  # type: ignore[attr-defined]
            for entity_type, entity in iter_course_entities(db, course)
        ]
        if not entity_keys:
            return NeedsReviewPage(items=[], total=0, limit=limit, offset=offset)
        query = query.filter(tuple_(ContentVersion.entity_type, ContentVersion.entity_id).in_(entity_keys))

    total = query.count()
    # Oldest first: the row that has been unreadable the longest is the
    # one to look at next. ``id`` breaks ties so paging cannot repeat or
    # skip a row when several land in the same transaction.
    rows = query.order_by(ContentVersion.created_at, ContentVersion.id).offset(offset).limit(limit).all()
    if not rows:
        return NeedsReviewPage(items=[], total=total, limit=limit, offset=offset)

    courses = _courses_for_rows(db, rows)
    source_texts = _source_texts_for_rows(db, rows)

    return NeedsReviewPage(
        items=[
            NeedsReviewRow(
                id=row.id,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                field=row.field,
                locale=row.locale,
                source_locale=row.source_locale,
                review_reason=row.review_reason,
                text=row.text,
                source_text=source_texts.get(row.id),
                created_at=row.created_at,
                course_id=courses[(row.entity_type, row.entity_id)].id
                if (row.entity_type, row.entity_id) in courses
                else None,
                course_title=getattr(courses.get((row.entity_type, row.entity_id)), "title", None) or None,
                is_daily_challenge=row.entity_type.startswith("daily_challenge"),
            )
            for row in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


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
