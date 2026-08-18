"""Run a set of translations concurrently, because the wait is the work.

Measured on 2026-08-17, with an instant fake provider so the only thing
left was our own code: a 180-call pass costs **1 ms per call** in tree
walking, language detection, skip decisions, validation and writes. The
other 420 ms per call is the pipeline sitting on a socket.

Which means the pipeline was spending 99.8% of its life waiting, one
call at a time, and a real course is 2,610 calls:

    sequential, 0.42 s/call     ~18 minutes of pure waiting
    8 at a time                 ~2 minutes
    16 at a time                ~1 minute

The API has the room — 24 requests at width 16 came back in 0.9 s, no
errors, latency flat at 0.38 s, which is over 1,600 requests a minute
against a pipeline that was doing 146.

Why this is a separate module rather than threads sprinkled into the
orchestrator: a SQLAlchemy Session is not thread-safe, and the fix is
not a lock — it is keeping the database out of the threads entirely.
So the pass runs in three phases:

1. **Decide** — one thread, the caller's session. What is already
   done, what a twin row can answer for free, what must be asked.
2. **Ask** — many threads, no database at all. Just the provider and
   the validator, which are pure with respect to our state.
3. **Record** — one thread, the caller's session again.

The phases also make the budget honest: it is checked between batches,
so a pass that runs out of time stops having started nothing it cannot
finish, exactly as the serial path did.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

from app.models.content_version import ContentVersion, ContentVersionStatus
from app.services.translation.budget import NoBudget
from app.services.translation.protocol import TranslationError, TranslationRequest
from app.services.translation.validation import ValidationIssue, summarise, validate_translation

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.content_version import ContentVersionField as TranslationField
    from app.schemas.locale import LocaleCode
    from app.services.translation.budget import TranslationBudget
    from app.services.translation.protocol import ContentKind, EntityType, TranslationProvider
    from app.services.translation.stores import VersionStore

logger = logging.getLogger(__name__)

# How many provider calls are in flight at once.
#
# Eight rather than sixteen: the measured ceiling is far higher, but the
# gain from 8 to 16 is a minute against half a minute on the largest
# course we have, and the cost of being wrong about someone else's rate
# limit is a burst of 429s in production. Room to raise it deliberately,
# once there is a course big enough for the difference to matter.
DEFAULT_MAX_WORKERS = 8

Outcome = Literal["translated", "skipped", "failed", "needs_review", "deferred"]


@dataclass(frozen=True, slots=True)
class TranslationTask:
    """One (field, target locale) to translate, with everything the call
    needs. Built by the callers from the registry's field specs."""

    entity_type: EntityType
    entity_id: str
    field: TranslationField
    source_locale: LocaleCode
    target_locale: LocaleCode
    text: str
    content_kind: ContentKind
    source_hash: str
    context: str | None = None


@dataclass(frozen=True, slots=True)
class _Answer:
    """What phase two produced for one task."""

    task: TranslationTask
    text: str | None
    issues_summary: str | None
    failed: bool


def _decide(
    db: Session,
    task: TranslationTask,
    store: VersionStore,
) -> tuple[Outcome, str | None] | None:
    """Is this task already answered? Returns the settled outcome, plus
    the text to record when a twin supplies one — or ``None`` when the
    provider has to be asked.

    Identical rules to the serial path, in the same order, because they
    are the rules and not an implementation detail: a human translation
    is never overwritten, an up-to-date row is not re-asked, a row
    parked for review moves only when its source changes, and a row that
    exhausted its retries is terminal.
    """
    existing = store.active_row(
        db,
        entity_type=task.entity_type,
        entity_id=task.entity_id,
        field=task.field,
        locale=task.target_locale,
    )
    if existing is not None:
        if existing.origin == "human":
            return "skipped", None
        if existing.status == "ok" and existing.source_hash == task.source_hash:
            return "skipped", None
        if existing.status == "needs_review" and existing.source_hash == task.source_hash:
            return "skipped", None
        if existing.status == "failed_permanent":
            return "skipped", None

    # Identical source, already translated somewhere else: reuse it
    # rather than pay again, and gain consistency between an answer
    # option and its twin in another quiz as a side effect.
    twin = (
        db.query(ContentVersion.text)
        .filter(
            ContentVersion.locale == task.target_locale,
            ContentVersion.source_hash == task.source_hash,
            ContentVersion.status == ContentVersionStatus.OK,
            ContentVersion.superseded_by.is_(None),
            ~((ContentVersion.entity_type == task.entity_type) & (ContentVersion.entity_id == task.entity_id)),
        )
        .order_by(ContentVersion.created_at)
        .limit(1)
        .scalar()
    )
    if twin is not None:
        return "translated", twin
    return None


def _ask(task: TranslationTask, provider: TranslationProvider) -> _Answer:
    """Phase two, and the only phase that runs off the main thread.

    Touches no database and no shared state: the provider owns an
    httpx client that is safe to share, and the validator is pure.

    The one retry on a failed structural check lives here because it is
    part of asking, not of recording — see the orchestrator's note on
    why a first bad answer is usually a bad roll rather than a fact.
    """
    request = TranslationRequest(
        text=task.text,
        source_locale=task.source_locale,
        target_locale=task.target_locale,
        content_kind=task.content_kind,
        context=task.context,
    )
    try:
        result = provider.translate(request)
    except TranslationError as exc:
        logger.warning(
            "Translation failed entity=%s:%s field=%s locale=%s err=%s",
            task.entity_type,
            task.entity_id,
            task.field,
            task.target_locale,
            exc,
        )
        return _Answer(task=task, text=None, issues_summary=None, failed=True)

    issues = validate_translation(
        source=task.text,
        translated=result.text,
        source_locale=task.source_locale,
        target_locale=task.target_locale,
        content_kind=task.content_kind,
    )
    if issues:
        # Two different remedies, and which one applies depends on why
        # the first answer was wrong.
        #
        # Sampling is at temperature 0, so asking the identical question
        # a second time returns the identical answer — a plain retry
        # only ever helps when the failure was in the trip rather than
        # in the judgement (a truncated response, a network fault). For
        # a defect the model actively prefers, the question has to
        # change: show it the words it chose and ask for different ones.
        try:
            retry = provider.translate(replace(request, rewrite_notes=tuple(issue.detail for issue in issues)))
        except TranslationError:
            retry = None
        if retry is not None:
            retry_issues = validate_translation(
                source=task.text,
                translated=retry.text,
                source_locale=task.source_locale,
                target_locale=task.target_locale,
                content_kind=task.content_kind,
            )
            # Keep whichever answer is less wrong. The model is not
            # deterministic, so a second pass is a second roll, not a
            # correction — and a retry that fixed the calque but broke a
            # placeholder must not be preferred to the first answer.
            if _rank(retry_issues) < _rank(issues):
                result, issues = retry, retry_issues

    blocking = [issue for issue in issues if issue.blocking]
    style = [issue for issue in issues if not issue.blocking]
    if style and not blocking:
        # Correct but stiff. Served, because a reader gains more from a
        # slightly translated-sounding sentence than from a gap — and
        # logged with a stable code, so the rate is a number on a
        # dashboard rather than an impression.
        logger.warning(
            "translation_style entity=%s:%s field=%s locale=%s notes=%s",
            task.entity_type,
            task.entity_id,
            task.field,
            task.target_locale,
            summarise(style),
        )

    return _Answer(
        task=task,
        text=result.text,
        issues_summary=summarise(blocking) if blocking else None,
        failed=False,
    )


def _rank(issues: list[ValidationIssue]) -> tuple[int, int]:
    """How bad a set of issues is: blocking defects first, then style."""
    return (
        sum(1 for issue in issues if issue.blocking),
        sum(1 for issue in issues if not issue.blocking),
    )


def _record(db: Session, answer: _Answer, store: VersionStore) -> Outcome:
    """Phase three: back on the caller's session, one write at a time."""
    task = answer.task
    if answer.failed:
        store.record_failure(
            db,
            entity_type=task.entity_type,
            entity_id=task.entity_id,
            field=task.field,
            locale=task.target_locale,
            source_locale=task.source_locale,
            source_hash=task.source_hash,
        )
        return "failed"

    if answer.text is None:
        return "failed"

    parked = answer.issues_summary is not None
    if parked:
        logger.warning(
            "Translation failed validation entity=%s:%s field=%s locale=%s issues=%s",
            task.entity_type,
            task.entity_id,
            task.field,
            task.target_locale,
            answer.issues_summary,
        )
    store.record_success(
        db,
        entity_type=task.entity_type,
        entity_id=task.entity_id,
        field=task.field,
        locale=task.target_locale,
        text=answer.text,
        source_locale=task.source_locale,
        source_hash=task.source_hash,
        status=ContentVersionStatus.NEEDS_REVIEW if parked else ContentVersionStatus.OK,
        review_reason=answer.issues_summary,
    )
    return "needs_review" if parked else "translated"


@dataclass(frozen=True, slots=True)
class PlanResult:
    translated: int = 0
    skipped: int = 0
    failed: int = 0
    needs_review: int = 0
    incomplete: bool = False


def execute_plan(
    db: Session,
    tasks: list[TranslationTask],
    *,
    provider: TranslationProvider,
    store: VersionStore,
    budget: TranslationBudget | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> PlanResult:
    """Decide, ask concurrently, record. Returns the same counters the
    serial path returned, so callers and tests read unchanged."""
    if not tasks:
        return PlanResult()

    active_budget = budget or NoBudget()
    translated = skipped = failed = needs_review = 0
    incomplete = False

    # Phase 1 — everything the database can answer without asking anyone.
    pending: list[TranslationTask] = []
    for task in tasks:
        settled = _decide(db, task, store)
        if settled is None:
            pending.append(task)
            continue
        outcome, text = settled
        if outcome == "skipped":
            skipped += 1
        elif text is not None:
            store.record_success(
                db,
                entity_type=task.entity_type,
                entity_id=task.entity_id,
                field=task.field,
                locale=task.target_locale,
                text=text,
                source_locale=task.source_locale,
                source_hash=task.source_hash,
                status=ContentVersionStatus.OK,
                review_reason=None,
            )
            translated += 1

    # Identical text, asked once.
    #
    # 27% of the production corpus is duplicate source text — 970 of
    # 3,562 rows share a hash with another row, because answer options
    # repeat ("True", "Yes", "Neither of these") across quizzes. The
    # serial path got this for free: the first row was written, and the
    # twin lookup answered the rest. Concurrency broke that, because
    # the duplicates are in flight together and none of them is written
    # yet — so the same string went to the provider several times, paid
    # for several times, and could come back worded differently each
    # time (temperature 0 is not determinism; measured).
    #
    # So the batch is built from distinct (source text, target
    # language), and the answer is recorded for every task that shares
    # it.
    by_text: dict[tuple[str, str], list[TranslationTask]] = {}
    for task in pending:
        by_text.setdefault((task.source_hash, task.target_locale), []).append(task)
    representatives = [group[0] for group in by_text.values()]

    # Phases 2 and 3, one batch at a time. The batch boundary is where
    # the budget is honoured: a pass never begins work it cannot pay
    # for, and what it did finish is already recorded.
    width = max(1, max_workers)
    for start in range(0, len(representatives), width):
        if not active_budget.can_afford_one_call():
            incomplete = True
            logger.info(
                "Translation plan paused: budget spent with %d distinct texts left",
                len(representatives) - start,
            )
            break
        batch = representatives[start : start + width]
        with ThreadPoolExecutor(max_workers=width) as pool:
            answers = list(pool.map(lambda task: _ask(task, provider), batch))
        for answer in answers:
            siblings = by_text[(answer.task.source_hash, answer.task.target_locale)]
            for task in siblings:
                # Same answer, recorded against each row that asked for
                # it — which is also how two quizzes end up agreeing on
                # what "True" is in German.
                outcome = _record(
                    db,
                    _Answer(
                        task=task,
                        text=answer.text,
                        issues_summary=answer.issues_summary,
                        failed=answer.failed,
                    ),
                    store,
                )
                if outcome == "translated":
                    translated += 1
                elif outcome == "needs_review":
                    needs_review += 1
                elif outcome == "failed":
                    failed += 1

    return PlanResult(
        translated=translated,
        skipped=skipped,
        failed=failed,
        needs_review=needs_review,
        incomplete=incomplete,
    )


__all__ = ["DEFAULT_MAX_WORKERS", "PlanResult", "TranslationTask", "execute_plan"]
