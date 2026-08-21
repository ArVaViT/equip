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
    TranslationUnavailable,
)
from app.services.translation.reviewer import ReviewVerdict, TranslationReviewer
from app.services.translation.term_memory import TermMemory
from app.services.translation.validation import ValidationIssue, summarise, validate_translation
from app.services.translation.version import TRANSLATOR_VERSION

if TYPE_CHECKING:
    from collections.abc import Container

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

# How many already-finished fields per language the term memory is
# seeded from at the start of a pass. Reading one costs about a
# millisecond, and a full-catalogue plan holds three thousand — three
# seconds of the worker's 180 spent before a single call goes out, for a
# course that stopped introducing new names somewhere in module two.
#
# 300 is 0.3 seconds and more fields than any course we have. The sample
# is spread across the plan rather than taken off the front, so the cap
# costs coverage of *repetitions*, not of names.
_SEED_PAIRS_PER_LOCALE = 300

# How many calls in a row may come back "the provider could not answer"
# before the pass stops asking.
#
# The worker fires every minute and a full-catalogue plan is thousands
# of calls. On 2026-08-20 the prepaid balance ran out and the pipeline
# spent the next several hours sending every one of those calls into a
# hard 429 — nothing translated, nothing learned, and the retry that
# would have worked was the one made after somebody topped up.
#
# Three consecutive unanswered calls is not a coincidence, and at
# ``DEFAULT_MAX_WORKERS`` the first batch of a real outage produces
# eight of them. Stopping there turns a tick from thousands of doomed
# calls into at most one batch — and the pass reports itself
# incomplete, so the job goes back to ``queued`` exactly as it does
# when the clock runs out. The next tick tries again a minute later,
# which is the right amount of patience for an outage that may end at
# any moment and the reason this needs no timer, no table and no
# setting.
_OUTAGE_STREAK_LIMIT = 3

Outcome = Literal["translated", "skipped", "failed", "needs_review", "deferred", "unavailable"]


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
    #: The provider could not answer: a 429, a 5xx, a timeout, a balance
    #: that ran out. Set alongside ``failed`` — no text came back, and
    #: for every counter and every reader this is a failed field — but it
    #: is the reason the failure must not be counted against the row's
    #: five attempts. See ``TranslationUnavailable``.
    unavailable: bool = False


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
    *,
    generation: int,
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

    ``generation`` is the run's, decided once and passed in, not read
    from the constant here. Every task in a plan is judged against the
    same number, so a plan cannot decide that half its rows are current
    and half are stale — see ``execute_plan``.
    """
    if existing is not None:
        if existing.origin == "human":
            return "skipped", None
        # A row made by an older pipeline is not up to date. This is the
        # whole mechanism by which a prompt improvement reaches the
        # thousands of translations already stored: they stop counting
        # as answers. See ``translation/version.py``.
        current = existing.translator_version >= generation
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
    *,
    generation: int,
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
                    ContentVersion.translator_version >= generation,
                ),
            )
            .order_by(ContentVersion.created_at)
            .all()
        )
        for source_hash, locale, text in rows:
            found.setdefault((source_hash, locale), text)
    return {key: value for key, value in found.items() if key in wanted}


def _seed_memory(
    memory: TermMemory,
    tasks: list[TranslationTask],
    existing_rows: dict[tuple[str, str, str, str], ActiveRow],
    *,
    generation: int,
) -> None:
    """Teach the memory what this course has already been translated into.

    Zero queries. Every row it reads was fetched by phase one to answer
    "is this already done?", and the answer to that question happens to
    be the corpus this needs: a translation of a text the plan is holding
    in ``task.text``, which is an aligned pair by construction. That
    alignment is the whole reason the seed sits here rather than in its
    own bulk read — a second query would have to reconstruct which source
    produced which translation, and the executor already knows.

    Three conditions, and each of them is about not learning a lie:

    * ``source_hash`` must match the task. A row whose source has since
      been rewritten translates a sentence we no longer have, so the
      pairing would be against the wrong text.
    * ``status`` must be ``ok``. A row parked for review is a wording a
      person has not accepted, and this is a mechanism for spreading a
      wording everywhere.
    * The row must be human, or made by the pipeline now in force. An
      older machine wording is exactly what a re-translation exists to
      replace, and a memory seeded from it would carry the discarded
      generation into the new one — the same rule ``_load_twins`` keeps,
      for the same reason.

    Scope follows the plan, which for the worker is one course's tree
    (``course_pipeline.plan_course_tasks``) and for a teacher saving a
    block is that entity. Nothing else can get in: the keys come from the
    plan's own tasks, so another course's choices are not merely
    outranked, they are never read.

    Reading a pair costs about a millisecond of our own work — a regular
    expression over both texts and a comparison between the names it
    finds. That is nothing beside the 420 ms a provider call spends on a
    socket, and it is not nothing three thousand times over before the
    first call is made, which is why ``_SEED_PAIRS_PER_LOCALE`` exists.
    Past that many fields a course is repeating names rather than
    introducing them, and the sample is taken evenly across the plan
    instead of from the front, so a name that first appears in the last
    module is as likely to be seen as one in the first.
    """
    usable: dict[str, list[tuple[TranslationTask, str]]] = {}
    seen: set[tuple[str, str]] = set()
    for task in tasks:
        existing = existing_rows.get((task.entity_type, task.entity_id, task.field, task.target_locale))
        if existing is None or not existing.text:
            continue
        if existing.status != "ok" or existing.source_hash != task.source_hash:
            continue
        if existing.origin != "human" and existing.translator_version < generation:
            continue
        pair = (task.source_hash, task.target_locale)
        if pair in seen:
            continue
        seen.add(pair)
        usable.setdefault(task.target_locale, []).append((task, existing.text))

    for rows in usable.values():
        step = max(1, -(-len(rows) // _SEED_PAIRS_PER_LOCALE))
        for task, translation in rows[::step]:
            memory.learn(
                task.text,
                translation,
                source_locale=task.source_locale,
                target_locale=task.target_locale,
            )


def _ask(
    task: TranslationTask,
    provider: TranslationProvider,
    budget: TranslationBudget | None = None,
    *,
    term_memory: tuple[tuple[str, str], ...] = (),
) -> _Answer:
    """Phase two, and the only phase that runs off the main thread.

    Touches no database and no shared state: the provider owns an
    httpx client that is safe to share, and the validator is pure.

    The one retry on a failed structural check lives here because it is
    part of asking, not of recording — see the orchestrator's note on
    why a first bad answer is usually a bad roll rather than a fact.

    ``budget`` is optional because most callers of this function have no
    clock: the synchronous paths and the tests translate one field with
    nothing waiting on them. ``None`` means "as many calls as it takes".

    ``term_memory`` is read on the caller's thread and handed in already
    settled, because the memory object is written between batches and a
    worker thread must never touch it. Empty means the pass has learned
    nothing that this text could use, which is exactly what every field
    of a course nobody has translated yet gets.
    """
    request = TranslationRequest(
        text=task.text,
        source_locale=task.source_locale,
        target_locale=task.target_locale,
        content_kind=task.content_kind,
        context=task.context,
        term_memory=term_memory,
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
    except TranslationUnavailable as exc:
        # Caught before ``TranslationError`` because it is one — the
        # ordering here is the whole classification. Nothing came back,
        # so the field failed and is recorded as failed; what is
        # different is that the row's attempt counter does not move, and
        # so it can never reach ``failed_permanent`` on the strength of
        # an outage.
        logger.warning(
            "translation_unavailable entity=%s:%s field=%s locale=%s err=%s",
            task.entity_type,
            task.entity_id,
            task.field,
            task.target_locale,
            exc,
        )
        return _Answer(task=task, text=None, issues_summary=None, failed=True, unavailable=True)
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
    # Advisory issues are named, never argued with. See
    # ``ValidationIssue.advisory``: a complaint the model has already
    # heard and considered is not a reason to spend a second call, and
    # it must not be the reason the editorial reader below is skipped.
    actionable = [issue for issue in issues if not issue.advisory]
    if actionable:
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
                provider, replace(request, rewrite_notes=tuple(issue.detail for issue in actionable)), budget
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
                actionable = [issue for issue in issues if not issue.advisory]

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
    # one would be paying twice for the same rejection. Nothing
    # *structural*: a glossary note is advisory precisely because this
    # reader is better placed to judge it, so it must not be the thing
    # that keeps the row away from them.
    if not actionable:
        advisory = issues
        reviewed, issues = _review_and_correct(task, result, provider, request, budget)
        if reviewed is result:
            # The reader changed nothing, so what the register noticed
            # still describes this text. Carried through so the rate
            # stays countable — a number on a dashboard, not a verdict.
            issues = [*advisory, *issues]
        result = reviewed

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
    """How bad a set of issues is: blocking defects first, then style.

    Advisory issues are not counted. They are observations the pipeline
    has decided not to act on, and a tie-break that counted them would
    act on them by the back door — it would prefer the answer that used
    the register's word to the answer that was right to avoid it.
    """
    counted = [issue for issue in issues if not issue.advisory]
    return (
        sum(1 for issue in counted if issue.blocking),
        sum(1 for issue in counted if not issue.blocking),
    )


@dataclass(frozen=True, slots=True)
class _Collision:
    """Another option of the same question that already says exactly this.

    ``text`` is that option's translation — the wording the new one has to
    be told about, because a note that does not say what to differ from
    cannot be acted on. ``sibling_source`` is what the same option says in
    the author's language, and it is the evidence that the two were ever
    meant to be different; ``None`` when the pass cannot see it.
    """

    sibling_id: str
    text: str
    sibling_source: str | None


#: What a person is told when a collision survives. Also the ``detail`` of
#: the issue the ranking below weighs, so the same sentence explains the
#: parked row and decides the comparison.
_COLLISION_REVIEW_REASON = (
    "[option_collision] This answer option is now word for word "
    "identical to another option of the same question. A quiz "
    "whose wrong answers have been turned into the right one "
    "cannot be answered."
)

#: What the translator is told when a collision is found — the one thing
#: the pipeline never used to do with this defect.
#:
#: It names the constraint and stops. What has to change is a fact about
#: the pair ("these two are now the same string, and their sources are
#: not"), not a word: a note that proposed one would be this file
#: translating into Ukrainian, which it cannot do, and the model would
#: take the proposal whether or not it was the better rendering. Both
#: sources are quoted because the distinction to preserve is between
#: them, and the twin's translation because that is the string to be
#: unlike. Nothing here suggests a rendering.
#:
#: Measured against the live model on 2026-08-21, on the pair that put
#: the three rows in the review queue — "Understand it" and "Comprehend
#: it", one daily-challenge question, English source. Asked cold,
#: Ukrainian came back «Зрозуміти це» for both, which is the production
#: defect reproduced. Fourteen correcting asks across uk and de: twelve
#: came back distinct — «Осягніть це», «Усвідомте це», «Begreife es»,
#: «Erfasse es» — and two came back the identical string again, which is
#: why the park stays and why there is exactly one ask.
#:
#: The sentence about pronouns and endings was added because of what the
#: other rolls returned: «Зрозуміти його», distinct as a string and not
#: distinct as an answer. It did not fix that case — a note names a
#: constraint, it does not enforce one — and the check downstream only
#: ever promised that two options are not the same string. Naming it
#: costs nothing and it is what a reader would say.
_COLLISION_NOTE = (
    "[option_collision] Your translation of this answer option came back word for word "
    "identical to the translation already recorded for a different option of the same "
    "question, which is «{twin}». The two options do not say the same thing in "
    "{source_locale}: this one says «{source}» and the other says «{sibling_source}». A "
    "student has to be able to tell them apart, so translate this option again with a "
    "rendering that is distinguishable from «{twin}» and still says exactly what its own "
    "source says. A different pronoun, article, case ending or punctuation mark is not a "
    "distinction a student can act on: the two options have to read as different answers. "
    "Do not move it towards the meaning of the other option, do not add an explanation, "
    "and keep it the length of an answer option."
)


def _as_one_option_reads(text: str) -> str:
    """Two options a student cannot tell apart are the same option.

    Spacing and case are not a distinction on a multiple-choice list, so
    they are removed before anything is compared — a collision and the
    sameness of two sources are the same question asked twice.
    """
    return " ".join(text.split()).casefold()


def _collides_with_a_sibling_option(
    db: Session,
    task: TranslationTask,
    text: str,
    *,
    unsettled: Container[tuple[str, str, str, str]] = frozenset(),
) -> bool:
    """Has this option become a copy of another option of the same question?

    Yes or no, for every caller that only needs to know whether the row
    can be served. ``_colliding_sibling`` answers the same question and
    says which option and in what words, which is what a note back to the
    translator needs.
    """
    return _colliding_sibling(db, task, text, unsettled=unsettled) is not None


def _colliding_sibling(
    db: Session,
    task: TranslationTask,
    text: str,
    *,
    unsettled: Container[tuple[str, str, str, str]] = frozenset(),
) -> _Collision | None:
    """Which option of the same question this text has turned into, if any.

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

    ``unsettled`` is the part of this run's own plan that has not been
    written yet, keyed the way ``VersionStore.active_rows`` keys rows.
    A sibling in that set is not evidence of anything: this same run is
    about to replace its translation, and what it says in the meantime
    is last generation's answer — see the note on the query below.
    """
    if task.entity_type not in ("quiz_option", "daily_challenge_option"):
        return None
    stripped = _as_one_option_reads(text)
    if not stripped:
        return None

    if task.entity_type == "quiz_option":
        from app.models.quiz import QuizOption as Option
    else:
        from app.models.daily_challenge import DailyChallengeOption as Option  # type: ignore[assignment]

    question_id = db.query(Option.question_id).filter(Option.id == _as_uuid(task.entity_id)).scalar()
    if question_id is None:
        return None
    sibling_ids = [
        str(row[0])
        for row in db.query(Option.id).filter(
            Option.question_id == question_id,
            Option.id != _as_uuid(task.entity_id),
        )
    ]
    if not sibling_ids:
        return None

    # Only siblings this run is not about to rewrite.
    #
    # A rebuild replaces a question's options one at a time, so for a
    # while the set is half new and half old — and the old half is
    # exactly the broken one this check exists to catch. Comparing
    # against it parks the correct new translation for matching a wrong
    # old one: measured during the generation-8 rebuild, thirteen
    # perfectly good German options were held back because a sibling
    # still carried last generation's duplicate.
    #
    # That used to be expressed as "only siblings at the generation now
    # in force", and generation is the wrong question twice over. It is
    # a global that a deploy moves under a running pass, so the answer
    # depends on when the row happened to be written rather than on what
    # it says. And it goes blind as soon as the corpus catches up: once
    # a generation has been in force for a while, a sibling written by
    # an earlier pass at the same generation — one this pass is holding
    # a task for and will replace in a minute — satisfies
    # ``>= TRANSLATOR_VERSION`` and parks a correct translation anyway.
    # Nine rows in production are parked that way.
    #
    # The run already knows the real answer. A sibling still queued in
    # this plan is unsettled and says nothing; a sibling this run has
    # already written, or one no task of this plan covers, is the text a
    # reader would see and counts. Human rows count for free: nothing
    # re-translates them, so they are never in the plan.
    sibling_ids = [
        sibling_id
        for sibling_id in sibling_ids
        if (task.entity_type, sibling_id, task.field, task.target_locale) not in unsettled
    ]
    if not sibling_ids:
        return None

    rows = db.query(ContentVersion.entity_id, ContentVersion.text).filter(
        ContentVersion.entity_type == task.entity_type,
        ContentVersion.entity_id.in_(sibling_ids),
        ContentVersion.field == task.field,
        ContentVersion.locale == task.target_locale,
        ContentVersion.superseded_by.is_(None),
    )
    for sibling_id, sibling_text in rows:
        if _as_one_option_reads(sibling_text or "") != stripped:
            continue
        return _Collision(
            sibling_id=str(sibling_id),
            text=sibling_text or "",
            sibling_source=_source_text_of(db, task, str(sibling_id)),
        )
    return None


def _source_text_of(db: Session, task: TranslationTask, sibling_id: str) -> str | None:
    """What a sibling option says in the author's language.

    Read only when a collision has already been found — three rows in the
    whole production corpus — so the check keeps the single query it has
    always cost, and the second one is paid for by the defect.

    ``None`` means the pass cannot see the sibling's source at all, and
    that is the case where it must not argue: with nothing to compare,
    "these two options are meant to differ" is an assumption, and a
    question whose source really does list the same answer twice is
    broken upstream of anything a translator can fix.
    """
    return (
        db.query(ContentVersion.text)
        .filter(
            ContentVersion.entity_type == task.entity_type,
            ContentVersion.entity_id == sibling_id,
            ContentVersion.field == task.field,
            ContentVersion.locale == task.source_locale,
            ContentVersion.superseded_by.is_(None),
        )
        .scalar()
    )


def _as_uuid(value: str) -> Any:
    """Option ids are uuids; the task carries them as text."""
    import uuid as _uuid

    try:
        return _uuid.UUID(value)
    except (ValueError, AttributeError):
        return value


def _ask_again_for_a_distinct_option(
    db: Session,
    task: TranslationTask,
    text: str,
    collision: _Collision,
    provider: TranslationProvider,
    budget: TranslationBudget | None,
    *,
    unsettled: Container[tuple[str, str, str, str]] = frozenset(),
) -> tuple[str, _Collision | None]:
    """Tell the translator its two options came out the same, and ask once
    more. Returns the wording to write and the collision that survives it.

    The pipeline already had the mechanism and never pointed it at this
    defect: ``_review_and_correct`` sends an objection back as
    ``rewrite_notes`` and asks again, and a collision is the most
    actionable objection there is — it is a fact about two strings, not
    an opinion about one. Ukrainian tells «Understand it» from
    «Comprehend it» without difficulty; what happened in production is
    that nobody said there was anything to tell apart.

    **One ask.** The same bound as ``_review_and_correct``, for the same
    reason: a loop that keeps going until two strings differ can be fed
    a question whose source really does repeat itself and will spend a
    budget discovering that. So the note goes out once. What comes back
    is either better or it is not, and a collision that survives parks
    exactly as it parked before — going quiet would be worse than
    parking, because two identical options in a live quiz is the thing
    this whole check exists to catch.

    **Why a note and not a retry.** Sampling is at temperature 0, so
    asking the identical question again returns the identical answer
    (see the note in ``_ask``). The note is the only thing that can
    change the outcome, which is also why there is no point asking twice.

    **Which of the two rows moves.** The collision is symmetric — two
    options, one string — but the pass is not. ``unsettled`` means a
    sibling this run has still to write says nothing, so the option
    written first is never compared to the one still queued: only the
    later one is ever asked to change, and the earlier one is already on
    the page and stays as it is. Two rows cannot chase each other, in
    this pass or across passes, because the row that moves is always the
    one still in hand.

    **Not asked at all** in three cases. Two are decided here: the two
    sources say the same thing, or the sibling's source cannot be read
    at all — a question that lists one answer twice is broken where no
    translator can reach, and without the sibling's source that is a
    guess. The third is decided by the caller: a row already going to a
    person for a structural defect is parked either way, so the call
    would buy that person nothing.
    """
    if collision.sibling_source is None:
        return text, collision
    if _as_one_option_reads(collision.sibling_source) == _as_one_option_reads(task.text):
        # The two options are the same option in the author's language.
        # Nothing the model returns can make them differ without saying
        # something the source does not say, so this goes to a person as
        # it always did — and the reason it needs one is upstream.
        logger.warning(
            "option_collision_in_source entity=%s locale=%s",
            task.entity_id,
            task.target_locale,
        )
        return text, collision

    note = _COLLISION_NOTE.format(
        twin=collision.text,
        source=task.text,
        sibling_source=collision.sibling_source,
        source_locale=task.source_locale,
    )
    try:
        corrected = _translate(
            provider,
            TranslationRequest(
                text=task.text,
                source_locale=task.source_locale,
                target_locale=task.target_locale,
                content_kind=task.content_kind,
                context=task.context,
                rewrite_notes=(note,),
                # No term memory. It exists to make a course agree with
                # itself on what a word is called, and this ask is the
                # one place where agreeing with the wording already
                # recorded is the defect.
            ),
            budget,
        )
    except (TranslationError, TranslationPaused):
        # A correction that could not be made is not a verdict on the
        # text. The row parks with what it had, as before.
        return text, collision

    # Ranked, not accepted. A second answer is a second roll, and one
    # that stopped colliding by dropping a placeholder or answering in
    # the wrong language is not a fix — ``_rank`` already knows how to
    # weigh that, and the collision is handed to it as the blocking
    # issue it is so that the answer which gave in to its neighbour
    # cannot win by being tidy. The incumbent's own structural issues
    # are not in the scale because there are none: a row that had any
    # was never sent here.
    #
    # Two consequences worth naming. A candidate that still collides can
    # never beat an incumbent that only collides, because both carry the
    # same blocking issue and ties go to the incumbent. And a candidate
    # that wins has no blocking issue of its own — nothing else could
    # get it under ``(1, 0)`` — so the wording written below needs no
    # summary and no parking, which is why this returns text and
    # collision and nothing more.
    still = _colliding_sibling(db, task, corrected.text, unsettled=unsettled)
    candidate = _issues_in(task, corrected)
    if still is not None:
        candidate.append(_collision_issue())
    if _rank(candidate) >= _rank([_collision_issue()]):
        return text, collision

    logger.info(
        "option_collision_corrected entity=%s locale=%s was=%r now=%r",
        task.entity_id,
        task.target_locale,
        text[:60],
        corrected.text[:60],
    )
    return corrected.text, still


def _collision_issue() -> ValidationIssue:
    """A collision as something ``_rank`` can weigh: blocking, because a
    question a student cannot answer is not served, and not advisory,
    because the model has not heard this complaint before."""
    return ValidationIssue(code="option_collision", detail=_COLLISION_REVIEW_REASON, blocking=True)


def _record(
    db: Session,
    answer: _Answer,
    store: VersionStore,
    *,
    generation: int,
    unsettled: Container[tuple[str, str, str, str]] = frozenset(),
    provider: TranslationProvider | None = None,
    budget: TranslationBudget | None = None,
) -> Outcome:
    """Phase three: back on the caller's session, one write at a time.

    ``generation`` is stamped onto whatever is written. It is the run's
    number, fixed before the first call went out, so every row of a
    plan carries the pipeline that actually produced it.

    The one provider call this phase can make lives here: an answer
    option that came back a copy of its neighbour is asked again with a
    note saying so. It has to be here, because the collision is the one
    defect that cannot be seen without the database — phase two runs
    without one, deliberately. It costs the pass its concurrency for the
    length of one call, on a defect that is three rows in the production
    corpus, which is cheaper than routing the answer back into a thread
    pool that has already shut down. ``provider`` is optional so that
    every caller with nothing to ask — the tests that record a made-up
    answer — records exactly as it always did.
    """
    task = answer.task
    if answer.deferred:
        # Nothing to write. The row keeps whatever it had — which for a
        # first translation is nothing at all, and that is the point: a
        # partial document must never reach the reader.
        return "deferred"
    if answer.failed:
        # Recorded either way, and that is the point of recording it.
        #
        # The tempting alternative — write nothing when the provider is
        # down, the way a deferred document writes nothing — is how a
        # course stops being translated without anybody being told. The
        # row is what the retry queue and the sweep read; a failure that
        # leaves no trace leaves a first-ever translation with no row at
        # all, and the only thing that would come back for it is a
        # coincidence.
        #
        # So the row is written exactly as before — ``failed``, findable,
        # retried by the very next pass — and one thing is withheld: the
        # attempt. See ``record_mt_failure``'s ``transient``.
        store.record_failure(
            db,
            entity_type=task.entity_type,
            entity_id=task.entity_id,
            field=task.field,
            locale=task.target_locale,
            source_locale=task.source_locale,
            source_hash=task.source_hash,
            transient=answer.unavailable,
        )
        return "unavailable" if answer.unavailable else "failed"

    if answer.text is None:
        return "failed"

    text = answer.text
    collision = _colliding_sibling(db, task, text, unsettled=unsettled)
    if collision is not None and provider is not None and answer.issues_summary is None:
        text, collision = _ask_again_for_a_distinct_option(
            db, task, text, collision, provider, budget, unsettled=unsettled
        )
    twin_of_a_sibling = collision is not None
    if collision is not None:
        # Named, so a person opening the review queue can find the other
        # half of the pair without going looking for it.
        logger.warning(
            "option_collision entity=%s locale=%s twin=%s text=%r",
            task.entity_id,
            task.target_locale,
            collision.sibling_id,
            text[:60],
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
        text=text,
        source_locale=task.source_locale,
        source_hash=task.source_hash,
        status=ContentVersionStatus.NEEDS_REVIEW if parked else ContentVersionStatus.OK,
        review_reason=(answer.issues_summary or (_COLLISION_REVIEW_REASON if twin_of_a_sibling else None)),
        translator_version=generation,
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
    generation: int | None = None,
) -> PlanResult:
    """Decide, ask concurrently, record. Returns the same counters the
    serial path returned, so callers and tests read unchanged.

    One generation for the whole run, read once here.

    ``TRANSLATOR_VERSION`` is what makes a stored translation count as
    an answer, and every phase of a pass consults it: deciding what is
    already done, deciding which stored wording may be reused, seeding
    the term memory, and stamping each row that is written. Read at each
    point of use it is a moving target — a worker tick lasts up to 180
    seconds and the cron fires every minute, so ticks overlap, and a
    deploy that lands between two of them has one pass writing a
    question's options at the old number while another writes its
    siblings at the new one. Everything downstream that compares two
    rows by generation is then comparing rows that were never in
    competition.

    So the number is settled before the first call goes out and carried
    through the run. A pass that straddles a deploy finishes as the
    pipeline it started as, whole: the rows it writes after the deploy
    are below the new constant, which is exactly the state the
    reconciler sweep exists to find, so they are re-translated on a
    later tick. Half a batch stamped each way is the one outcome
    nothing can repair, because both halves look finished.

    ``generation`` is a parameter so a caller running several plans in
    one tick can hold them to one number; ``None`` means "whatever is in
    force as this run starts", which is what every caller wants today.
    """
    if not tasks:
        return PlanResult()

    run_generation = TRANSLATOR_VERSION if generation is None else generation
    active_budget = budget or NoBudget()
    translated = skipped = failed = needs_review = 0
    incomplete = False
    #: Consecutive asked texts the provider could not answer. Reset by
    #: any answer at all, including a bad one — a provider that is
    #: talking is not an outage. See ``_OUTAGE_STREAK_LIMIT``.
    unanswered_in_a_row = 0

    # Phase 1 — everything the database can answer without asking anyone,
    # read in two queries for the entire plan. Per-task reads were what
    # made a full-catalogue pass burn its whole budget on deciding.
    existing_rows = store.active_rows(
        db,
        [(task.entity_type, task.entity_id, task.field, task.target_locale) for task in tasks],
    )
    twins = _load_twins(db, tasks, generation=run_generation)

    # What this course has already decided to call things, built out of
    # the rows phase one just read. Nothing is asked of the database for
    # it — see ``_seed_memory`` — and on a course nobody has translated
    # yet it stays empty, so the pass below is the pass that has always
    # run.
    memory = TermMemory()
    _seed_memory(memory, tasks, existing_rows, generation=run_generation)

    pending: list[TranslationTask] = []
    for task in tasks:
        settled = _decide(
            task,
            existing_rows.get((task.entity_type, task.entity_id, task.field, task.target_locale)),
            twins,
            generation=run_generation,
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
                translator_version=run_generation,
            )
            translated += 1

    # What this run is going to write and has not written yet.
    #
    # Read by the answer-option collision check, which has to tell a
    # sibling that says something from a sibling that merely has not
    # been redone yet. A key leaves the set the moment its row is
    # written, so a collision made inside this very pass is still
    # caught — the option written second is checked against the option
    # written first, which is where the duplicate actually appears.
    #
    # The one thing this cannot see is another worker tick rebuilding
    # the same course at the same time: ticks overlap by design and a
    # second job for a course may be enqueued while the first is still
    # processing. That pass's pending set is its own. Narrower than
    # what it replaces, and the same for every generation.
    unsettled: set[tuple[str, str, str, str]] = {
        (task.entity_type, task.entity_id, task.field, task.target_locale) for task in pending
    }

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
    # The key carries the content kind as well as the text, because the
    # kind changes the question being asked. A sentence sent as ``html``
    # is told to preserve markup; the same sentence sent as
    # ``quiz_option`` is told not to grow into a paragraph. Grouping on
    # the text alone let the first task's kind answer for both, and the
    # second row was written having never been checked under its own
    # rules — validation runs once, on the representative.
    #
    # The context is deliberately NOT in the key, and that is a fix, not
    # an omission. It was in the key, and it is what made «Проверьте
    # себя» four different German headings: the heading is its own field,
    # its context is the paragraph above it, and that paragraph differs
    # in every lesson — so 23 identical strings landed in 23 groups and
    # were asked 23 times. Nothing downstream noticed, because each
    # answer was individually fine.
    #
    # The recorded behaviour was never context-sensitive either:
    # ``_load_twins`` answers by ``(source_hash, target_locale)`` alone,
    # so the same heading translated last week is reused this week no
    # matter what stands above it. Keeping context in the in-flight key
    # made one pass stricter than the pipeline it feeds, which is how a
    # rule meant to hold the catalogue together produced the divergence
    # instead. Context still reaches the model — the representative
    # carries its own — it just no longer decides who counts as the same
    # string. Validation does not read the context, so a sibling is
    # checked under the rules that apply to it.
    by_text: dict[tuple[str, str, str], list[TranslationTask]] = {}
    for task in pending:
        by_text.setdefault(
            (task.source_hash, task.target_locale, task.content_kind),
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
        # Read the memory here, on this thread, and hand each call the
        # pairs it can use. The batch is the granularity at which the
        # memory moves: eight calls are in flight together and none of
        # them can see the others, which is the same trade the executor
        # already makes everywhere else and for the same reason.
        prepared = [(task, memory.recall(task.text, target_locale=task.target_locale)) for task in batch]
        with ThreadPoolExecutor(max_workers=width) as pool:
            answers = list(
                pool.map(
                    lambda prepared_task: _ask(prepared_task[0], provider, active_budget, term_memory=prepared_task[1]),
                    prepared,
                )
            )
        for answer in answers:
            # Only the representatives are asked, so only they say
            # anything about whether the provider is answering. A sibling
            # inherits the verdict without a call of its own and must not
            # inflate the streak.
            unanswered_in_a_row = unanswered_in_a_row + 1 if answer.unavailable else 0
            if answer.text is not None and not answer.failed and not answer.deferred and answer.issues_summary is None:
                # Learn only from answers nothing objected to. A row
                # parked for review is a wording waiting for a person,
                # and copying it into every later field would be the
                # pipeline agreeing with itself about something it has
                # already flagged.
                memory.learn(
                    answer.task.text,
                    answer.text,
                    source_locale=answer.task.source_locale,
                    target_locale=answer.task.target_locale,
                )
            siblings = by_text[
                (
                    answer.task.source_hash,
                    answer.task.target_locale,
                    answer.task.content_kind,
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
                        unavailable=answer.unavailable,
                    ),
                    store,
                    generation=run_generation,
                    unsettled=unsettled,
                    provider=provider,
                    budget=active_budget,
                )
                if outcome in ("translated", "needs_review"):
                    # Written, so it is now what a reader sees and the
                    # next option of this question is judged against it.
                    unsettled.discard((task.entity_type, task.entity_id, task.field, task.target_locale))
                if outcome == "translated":
                    translated += 1
                elif outcome == "needs_review":
                    needs_review += 1
                elif outcome in ("failed", "unavailable"):
                    # Counted together, because for everything that reads
                    # this number they are the same thing: a field that
                    # was supposed to get text and did not. The
                    # difference lives in the row, where the attempt
                    # counter is, and nowhere else — which is also what
                    # keeps ``made_progress`` true through an outage, so
                    # the *job* does not spend its own attempts either.
                    failed += 1

                elif outcome == "deferred":
                    # A document too long to finish in what was left of
                    # the tick. The pass is not complete, so the job goes
                    # back to ``queued`` rather than being taken as done
                    # with a hole in it.
                    incomplete = True

        if unanswered_in_a_row >= _OUTAGE_STREAK_LIMIT:
            # Nobody is on the other end. Stop asking for the rest of
            # this tick rather than walking the remaining thousands of
            # texts into the same wall — and say the pass is incomplete,
            # which sends the job back to ``queued`` for a fresh try in a
            # minute. Everything already recorded stands.
            incomplete = True
            logger.error(
                "Translation plan halted: provider unavailable for %d calls in a row, %d distinct texts left",
                unanswered_in_a_row,
                max(0, len(representatives) - (start + width)),
            )
            break

    return PlanResult(
        translated=translated,
        skipped=skipped,
        failed=failed,
        needs_review=needs_review,
        incomplete=incomplete,
    )


__all__ = ["DEFAULT_MAX_WORKERS", "PlanResult", "TranslationTask", "execute_plan"]
