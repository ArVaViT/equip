"""Translate all teacher-authored text under a course (metadata + tree).

Invoked after publish and after edits while the course stays published.
Idempotent via the orchestrator's ``source_hash`` short-circuit, so a
re-run on an unchanged course costs zero LLM calls.

Per-entity field specs (which fields, which content_kind) live in
``registry.REGISTRY``; the shape of the tree — how to walk modules →
chapters → blocks → quiz/assignment plus the side entities bound by
``course_id`` — lives in ``course_tree``. This module is what remains:
walk, plan, execute.

**Plan the whole course, then run it.** The walk used to translate one
entity at a time, and each entity is one or two fields — so the widest
thing in flight was a field's three target languages. Since the pass is
99.8% waiting on the network (measured: 1 ms of our own work per call),
that shape put a ceiling on everything: a 2,610-call course took some
forty minutes, almost all of it idle sockets.

Collecting the tasks for the entire tree first and handing them to
``executor.execute_plan`` lets the concurrency apply across entities
instead of within one, which is the difference between a batch of three
and a batch of eight — and, on a real course, between forty minutes and
about two.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.schemas.locale import normalize_locale
from app.services.translation.budget import NoBudget
from app.services.translation.course_tree import iter_course_entities
from app.services.translation.executor import execute_plan
from app.services.translation.orchestrator import OrchestratorReport, build_tasks
from app.services.translation.registry import REGISTRY, entity_field_specs
from app.services.translation.service import (
    get_translation_provider,
    is_translation_enabled,
)
from app.services.translation.stores import LIVE_STORE

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.course import Course
    from app.schemas.locale import LocaleCode
    from app.services.translation.budget import TranslationBudget
    from app.services.translation.executor import TranslationTask
    from app.services.translation.protocol import TranslationProvider
    from app.services.translation.stores import VersionStore

logger = logging.getLogger(__name__)


def merge_orchestrator_reports(*parts: OrchestratorReport) -> OrchestratorReport:
    return OrchestratorReport(
        translated=sum(p.translated for p in parts),
        skipped=sum(p.skipped for p in parts),
        failed=sum(p.failed for p in parts),
        needs_review=sum(p.needs_review for p in parts),
        incomplete=any(p.incomplete for p in parts),
    )


def plan_course_tasks(db: Session, course: Course) -> list[TranslationTask]:
    """Every (field, target locale) the course still describes.

    Walks the tree once, asks the registry what each entity's
    translatable fields are and which language each one is actually
    written in (the per-field detector lives there), and turns the
    answer into work items. Deciding what is already done is the
    executor's first phase — this only says what exists.
    """
    from app.services.translation.resolve_for_display import populate_spine_texts

    course_source: LocaleCode = normalize_locale(course.source_locale)
    tasks: list[TranslationTask] = []

    # ``build_context`` lambdas read ``course.title``, which is a runtime
    # attribute hydrated from cv rather than a column. Hydrate once for
    # the whole walk instead of per entity.
    populate_spine_texts(db, [course])

    for entity_type, entity in iter_course_entities(db, course):
        reg = REGISTRY[entity_type]
        fields = entity_field_specs(db, entity_type, entity, course_source)
        if not fields:
            continue
        context = reg.build_context(entity, course) if reg.build_context is not None else None
        tasks.extend(
            build_tasks(
                entity_type=entity_type,
                entity_id=str(entity.id),  # type: ignore[attr-defined]
                source_locale=course_source,
                fields=fields,
                context=context,
            )
        )
    return tasks


def translate_course_content(
    db: Session,
    course: Course,
    *,
    provider: TranslationProvider | None = None,
    budget: TranslationBudget | None = None,
    store: VersionStore | None = None,
) -> OrchestratorReport:
    """Translate everything teacher-authored under ``course`` into every
    locale that's not the field's source locale.

    ``budget`` bounds the pass. A course whose tree does not fit in one
    worker invocation is not a course that cannot be translated — the
    executor stops on a batch boundary when the clock says so and the
    report says ``incomplete``, and the next tick resumes from the first
    field that still needs work.
    """
    if not is_translation_enabled():
        return OrchestratorReport()

    active_budget = budget or NoBudget()
    tasks = plan_course_tasks(db, course)
    if not tasks:
        return OrchestratorReport()

    result = execute_plan(
        db,
        tasks,
        provider=provider or get_translation_provider(),
        store=store or LIVE_STORE,
        budget=active_budget,
    )
    db.commit()

    logger.info(
        "course %s: planned %d tasks, translated=%d skipped=%d failed=%d needs_review=%d incomplete=%s",
        course.id,
        len(tasks),
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


__all__ = ["merge_orchestrator_reports", "plan_course_tasks", "translate_course_content"]
