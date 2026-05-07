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

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.models.content_translation import (
    ContentTranslation,
    TranslationEntityType,
    TranslationField,
)
from app.schemas.locale import LOCALE_CODES, LocaleCode, normalize_locale
from app.services.translation.hash import compute_source_hash
from app.services.translation.protocol import (
    TranslationError,
    TranslationProvider,
    TranslationRequest,
)
from app.services.translation.service import (
    get_translation_provider,
    is_translation_enabled,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.course import Course

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TranslationFieldSpec:
    """One ``(field, text, content_kind)`` tuple to translate.

    ``text`` is allowed to be empty / ``None``; the orchestrator skips those
    rows so the caller can build the spec list naively without filtering.
    """

    field: TranslationField
    text: str | None
    # See ``TranslationRequest.content_kind`` — chooses prompt nuances.
    content_kind: str = "plain"


@dataclass(frozen=True, slots=True)
class OrchestratorReport:
    """Lightweight summary returned to the caller.

    Useful both in tests and in admin endpoints that surface a quick "X
    fields translated, Y skipped" toast in the UI.
    """

    translated: int = 0
    skipped: int = 0
    failed: int = 0


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
) -> OrchestratorReport:
    """Translate ``fields`` of ``(entity_type, entity_id)`` into each target.

    Returns a per-call summary. Never raises for ordinary translation
    failures — those become ``status='failed'`` rows. Re-raises only on
    SQLAlchemy errors, which surface bugs that the caller does want to see.
    """
    if not is_translation_enabled():
        # Don't burn DB writes when there's no real provider configured;
        # the noop fallback would just echo the source text back.
        logger.info("Translation disabled; skipping %s:%s", entity_type, entity_id)
        return OrchestratorReport()

    targets = target_locales if target_locales is not None else other_locales(source_locale)
    if not targets:
        return OrchestratorReport()

    active_provider = provider or get_translation_provider()
    translated = 0
    skipped = 0
    failed = 0

    for spec in fields:
        text = (spec.text or "").strip()
        if not text:
            # Empty source has nothing to translate; we also actively avoid
            # creating empty translation rows that would later round-trip
            # back into the UI as blanks. Empty-source fields are not
            # counted in ``skipped`` — that counter tracks rows we
            # *consciously* short-circuited (human override, hash match),
            # not rows that never had work to do.
            continue

        source_hash = compute_source_hash(text, locale=source_locale)
        for target in targets:
            outcome = _translate_one_field(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                field=spec.field,
                source_locale=source_locale,
                target_locale=target,
                text=text,
                content_kind=spec.content_kind,
                source_hash=source_hash,
                context=context,
                provider=active_provider,
            )
            if outcome == "translated":
                translated += 1
            elif outcome == "skipped":
                skipped += 1
            else:
                failed += 1

    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    logger.info(
        "Translation orchestrator finished entity=%s:%s translated=%d skipped=%d failed=%d",
        entity_type,
        entity_id,
        translated,
        skipped,
        failed,
    )
    return OrchestratorReport(translated=translated, skipped=skipped, failed=failed)


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
    content_kind: str,
    source_hash: str,
    context: str | None,
    provider: TranslationProvider,
) -> str:
    """Translate (or up-to-date short-circuit) one ``(field, target)`` row.

    Returns ``"translated" | "skipped" | "failed"`` so the orchestrator can
    aggregate counters without inspecting the DB row again.
    """
    existing = (
        db.query(ContentTranslation)
        .filter(
            ContentTranslation.entity_type == entity_type,
            ContentTranslation.entity_id == entity_id,
            ContentTranslation.field == field,
            ContentTranslation.locale == target_locale,
        )
        .one_or_none()
    )

    # ``origin='human'`` means a teacher manually wrote a localized copy;
    # the auto-pipeline must never clobber that, even if the source mutated.
    if existing is not None and existing.origin == "human":
        return "skipped"

    if existing is not None and existing.status == "ok" and existing.source_hash == source_hash:
        return "skipped"

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
        _persist_translation(
            db,
            existing=existing,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            target_locale=target_locale,
            text=existing.text if existing is not None else text,
            source_hash=source_hash,
            status="failed",
        )
        return "failed"

    _persist_translation(
        db,
        existing=existing,
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        target_locale=target_locale,
        text=result.text,
        source_hash=source_hash,
        status="ok",
    )
    return "translated"


def _persist_translation(
    db: Session,
    *,
    existing: ContentTranslation | None,
    entity_type: TranslationEntityType,
    entity_id: str,
    field: TranslationField,
    target_locale: LocaleCode,
    text: str,
    source_hash: str,
    status: str,
) -> None:
    """Insert or update one translation row.

    Wraps each insert in a SAVEPOINT so a concurrent writer that beats us to
    the unique key (``content_translations_unique``) doesn't corrupt the
    outer transaction — we catch the ``IntegrityError``, roll back the
    savepoint, refetch the row a peer just inserted, and turn the operation
    into an update instead. This mirrors the enrollment race fix in
    ``app.services.course_service._enrollment``. The outer ``db.commit()``
    happens later in ``translate_entity_fields``; per-row savepoints keep
    that batch commit safe even when many course-publish hooks fire on the
    same course at once.
    """
    if existing is not None:
        existing.text = text
        existing.source_hash = source_hash
        existing.status = status
        return

    row = ContentTranslation(
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        locale=target_locale,
        text=text,
        source_hash=source_hash,
        status=status,
        origin="mt",
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        # A concurrent translator just inserted the same
        # (entity_type, entity_id, field, locale) row. Re-fetch and
        # convert to an in-place update so this batch still converges on
        # the latest source_hash + text without a 500 to the caller.
        winner = (
            db.query(ContentTranslation)
            .filter(
                ContentTranslation.entity_type == entity_type,
                ContentTranslation.entity_id == entity_id,
                ContentTranslation.field == field,
                ContentTranslation.locale == target_locale,
            )
            .one_or_none()
        )
        if winner is None:
            # Race lost but row vanished — nothing we can do beyond
            # surfacing the original failure on the next commit.
            raise
        # Don't clobber a human-edited row; the auto-pipeline never
        # overwrites manual translations even under racing conditions.
        if winner.origin == "human":
            return
        winner.text = text
        winner.source_hash = source_hash
        winner.status = status


__all__ = [
    "OrchestratorReport",
    "TranslationFieldSpec",
    "other_locales",
    "translate_course_metadata",
    "translate_entity_fields",
]
