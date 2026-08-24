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

from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.models.course import Course, CourseStatus
from app.services.course_service import get_course
from app.services.translation.course_pipeline import translate_course_content
from app.services.translation.protocol import TranslationError
from app.services.translation.queue import enqueue_course_translation
from app.services.translation.registry import REGISTRY, reconcile_entity
from app.services.translation.service import is_translation_enabled

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.translation.protocol import EntityType

logger = logging.getLogger(__name__)


def _safe_rollback(db: Session) -> None:
    """Roll the session back without ever raising — pipeline hooks must
    return cleanly even if the rollback itself fails. Any inner failure
    here is logged at critical because it leaves the session in an
    unrecoverable state for the caller's next operation."""
    try:
        db.rollback()
    except Exception:
        logger.critical("Translation pipeline session rollback failed", exc_info=True)


def _log_pipeline_failure(
    *,
    scope: str,
    entity_type: str | None,
    entity_id: object,
    exc: BaseException,
) -> None:
    """Single structured logging point for every pipeline-hook
    swallowed exception. Goes to the standard logger at the right
    severity, with a ``failure_class`` extra so log aggregation can
    cleanly filter expected vs unexpected failures.
    """
    failure_class = type(exc).__name__
    # ``TranslationError`` (from the provider) is the expected sad
    # path — the failed row is already persisted by the orchestrator
    # via ``_dual_write_mt_failure``, so this is an INFO-level event,
    # not a wake-the-oncall ERROR.
    severity = logging.INFO if isinstance(exc, TranslationError) else logging.ERROR
    logger.log(
        severity,
        "Translation %s failed: %s",
        scope,
        exc,
        extra={
            "failure_class": failure_class,
            "scope": scope,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id is not None else None,
        },
        exc_info=severity == logging.ERROR,
    )


def run_course_translation_pipeline_if_published(db: Session, course_id: str) -> None:
    """Re-run the full course tree pipeline when a published course mutates.

    Two delivery modes, selected by ``settings.TRANSLATION_QUEUE_ENABLED``:

    * **Queue mode** (the default, and what production runs):
      enqueue ONE row in ``translation_jobs`` and return. The cron-
      driven worker drains the queue out-of-band, so a
      100-block course publish takes one INSERT instead of 100
      synchronous Gemini round-trips.
    * **Sync mode** (legacy): call ``translate_course_content``
      directly inside the teacher's request. Kept behind the feature
      flag so a deploy without the worker cron configured stays on the
      working old path.

    No-ops when the course is a draft, Gemini is disabled, or the load
    fails. Errors never propagate — teachers must never lose a save
    because MT lagged. The session is rolled back on SQLAlchemy errors
    so a follow-up query in the same request does not inherit a poisoned
    transaction state.
    """
    if not is_translation_enabled():
        return
    # Narrow probe first — most write hooks fire during course building when
    # the course is still a draft, and loading the full course tree just to
    # read ``status`` is wasted I/O. Only pay for the full tree when we
    # actually intend to translate.
    course_status = db.query(Course.status).filter(Course.id == course_id, Course.deleted_at.is_(None)).scalar()
    # ``publishing`` is a course on its way out that is not whole yet —
    # it is exactly the course that most needs translating. Only a
    # draft is left alone.
    if course_status not in (CourseStatus.PUBLISHED, CourseStatus.PUBLISHING):
        return

    if settings.TRANSLATION_QUEUE_ENABLED:
        # Queue-mode publish path. ``enqueue_course_translation`` is
        # idempotent on pending jobs so a teacher mashing Save doesn't
        # multiply the work the worker has to do.
        try:
            enqueue_course_translation(db, course_id)
        except SQLAlchemyError as exc:
            _safe_rollback(db)
            _log_pipeline_failure(
                scope="course-pipeline-enqueue",
                entity_type="course",
                entity_id=course_id,
                exc=exc,
            )
        except Exception as exc:
            _log_pipeline_failure(
                scope="course-pipeline-enqueue",
                entity_type="course",
                entity_id=course_id,
                exc=exc,
            )
        return

    course = get_course(db, course_id)
    if not course:
        return
    try:
        translate_course_content(db, course)
    except SQLAlchemyError as exc:
        _safe_rollback(db)
        _log_pipeline_failure(scope="course-pipeline", entity_type="course", entity_id=course_id, exc=exc)
    except Exception as exc:
        _log_pipeline_failure(scope="course-pipeline", entity_type="course", entity_id=course_id, exc=exc)


def _translate_and_release_edits(
    db: Session,
    course: Course,
    *,
    entity_type: str,
    entity_id: object,
) -> None:
    """Translate whatever this save put on hold, then release what is whole.

    Two delivery modes, the same pair the full-course path has:

    * **Queue mode** — one INSERT and the cron worker picks it up.
      Preferred in production: a one-line edit still costs one Gemini
      round trip per language, and doing that inside the teacher's
      request means their save is as slow as the provider is that
      minute.
    * **Sync mode** — do it here. On an edit this is a handful of calls
      (one field, three languages), not the hundreds a course walk can
      be, so the legacy path stays honest for a deploy without a cron.

    Either way the teacher's save is never failed by it: the edit is
    already recorded and will be picked up by the next worker pass even
    if everything below throws.
    """
    from app.services.staged_edits import promote_ready_fields
    from app.services.translation.staged_pipeline import translate_staged_edits

    course_id = str(course.id)
    if settings.TRANSLATION_QUEUE_ENABLED:
        try:
            enqueue_course_translation(db, course_id)
        except SQLAlchemyError as exc:
            _safe_rollback(db)
            _log_pipeline_failure(scope="staged-enqueue", entity_type=entity_type, entity_id=entity_id, exc=exc)
        except Exception as exc:
            _log_pipeline_failure(scope="staged-enqueue", entity_type=entity_type, entity_id=entity_id, exc=exc)
        return

    try:
        translate_staged_edits(db, course)
        promote_ready_fields(db, course)
    except SQLAlchemyError as exc:
        _safe_rollback(db)
        _log_pipeline_failure(scope="staged-edit", entity_type=entity_type, entity_id=entity_id, exc=exc)
    except Exception as exc:
        _log_pipeline_failure(scope="staged-edit", entity_type=entity_type, entity_id=entity_id, exc=exc)


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
    save because the MT path stumbled. ``SQLAlchemyError`` rolls the
    session back so the caller's next query is not poisoned.
    """
    if not is_translation_enabled():
        return
    reg = REGISTRY[entity_type]
    course = reg.resolve_course(db, entity)
    if not course or course.status not in (CourseStatus.PUBLISHED, CourseStatus.PUBLISHING):
        return
    entity_id = getattr(entity, "id", None)

    # On a published course the teacher's new text did not go into
    # ``content_versions`` at all — it is held in the staging table
    # until every language has it (see ``services/staged_edits``). So
    # the thing to translate is the held edit, not the entity, and
    # reconciling the entity here would re-check text that has not
    # changed and leave the edit untranslated. Which is how an edit
    # would sit invisible forever.
    if course.status == CourseStatus.PUBLISHED:
        _translate_and_release_edits(db, course, entity_type=str(entity_type), entity_id=entity_id)
        return

    try:
        reconcile_entity(db, entity_type, entity)
    except SQLAlchemyError as exc:
        _safe_rollback(db)
        _log_pipeline_failure(
            scope="entity-reconcile",
            entity_type=str(entity_type),
            entity_id=entity_id,
            exc=exc,
        )
    except Exception as exc:
        _log_pipeline_failure(
            scope="entity-reconcile",
            entity_type=str(entity_type),
            entity_id=entity_id,
            exc=exc,
        )
