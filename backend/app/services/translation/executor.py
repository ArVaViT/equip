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
finish, exactly as the serial path did. Since a long HTML block is
translated in several calls (``translation/html_split``), the check runs
inside a document too — the batch check authorises the first call, and
every call the split added asks again. A document that cannot be
finished is deferred: nothing is written for it, and the pass says so.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import or_

from app.models.content_version import ContentVersion, ContentVersionStatus
from app.services.translation.budget import NoBudget
from app.services.translation.protocol import (
    BudgetedTranslator,
    TranslationError,
    TranslationPaused,
    TranslationRequest,
    TranslationResult,
)
from app.services.translation.reviewer import ReviewVerdict, TranslationReviewer
from app.services.translation.validation import ValidationIssue, summarise, validate_translation
from app.services.translation.version import TRANSLATOR_VERSION

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.content_version import ContentVersionField as TranslationField
    from app.schemas.locale import LocaleCode
    from app.services.translation.budget import TranslationBudget
    from app.services.translation.protocol import ContentKind, EntityType, TranslationProvider
    from app.services.translation.stores import ActiveRow, VersionStore

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
    #: The clock ran out part-way through a document that takes several
    #: calls. Not a failure of the text and not an answer — nothing is
    #: written, and the pass reports itself incomplete so the next tick
    #: starts this document again with a full allowance.
    deferred: bool = False


def _translate(
    provider: TranslationProvider,
    request: TranslationRequest,
    budget: TranslationBudget | None,
) -> TranslationResult:
    """Ask the provider, telling it about the clock if it can hear.

    A long HTML block is translated in several calls, and a provider
    that spends more than one call on a request needs to know when to
    stop. Providers that do not — every fake in the suite, the noop —
    are called exactly as before. Same shape as the reviewer capability
    in ``_review_and_correct``: asked for by a distinct method name, not
    by a keyword, because a ``runtime_checkable`` Protocol only checks
    that the name is there.
    """
    if isinstance(provider, BudgetedTranslator):
        return provider.translate_within(request, budget=budget)
    return provider.translate(request)


def _decide(
    task: TranslationTask,
    existing: ActiveRow | None,
    twins: dict[tuple[str, str], str],
) -> tuple[Outcome, str | None] | None:
    """Is this task already answered? Returns the settled outcome, plus
    the text to record when a twin supplies one — or ``None`` when the
    provider has to be asked.

    Pure: everything the database could say has already been said, in
    two queries for the whole plan rather than two per task. That is not
    an optimisation detail — at three thousand tasks the per-task
    version spent the worker's entire budget deciding and never reached
    the asking.

    Identical rules to the serial path, in the same order, because they
    are the rules and not an implementation detail: a human translation
    is never overwritten, an up-to-date row is not re-asked, a row
    parked for review moves only when its source changes, a row that
    exhausted its retries is terminal — and a row made by an older
    pipeline is none of those things, however unchanged its source is.
    """
    if existing is not None:
        if existing.origin == "human":
            return "skipped", None
        # A row made by an older pipeline is not up to date. This is the
        # whole mechanism by which a prompt improvement reaches the
        # thousands of translations already stored: they stop counting
        # as answers. See ``translation/version.py``.
        current = existing.translator_version >= TRANSLATOR_VERSION
        if current and existing.status == "ok" and existing.source_hash == task.source_hash:
            return "skipped", None
        if current and existing.status == "needs_review" and existing.source_hash == task.source_hash:
            return "skipped", None
        if existing.status == "failed_permanent":
            # Terminal regardless of version: something about this text
            # defeats translation, and a new prompt is not a reason to
            # spend the retries again automatically.
            return "skipped", None

    # Identical source, already translated somewhere else: reuse it
    # rather than pay again, and gain consistency between an answer
    # option and its twin in another quiz as a side effect.
    twin = twins.get((task.source_hash, task.target_locale))
    if twin is not None:
        return "translated", twin
    return None


def _load_twins(
    db: Session,
    tasks: list[TranslationTask],
) -> dict[tuple[str, str], str]:
    """One usable translation per (source text, language), for the whole plan.

    "Usable" means human, or machine made by the pipeline now in force —
    an older machine wording is exactly what we are here to replace, and
    copying it around would spread the thing being fixed.
    """
    wanted = {(task.source_hash, task.target_locale) for task in tasks}
    if not wanted:
        return {}
    hashes = sorted({source_hash for source_hash, _ in wanted})
    locales = sorted({locale for _, locale in wanted})
    found: dict[tuple[str, str], str] = {}
    chunk = 500
    for start in range(0, len(hashes), chunk):
        rows = (
            db.query(
                ContentVersion.source_hash,
                ContentVersion.locale,
                ContentVersion.text,
            )
            .filter(
                ContentVersion.source_hash.in_(hashes[start : start + chunk]),
                ContentVersion.locale.in_(locales),
                ContentVersion.status == ContentVersionStatus.OK,
                ContentVersion.superseded_by.is_(None),
                or_(
                    ContentVersion.origin == "human",
                    ContentVersion.translator_version >= TRANSLATOR_VERSION,
                ),
            )
            .order_by(ContentVersion.created_at)
            .all()
        )
        for source_hash, locale, text in rows:
            found.setdefault((source_hash, locale), text)
    return {key: value for key, value in found.items() if key in wanted}


def _ask(task: TranslationTask, provider: TranslationProvider, budget: TranslationBudget | None = None) -> _Answer:
    """Phase two, and the only phase that runs off the main thread.

    Touches no database and no shared state: the provider owns an
    httpx client that is safe to share, and the validator is pure.

    The one retry on a failed structural check lives here because it is
    part of asking, not of recording — see the orchestrator's note on
    why a first bad answer is usually a bad roll rather than a fact.

    ``budget`` is optional because most callers of this function have no
    clock: the synchronous paths and the tests translate one field with
    nothing waiting on them. ``None`` means "as many calls as it takes".
    """
    request = TranslationRequest(
        text=task.text,
        source_locale=task.source_locale,
        target_locale=task.target_locale,
        content_kind=task.content_kind,
        context=task.context,
    )
    try:
        result = _translate(provider, request, budget)
    except TranslationPaused as exc:
        # The document is long enough to need several calls and the
        # allowance ran out between them. Nothing is recorded: half a
        # lesson in the reader's language and half in the author's is
        # worse than the gap, and the next tick will start it again from
        # the top for free.
        logger.info(
            "translation_deferred entity=%s:%s field=%s locale=%s reason=%s",
            task.entity_type,
            task.entity_id,
            task.field,
            task.target_locale,
            exc,
        )
        return _Answer(task=task, text=None, issues_summary=None, failed=False, deferred=True)
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

    issues = _issues_in(task, result)
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
            retry = _translate(
                provider, replace(request, rewrite_notes=tuple(issue.detail for issue in issues)), budget
            )
        except (TranslationError, TranslationPaused):
            retry = None
        if retry is not None:
            retry_issues = _issues_in(task, retry)
            # Keep whichever answer is less wrong. The model is not
            # deterministic, so a second pass is a second roll, not a
            # correction — and a retry that fixed the calque but broke a
            # placeholder must not be preferred to the first answer.
            if _rank(retry_issues) < _rank(issues):
                result, issues = retry, retry_issues

    # Structure is settled; now somebody reads it.
    #
    # Every check above asks whether the shape survived. None of them
    # reads the sentence, which is why a passage calling the Ethiopian
    # eunuch a Pentecostal sat in production marked ok. A second model
    # reads the source and the answer together and objects the way an
    # editor would, and what it objects to goes back through the same
    # correction loop — the translator is shown the notes and asked
    # again.
    #
    # Only when nothing structural is outstanding: a reply that lost its
    # markup does not need an opinion on its register, and paying for
    # one would be paying twice for the same rejection.
    if not issues:
        result, issues = _review_and_correct(task, result, provider, request, budget)

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


def _review_and_correct(
    task: TranslationTask,
    result: TranslationResult,
    provider: TranslationProvider,
    request: TranslationRequest,
    budget: TranslationBudget | None,
) -> tuple[TranslationResult, list[ValidationIssue]]:
    """Have the answer read, and act on what the reader says.

    One review, one correction, one re-review, then a person. The bound
    is the point: a loop that keeps going until a reviewer is happy will
    spend a budget arguing about a synonym, and a reviewer that objects
    to everything would put the whole catalogue in front of a human —
    which is the situation this pipeline exists to end.

    A reviewer that cannot be reached, cannot be parsed, or rejects
    without saying why returns no opinion, and no opinion changes
    nothing. This layer can only raise the floor; it must never be a new
    way for the pipeline to fail.
    """
    reviewer = provider if isinstance(provider, TranslationReviewer) else None
    if reviewer is None:
        return result, []

    verdict = reviewer.review(
        source=task.text,
        translation=result.text,
        source_locale=task.source_locale,
        target_locale=task.target_locale,
        content_kind=task.content_kind,
        context=task.context,
    )
    if not verdict.has_objections:
        return result, []

    try:
        corrected = _translate(provider, replace(request, rewrite_notes=verdict.notes), budget)
    except (TranslationError, TranslationPaused):
        corrected = None

    if corrected is None:
        return result, _from_review(verdict)

    # The corrected answer has to clear the structural checks on its own
    # merits — a fix for register that drops a placeholder is not a fix.
    corrected_issues = _issues_in(task, corrected)
    if corrected_issues:
        return result, _from_review(verdict)

    second = reviewer.review(
        source=task.text,
        translation=corrected.text,
        source_locale=task.source_locale,
        target_locale=task.target_locale,
        content_kind=task.content_kind,
        context=task.context,
    )
    if not second.has_objections:
        logger.info(
            "review_corrected entity=%s:%s field=%s locale=%s",
            task.entity_type,
            task.entity_id,
            task.field,
            task.target_locale,
        )
        return corrected, []

    # Still objected to after a correction. Served anyway — the reviewer
    # is an opinion, not a structural fact, and an editor's second
    # thoughts are not worth a blank page to a student — but recorded so
    # the rate is visible and the row can be read by a person.
    return corrected, _from_review(second)


def _from_review(verdict: ReviewVerdict) -> list[ValidationIssue]:
    return [
        ValidationIssue(
            code="review_objection",
            detail=" ".join(verdict.notes),
            blocking=False,
        )
    ]


def _issues_in(task: TranslationTask, result: TranslationResult) -> list[ValidationIssue]:
    """Everything wrong with this answer — structural, stylistic, and one
    thing only the provider can see.

    ``lost_scripture`` cannot be found by comparing source to
    translation: the provider swaps a quoted verse for a placeholder and
    restores the canonical text afterwards, so neither the text we sent
    nor the text we got back contains a marker. When the model drops the
    placeholder the verse is silently deleted and the reference is left
    behind, which reads as complete. The provider says so; this is where
    it becomes a defect like any other, and it is blocking — a student
    asked to recognise a verse must not be shown a citation with nothing
    behind it.
    """
    issues = validate_translation(
        source=task.text,
        translated=result.text,
        source_locale=task.source_locale,
        target_locale=task.target_locale,
        content_kind=task.content_kind,
    )
    if result.lost_scripture:
        issues.insert(
            0,
            ValidationIssue(
                code="scripture_dropped",
                detail=(
                    "The quoted Scripture was left out of the translation. "
                    "A verse handed to you as a VERSE_ placeholder must come "
                    "back exactly as it was given, in the same position."
                ),
            ),
        )
    return issues


def _rank(issues: list[ValidationIssue]) -> tuple[int, int]:
    """How bad a set of issues is: blocking defects first, then style."""
    return (
        sum(1 for issue in issues if issue.blocking),
        sum(1 for issue in issues if not issue.blocking),
    )


def _collides_with_a_sibling_option(db: Session, task: TranslationTask, text: str) -> bool:
    """Has this option become a copy of another option of the same question?

    The one defect a per-string check cannot see, because nothing is
    wrong with the string. Told what question it answers, the model
    helpfully repairs the wrong answers: measured across the corpus, 22
    questions came back with two identical options — four English
    options all reading "Malta", three all reading "John" — and every
    one of those questions is unanswerable. The Russian source has no
    duplicate options anywhere in 128 questions, so every collision was
    made in translation.

    The prompt now says twice that a wrong answer is wrong on purpose,
    and that stopped it in every case measured. This is the check behind
    the instruction, because an instruction is a hope and a quiz that
    cannot be answered is worse than a quiz with a clumsy sentence in
    it.
    """
    if task.entity_type not in ("quiz_option", "daily_challenge_option"):
        return False
    stripped = " ".join(text.split()).casefold()
    if not stripped:
        return False

    if task.entity_type == "quiz_option":
        from app.models.quiz import QuizOption as Option
    else:
        from app.models.daily_challenge import DailyChallengeOption as Option  # type: ignore[assignment]

    question_id = db.query(Option.question_id).filter(Option.id == _as_uuid(task.entity_id)).scalar()
    if question_id is None:
        return False
    sibling_ids = [
        str(row[0])
        for row in db.query(Option.id).filter(
            Option.question_id == question_id,
            Option.id != _as_uuid(task.entity_id),
        )
    ]
    if not sibling_ids:
        return False

    rows = db.query(ContentVersion.text).filter(
        ContentVersion.entity_type == task.entity_type,
        ContentVersion.entity_id.in_(sibling_ids),
        ContentVersion.field == task.field,
        ContentVersion.locale == task.target_locale,
        ContentVersion.superseded_by.is_(None),
    )
    return any(" ".join((row[0] or "").split()).casefold() == stripped for row in rows)


def _as_uuid(value: str) -> Any:
    """Option ids are uuids; the task carries them as text."""
    import uuid as _uuid

    try:
        return _uuid.UUID(value)
    except (ValueError, AttributeError):
        return value


def _record(db: Session, answer: _Answer, store: VersionStore) -> Outcome:
    """Phase three: back on the caller's session, one write at a time."""
    task = answer.task
    if answer.deferred:
        # Nothing to write. The row keeps whatever it had — which for a
        # first translation is nothing at all, and that is the point: a
        # partial document must never reach the reader.
        return "deferred"
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

    twin_of_a_sibling = _collides_with_a_sibling_option(db, task, answer.text)
    if twin_of_a_sibling:
        logger.warning(
            "option_collision entity=%s locale=%s text=%r",
            task.entity_id,
            task.target_locale,
            answer.text[:60],
        )

    parked = answer.issues_summary is not None or twin_of_a_sibling
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
        review_reason=(
            answer.issues_summary
            or (
                "[option_collision] This answer option is now word for word "
                "identical to another option of the same question. A quiz "
                "whose wrong answers have been turned into the right one "
                "cannot be answered."
                if twin_of_a_sibling
                else None
            )
        ),
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

    # Phase 1 — everything the database can answer without asking anyone,
    # read in two queries for the entire plan. Per-task reads were what
    # made a full-catalogue pass burn its whole budget on deciding.
    existing_rows = store.active_rows(
        db,
        [(task.entity_type, task.entity_id, task.field, task.target_locale) for task in tasks],
    )
    twins = _load_twins(db, tasks)

    pending: list[TranslationTask] = []
    for task in tasks:
        settled = _decide(
            task,
            existing_rows.get((task.entity_type, task.entity_id, task.field, task.target_locale)),
            twins,
        )
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
    #
    # The key carries the content kind and the context as well as the
    # text, because those change the question being asked. A sentence
    # sent as ``html`` is told to preserve markup; the same sentence sent
    # as ``quiz_option`` is told not to grow into a paragraph. Grouping
    # on the text alone let the first task's kind answer for both, and
    # the second row was written having never been checked under its own
    # rules — validation runs once, on the representative.
    by_text: dict[tuple[str, str, str, str | None], list[TranslationTask]] = {}
    for task in pending:
        by_text.setdefault(
            (task.source_hash, task.target_locale, task.content_kind, task.context),
            [],
        ).append(task)
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
            answers = list(pool.map(lambda task: _ask(task, provider, active_budget), batch))
        for answer in answers:
            siblings = by_text[
                (
                    answer.task.source_hash,
                    answer.task.target_locale,
                    answer.task.content_kind,
                    answer.task.context,
                )
            ]
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
                        deferred=answer.deferred,
                    ),
                    store,
                )
                if outcome == "translated":
                    translated += 1
                elif outcome == "needs_review":
                    needs_review += 1
                elif outcome == "failed":
                    failed += 1
                elif outcome == "deferred":
                    # A document too long to finish in what was left of
                    # the tick. The pass is not complete, so the job goes
                    # back to ``queued`` rather than being taken as done
                    # with a hole in it.
                    incomplete = True

    return PlanResult(
        translated=translated,
        skipped=skipped,
        failed=failed,
        needs_review=needs_review,
        incomplete=incomplete,
    )


__all__ = ["DEFAULT_MAX_WORKERS", "PlanResult", "TranslationTask", "execute_plan"]
