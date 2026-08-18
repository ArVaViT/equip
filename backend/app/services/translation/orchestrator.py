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

from app.schemas.locale import LOCALE_CODES, LocaleCode, normalize_locale
from app.services.translation.executor import TranslationTask, execute_plan
from app.services.translation.hash import compute_source_hash
from app.services.translation.service import (
    get_translation_provider,
    is_translation_enabled,
)
from app.services.translation.stores import LIVE_STORE, VersionStore

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.content_version import (
        ContentVersionEntityType as TranslationEntityType,
    )
    from app.models.content_version import (
        ContentVersionField as TranslationField,
    )
    from app.models.course import Course
    from app.services.translation.budget import TranslationBudget
    from app.services.translation.protocol import ContentKind, TranslationProvider

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
    active_store = store or LIVE_STORE

    tasks = build_tasks(
        entity_type=entity_type,
        entity_id=entity_id,
        source_locale=source_locale,
        fields=fields,
        target_locales=target_locales,
        context=context,
    )
    result = execute_plan(
        db,
        tasks,
        provider=active_provider,
        store=active_store,
        budget=budget,
    )

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
        result.translated,
        result.skipped,
        result.failed,
        result.needs_review,
        result.incomplete,
    )
    return OrchestratorReport(
        translated=result.translated,
        skipped=result.skipped,
        failed=result.failed,
        needs_review=result.needs_review,
        incomplete=result.incomplete,
    )


def build_tasks(
    *,
    entity_type: TranslationEntityType,
    entity_id: str,
    source_locale: LocaleCode,
    fields: list[TranslationFieldSpec],
    target_locales: tuple[LocaleCode, ...] | None = None,
    context: str | None = None,
) -> list[TranslationTask]:
    """Turn one entity's field specs into (field, target) work items.

    Split out so a whole course can be planned in one go: the executor
    runs a list, and a list assembled from every entity under a course
    is what turns eight concurrent calls into eight concurrent calls on
    real work rather than on the three locales of a single block.

    Empty fields are dropped here — nothing to translate, and an empty
    row would round-trip into the UI as a blank.
    """
    tasks: list[TranslationTask] = []
    for spec in fields:
        text = (spec.text or "").strip()
        if not text:
            continue
        # Per-field source locale (set by ``reconcile_entity`` from the
        # detector) decides the direction; the entity-level value is the
        # fallback for fields the detector could not read.
        field_source: LocaleCode = spec.source_locale or source_locale
        field_targets = target_locales if target_locales is not None else other_locales(field_source)
        if not field_targets:
            continue
        source_hash = compute_source_hash(text, locale=field_source)
        tasks.extend(
            TranslationTask(
                entity_type=entity_type,
                entity_id=entity_id,
                field=spec.field,
                source_locale=field_source,
                target_locale=target,
                text=text,
                content_kind=spec.content_kind,
                source_hash=source_hash,
                context=context,
            )
            for target in field_targets
        )
    return tasks


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


__all__ = [
    "OrchestratorReport",
    "TranslationFieldSpec",
    "other_locales",
    "translate_course_metadata",
    "translate_entity_fields",
]
