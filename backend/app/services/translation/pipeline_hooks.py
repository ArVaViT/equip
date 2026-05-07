"""Fire-and-forget hooks called by write endpoints after a successful save.

Two flavours:

* ``run_course_translation_pipeline_if_published`` — full course tree
  walk. Use after a mutation that could ripple across many entities
  (publish, structural reordering, bulk content change). Idempotent via
  ``source_hash`` so re-running on a quiet course is free.

* ``reconcile_entity_if_course_published`` — translate exactly one
  entity (its title/description/content fields per the registry).
  Cheap: one SELECT + one round-trip to Gemini per missing field. Use
  after a per-entity write (creating one announcement, editing one
  block) so we don't waste DB / Gemini calls re-walking the whole tree.

Both swallow exceptions internally — a teacher's save must never fail
because Gemini was down or rate-limited.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.course_service import get_course
from app.services.translation.course_pipeline import translate_course_content
from app.services.translation.registry import REGISTRY, reconcile_entity
from app.services.translation.service import is_translation_enabled

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.translation.protocol import EntityType

logger = logging.getLogger(__name__)


def run_course_translation_pipeline_if_published(db: Session, course_id: str) -> None:
    """Re-run the full course tree pipeline when a published course mutates.

    No-ops when the course is a draft, Gemini is disabled, or the load fails.
    Errors never propagate — teachers must never lose a save because MT lagged.
    """
    if not is_translation_enabled():
        return
    course = get_course(db, course_id)
    if not course or course.status != "published":
        return
    try:
        translate_course_content(db, course)
    except Exception:
        logger.exception("Translation pipeline failed after mutation (course_id=%s)", course_id)


def reconcile_entity_if_course_published(
    db: Session,
    entity_type: EntityType,
    entity: object,
) -> None:
    """Translate one entity if its course is published. Fire-and-forget.

    The cheap incremental counterpart of
    ``run_course_translation_pipeline_if_published``: when a teacher
    edits one block / posts one announcement, we don't need to re-walk
    every chapter and quiz of the course — just translate this entity.
    The orchestrator's ``source_hash`` short-circuit still protects
    against duplicate work if the field happens to equal a prior value.

    Errors are logged but never raised — teachers must never lose a
    save because the MT path stumbled.
    """
    if not is_translation_enabled():
        return
    reg = REGISTRY[entity_type]
    course = reg.resolve_course(db, entity)
    if not course or course.status != "published":
        return
    try:
        reconcile_entity(db, entity_type, entity)
    except Exception:
        logger.exception(
            "Per-entity translation failed (entity_type=%s id=%s)",
            entity_type,
            getattr(entity, "id", "?"),
        )
