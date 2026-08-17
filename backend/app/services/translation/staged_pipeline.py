"""Translating the edits that are waiting, rather than the course.

The live pipeline walks a course tree and asks each entity what it has.
This one walks the staging table instead and asks each held edit what
it still needs — a much shorter list, because a course at rest has
nothing staged at all, and a course being edited usually has one or two
fields in flight.

The work per field is identical (same orchestrator, same validation,
same budget); only the destination differs, which is what
``translation/stores.py`` exists for.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from app.schemas.locale import LocaleCode, normalize_locale
from app.services.staged_edits.read import staged_field_specs
from app.services.translation.budget import NoBudget
from app.services.translation.orchestrator import (
    OrchestratorReport,
    TranslationFieldSpec,
    translate_entity_fields,
)
from app.services.translation.registry import REGISTRY
from app.services.translation.service import is_translation_enabled
from app.services.translation.stores import StagedStore

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.content_version import ContentVersionField as TranslationField
    from app.models.course import Course
    from app.services.translation.budget import TranslationBudget
    from app.services.translation.protocol import ContentKind, EntityType, TranslationProvider

logger = logging.getLogger(__name__)


def _content_kind_of(entity_type: str, field: str) -> ContentKind:
    """The prompt nuance this field is translated with.

    Read from the same registry the live path uses, so a quiz option
    staged for release is translated as a quiz option and not as prose.
    Falls back to ``plain`` for a field the registry does not describe —
    which would be a registry bug, not a reason to skip the work.
    """
    reg = REGISTRY.get(cast("EntityType", entity_type))
    if reg is not None:
        for spec in reg.fields:
            if spec.name == field:
                return spec.content_kind
    return "plain"


def translate_staged_edits(
    db: Session,
    course: Course,
    *,
    provider: TranslationProvider | None = None,
    budget: TranslationBudget | None = None,
) -> OrchestratorReport:
    """Translate every edit held for ``course`` into every other language.

    Returns the combined report. ``incomplete`` propagates from the
    budget exactly as it does on the live path, so the worker treats a
    long backlog of edits the same way it treats a long course: pause,
    keep what was done, continue next tick.
    """
    if not is_translation_enabled():
        return OrchestratorReport()

    specs = staged_field_specs(db, str(course.id))
    if not specs:
        return OrchestratorReport()

    active_budget = budget or NoBudget()
    store = StagedStore(str(course.id))
    total = OrchestratorReport()

    for entity_type, entity_id, field, source_locale, text in specs:
        if active_budget.expired():
            total = _merge(total, OrchestratorReport(incomplete=True))
            break
        locale: LocaleCode = normalize_locale(source_locale)
        part = translate_entity_fields(
            db,
            entity_type=cast("EntityType", entity_type),
            entity_id=entity_id,
            source_locale=locale,
            fields=[
                TranslationFieldSpec(
                    field=cast("TranslationField", field),
                    text=text,
                    content_kind=_content_kind_of(entity_type, field),
                    source_locale=locale,
                )
            ],
            provider=provider,
            budget=active_budget,
            store=store,
        )
        total = _merge(total, part)
        if part.incomplete:
            break

    logger.info(
        "staged pipeline: course %s translated=%d skipped=%d failed=%d needs_review=%d incomplete=%s",
        course.id,
        total.translated,
        total.skipped,
        total.failed,
        total.needs_review,
        total.incomplete,
    )
    return total


def _merge(*parts: OrchestratorReport) -> OrchestratorReport:
    return OrchestratorReport(
        translated=sum(p.translated for p in parts),
        skipped=sum(p.skipped for p in parts),
        failed=sum(p.failed for p in parts),
        needs_review=sum(p.needs_review for p in parts),
        incomplete=any(p.incomplete for p in parts),
    )


__all__ = ["translate_staged_edits"]
