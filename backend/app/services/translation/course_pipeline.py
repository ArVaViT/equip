"""Translate all teacher-authored text under a course (metadata + tree).

Invoked after publish and after edits while the course stays published.
Idempotent via the orchestrator's ``source_hash`` short-circuit, so a
re-run on an unchanged course costs zero LLM calls.

Per-entity field specs (which fields, which content_kind) live in
``registry.REGISTRY``; the shape of the tree — how to walk modules →
chapters → blocks → quiz/assignment plus the side entities bound by
``course_id`` — lives in ``course_tree``. This module is what remains:
walk, reconcile, add up.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.translation.course_tree import iter_course_entities
from app.services.translation.orchestrator import OrchestratorReport
from app.services.translation.registry import reconcile_entity
from app.services.translation.service import is_translation_enabled

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.course import Course
    from app.services.translation.protocol import TranslationProvider

logger = logging.getLogger(__name__)


def merge_orchestrator_reports(*parts: OrchestratorReport) -> OrchestratorReport:
    return OrchestratorReport(
        translated=sum(p.translated for p in parts),
        skipped=sum(p.skipped for p in parts),
        failed=sum(p.failed for p in parts),
        needs_review=sum(p.needs_review for p in parts),
    )


def translate_course_content(
    db: Session,
    course: Course,
    *,
    provider: TranslationProvider | None = None,
) -> OrchestratorReport:
    """Translate everything teacher-authored under ``course`` into every
    locale that's not the field's source locale.

    Each per-entity step delegates to ``reconcile_entity``, which reads
    the field spec from ``REGISTRY``.
    """
    if not is_translation_enabled():
        return OrchestratorReport()

    total = OrchestratorReport()
    for entity_type, entity in iter_course_entities(db, course):
        total = merge_orchestrator_reports(
            total,
            reconcile_entity(db, entity_type, entity, provider=provider),
        )
    return total


__all__ = ["merge_orchestrator_reports", "translate_course_content"]
