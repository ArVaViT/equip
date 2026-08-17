"""Domain-level translation orchestrator.

The provider in ``app.services.translation.gemini`` only knows how to turn a
single chunk of text into another chunk of text. This module wraps that
primitive with the persistence + idempotency rules the rest of the app needs:

* Look up the existing ``content_translations`` row (if any) for the
  ``(entity_type, entity_id, field, locale)`` tuple.
* Skip the call when the source text is unchanged (``source_hash`` match)
  and the row is already ``status='ok'``.
* Never overwrite a ``origin='human'`` row — those are manual overrides.
* Persist a ``status='failed'`` row when a provider call raises, so the
  failed-rows queue UI (Wave 2 follow-up) can find them.

Caller responsibilities:
* Pass canonical, sanitized source text. The orchestrator does **not**
  re-sanitize HTML — that already happened at the model edge.
* Decide which target locales to translate into. The default helper
  ``other_locales`` covers the common case (everything except the source).

Public surface kept intentionally small (one function per concern) so the
``draft → published`` hook reads as plain English at the call site.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from app.models.content_version import ContentVersion, ContentVersionStatus
from app.schemas.locale import LOCALE_CODES, LocaleCode, normalize_locale
from app.services.translation.budget import NoBudget, TranslationBudget
from app.services.translation.hash import compute_source_hash
from app.services.translation.protocol import (
    ContentKind,
    TranslationError,
    TranslationProvider,
    TranslationRequest,
)
from app.services.translation.service import (
    get_translation_provider,
    is_translation_enabled,
)
from app.services.translation.stores import LIVE_STORE, VersionStore
from app.services.translation.validation import summarise, validate_translation

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.content_version import (
        ContentVersionEntityType as TranslationEntityType,
    )
    from app.models.content_version import (
        ContentVersionField as TranslationField,
    )
    from app.models.course import Course

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TranslationFieldSpec:
    """One ``(field, text, content_kind)`` tuple to translate.

    ``text`` is allowed to be empty / ``None``; the orchestrator skips those
    rows so the caller can build the spec list naively without filtering.

    ``source_locale`` is an OPTIONAL per-field override of the
    entity-level source locale. When set, this field's translation
    fires from this language into every OTHER supported locale —
    regardless of the entity-level ``source_locale`` passed to
    ``translate_entity_fields``. Callers populate it from a
    per-field language detector (see ``reconcile_entity``) so an
    entity whose title is in one language and description in another
    gets each field translated in the correct direction.
    """

    field: TranslationField
    text: str | None
    # See ``TranslationRequest.content_kind`` — chooses prompt nuances.
    content_kind: ContentKind = "plain"
    source_locale: LocaleCode | None = None


@dataclass(frozen=True, slots=True)
class OrchestratorReport:
    """Lightweight summary returned to the caller.

    Useful both in tests and in admin endpoints that surface a quick "X
    fields translated, Y skipped" toast in the UI.

    ``needs_review`` counts rows where the provider answered but the
    answer failed the structural check — text stored, not servable.
    They are counted apart from ``failed`` because the two need
    different work: a failure is retried, a review is read.

    ``incomplete`` means the pass stopped early because its time budget
    ran out, not because it finished. Whatever it did translate is
    committed; what remains is still there to do. The worker reads this
    to decide whether the job is done or merely paused — see
    ``translation/budget.py`` for why that distinction is the whole
    difference between a large course and a broken one.
    """

    translated: int = 0
    skipped: int = 0
    failed: int = 0
    needs_review: int = 0
    incomplete: bool = False

    @property
    def made_progress(self) -> bool:
        """Did this pass move anything at all?

        A tick that translated, parked for review, or even recorded a
        failure has advanced the course's state and earns another tick
        without spending an attempt. A tick that only skipped — or did
        nothing — has not.
        """
        return bool(self.translated or self.needs_review or self.failed)


def other_locales(source_locale: LocaleCode) -> tuple[LocaleCode, ...]:
    """Return every supported locale other than ``source_locale``.

    Wrapped in a function (not a constant) because adding a new locale to
    ``LOCALE_CODES`` should automatically extend this tuple — see
    ``app/schemas/locale.py`` for the three-step language-rollout checklist.
    """
    return tuple(code for code in LOCALE_CODES if code != source_locale)


def translate_entity_fields(
    db: Session,
    *,
    entity_type: TranslationEntityType,
    entity_id: str,
    source_locale: LocaleCode,
    fields: list[TranslationFieldSpec],
    target_locales: tuple[LocaleCode, ...] | None = None,
    context: str | None = None,
    provider: TranslationProvider | None = None,
    budget: TranslationBudget | None = None,
    store: VersionStore | None = None,
) -> OrchestratorReport:
    """Translate ``fields`` of ``(entity_type, entity_id)`` into each target.

    Returns a per-call summary. Never raises for ordinary translation
    failures — those become ``status='failed'`` rows. Re-raises only on
    SQLAlchemy errors, which surface bugs that the caller does want to see.

    ``budget`` bounds how long the pass may run. When it runs out the
    loop stops at the next field that would need a provider call, and
    the report comes back ``incomplete``; the caller commits what was
    done and picks the rest up later. Callers with no deadline — a
    teacher saving one block, a test, an admin retry — pass nothing.

    ``store`` decides where the results land: ``content_versions``
    (the default, servable at once) or the staging table, for an edit
    to a course students are currently reading. See
    ``translation/stores.py``.
    """
    if not is_translation_enabled():
        # Don't burn DB writes when there's no real provider configured;
        # the noop fallback would just echo the source text back.
        logger.info("Translation disabled; skipping %s:%s", entity_type, entity_id)
        return OrchestratorReport()

    # ``target_locales`` is a caller override for the entire batch.
    # When unset (the common case), each field computes its own targets
    # from its own ``source_locale`` (per-field detection in
    # ``reconcile_entity``) — that's what makes mixed-language entities
    # translate in the correct direction per field.
    active_provider = provider or get_translation_provider()
    active_budget = budget or NoBudget()
    active_store = store or LIVE_STORE
    translated = 0
    skipped = 0
    failed = 0
    needs_review = 0
    incomplete = False

    for spec in fields:
        if incomplete:
            break
        text = (spec.text or "").strip()
        if not text:
            # Empty source has nothing to translate; we also actively avoid
            # creating empty translation rows that would later round-trip
            # back into the UI as blanks. Empty-source fields are not
            # counted in ``skipped`` — that counter tracks rows we
            # *consciously* short-circuited (human override, hash match),
            # not rows that never had work to do.
            continue

        # Per-field source-locale override (set by ``reconcile_entity``
        # after running the language detector on this field's text).
        # Falls back to the entity-level source_locale when unset, which
        # preserves the existing single-language behaviour for callers
        # that haven't opted into per-field detection.
        field_source: LocaleCode = spec.source_locale or source_locale
        field_targets = target_locales if target_locales is not None else other_locales(field_source)
        if not field_targets:
            continue
        source_hash = compute_source_hash(text, locale=field_source)
        for target in field_targets:
            outcome = _translate_one_field(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                field=spec.field,
                source_locale=field_source,
                target_locale=target,
                text=text,
                content_kind=spec.content_kind,
                source_hash=source_hash,
                context=context,
                provider=active_provider,
                budget=active_budget,
                store=active_store,
            )
            if outcome == "translated":
                translated += 1
            elif outcome == "skipped":
                skipped += 1
            elif outcome == "needs_review":
                needs_review += 1
            elif outcome == "deferred":
                # Out of time, and this row would have needed a provider
                # call. Stop here rather than walking the rest of the
                # fields for their short-circuits: the cheap ones cost a
                # query each, and on a large course that is thousands of
                # queries buying nothing. The next tick starts where this
                # one stopped, for free, because the fields already done
                # match on ``source_hash``.
                incomplete = True
                break
            else:
                failed += 1

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    logger.info(
        "Translation orchestrator finished entity=%s:%s translated=%d skipped=%d failed=%d "
        "needs_review=%d incomplete=%s",
        entity_type,
        entity_id,
        translated,
        skipped,
        failed,
        needs_review,
        incomplete,
    )
    return OrchestratorReport(
        translated=translated,
        skipped=skipped,
        failed=failed,
        needs_review=needs_review,
        incomplete=incomplete,
    )


def translate_course_metadata(
    db: Session,
    course: Course,
    *,
    provider: TranslationProvider | None = None,
) -> OrchestratorReport:
    """Translate ``title`` + ``description`` for a course into every other locale.

    Full-tree translation (modules, chapters, blocks, quizzes) lives in
    ``course_pipeline.translate_course_content``, which calls this helper first.
    """
    fields: list[TranslationFieldSpec] = [
        TranslationFieldSpec(field="title", text=course.title, content_kind="title"),
        TranslationFieldSpec(field="description", text=course.description, content_kind="plain"),
    ]
    source_locale: LocaleCode = normalize_locale(course.source_locale)
    return translate_entity_fields(
        db,
        entity_type="course",
        entity_id=str(course.id),
        source_locale=source_locale,
        fields=fields,
        context=f"Course title: {course.title}" if course.title else None,
        provider=provider,
    )


def _translate_one_field(
    db: Session,
    *,
    entity_type: TranslationEntityType,
    entity_id: str,
    field: TranslationField,
    source_locale: LocaleCode,
    target_locale: LocaleCode,
    text: str,
    content_kind: ContentKind,
    source_hash: str,
    context: str | None,
    provider: TranslationProvider,
    budget: TranslationBudget,
    store: VersionStore,
) -> str:
    """Translate (or up-to-date short-circuit) one ``(field, target)`` row.

    Returns ``"translated" | "skipped" | "failed" | "deferred"`` so the
    orchestrator can aggregate counters without inspecting the DB row
    again. ``"deferred"`` means this row needs a provider call and the
    budget has no room for one — nothing was written and nothing was
    charged.
    """
    # Skip-decisions read from whichever store this pass is writing to:
    # ``content_versions`` for work that is servable immediately, the
    # staging table for an edit to a course students are reading. The
    # rules below are identical either way — that is the point of the
    # store abstraction (see ``translation/stores.py``).
    existing = store.active_row(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        locale=target_locale,
    )

    # ``origin='human'`` means a teacher manually wrote a localized copy;
    # the auto-pipeline must never clobber that, even if the source mutated.
    if existing is not None and existing.origin == "human":
        return "skipped"

    if existing is not None and existing.status == "ok" and existing.source_hash == source_hash:
        return "skipped"

    # A row parked for review is not retried on its own. Gemini runs at
    # temperature=0, so the same source would produce the same output
    # and the same verdict — re-asking would burn quota on every save
    # to arrive back where we are. It moves when the source changes
    # (different hash, falls through to a real call) or when a human
    # accepts or replaces it.
    if existing is not None and existing.status == "needs_review" and existing.source_hash == source_hash:
        return "skipped"

    # Rows that hit the retry cap (``failed_permanent``) are terminal as far
    # as the auto-pipeline is concerned. They stay terminal even if the
    # source text mutates — a row that fails for a permanent reason (safety
    # filter, oversize input) won't suddenly succeed because the prompt
    # changed by one word. An operator who wants to retry must explicitly
    # reset ``status='ok'`` / ``status='failed'`` + ``attempts=0`` from
    # admin tooling.
    if existing is not None and existing.status == "failed_permanent":
        return "skipped"

    # Phase 5s: duplicate-source dedupe. Gemini at temperature=0 is
    # not strictly deterministic — identical RU source text can render
    # to "Do not move..." 4x and "Don't move..." 1x across a quiz's
    # answer options. Before paying a Gemini call, look for any other
    # active+ok row with the same (target_locale, source_hash) and
    # reuse its text. This costs one indexed query but eliminates an
    # entire class of intra-question inconsistency (and one Gemini
    # call per duplicate). Same-entity rows are excluded so we don't
    # collide with the in-place ``existing`` branch above.
    twin = (
        db.query(ContentVersion.text)
        .filter(
            ContentVersion.locale == target_locale,
            ContentVersion.source_hash == source_hash,
            ContentVersion.status == ContentVersionStatus.OK,
            ContentVersion.superseded_by.is_(None),
            ~((ContentVersion.entity_type == entity_type) & (ContentVersion.entity_id == entity_id)),
        )
        .order_by(ContentVersion.created_at)
        .limit(1)
        .scalar()
    )
    if twin is not None:
        store.record_success(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            locale=target_locale,
            text=twin,
            source_locale=source_locale,
            source_hash=source_hash,
            status=ContentVersionStatus.OK,
            review_reason=None,
        )
        return "translated"

    # Everything above this line is cheap: an indexed lookup, maybe a
    # reuse of an identical translation already paid for. Below it is a
    # network call that can take its timeout on each of its retries. So
    # this is where the deadline is enforced — a call is only started
    # when its whole worst case still fits inside the invocation. The
    # row is left exactly as it was; the next tick finds it unchanged
    # and does the work then.
    if not budget.can_afford_one_call():
        logger.info(
            "Translation deferred (budget spent) entity=%s:%s field=%s locale=%s",
            entity_type,
            entity_id,
            field,
            target_locale,
        )
        return "deferred"

    request = TranslationRequest(
        text=text,
        source_locale=source_locale,
        target_locale=target_locale,
        content_kind=content_kind,
        context=context,
    )
    try:
        result = provider.translate(request)
    except TranslationError as exc:
        logger.warning(
            "Translation failed entity=%s:%s field=%s locale=%s err=%s",
            entity_type,
            entity_id,
            field,
            target_locale,
            exc,
        )
        # The store bumps ``attempts`` in place and promotes to
        # ``failed_permanent`` at the threshold.
        store.record_failure(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            locale=target_locale,
            source_locale=source_locale,
            source_hash=source_hash,
        )
        return "failed"

    # The provider only checked that the response was well-formed.
    # Whether what came back is a translation OF THIS TEXT — same
    # scripture markers, same markup, same numbers, the language we
    # asked for — is decided here. A row that fails is stored with its
    # text and parked as ``needs_review``: readers filter on ``ok``, so
    # it reads as "not translated yet" instead of being served.
    issues = validate_translation(
        source=text,
        translated=result.text,
        source_locale=source_locale,
        target_locale=target_locale,
        content_kind=content_kind,
    )
    if issues:
        # Ask once more before parking it.
        #
        # The rule that a ``needs_review`` row is never retried rests on
        # "temperature 0 means the same answer", and that turns out to be
        # false. Measured on 2026-08-17: a one-sentence block came back
        # from production stripped of its <p> wrapper and was parked; the
        # identical text, same model, same prompt, came back clean nine
        # times out of nine on the next attempts. The model is not
        # deterministic, so a structural failure is often a coin landing
        # badly rather than a fact about the text.
        #
        # One retry, and only when the first answer actually failed —
        # which costs a call on the rare bad roll and saves a person
        # having to accept a row by hand. A second failure is treated as
        # what it looks like: something about this text the model cannot
        # do, and a human should see it.
        if budget.can_afford_one_call():
            logger.info(
                "Translation failed validation, retrying once entity=%s:%s field=%s locale=%s issues=%s",
                entity_type,
                entity_id,
                field,
                target_locale,
                ",".join(issue.code for issue in issues),
            )
            try:
                retry = provider.translate(request)
            except TranslationError:
                retry = None
            if retry is not None:
                retry_issues = validate_translation(
                    source=text,
                    translated=retry.text,
                    source_locale=source_locale,
                    target_locale=target_locale,
                    content_kind=content_kind,
                )
                if not retry_issues:
                    result = retry
                    issues = []

    if issues:
        logger.warning(
            "Translation failed validation entity=%s:%s field=%s locale=%s issues=%s",
            entity_type,
            entity_id,
            field,
            target_locale,
            ",".join(issue.code for issue in issues),
        )

    # The live store supersedes the active row and resets attempts on
    # success; the staged store overwrites its single row. Either way
    # the text is now recorded with the verdict the check gave it.
    store.record_success(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        locale=target_locale,
        text=result.text,
        source_locale=source_locale,
        source_hash=source_hash,
        status=ContentVersionStatus.NEEDS_REVIEW if issues else ContentVersionStatus.OK,
        review_reason=summarise(issues) if issues else None,
    )
    return "needs_review" if issues else "translated"


__all__ = [
    "OrchestratorReport",
    "TranslationFieldSpec",
    "other_locales",
    "translate_course_metadata",
    "translate_entity_fields",
]
