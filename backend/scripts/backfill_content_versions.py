"""Phase 3 of the V1 bilingual rebuild: backfill ``content_versions``.

Copies every legitimate row from the legacy stores (entity-column
source text + ``content_translations`` overlay) into the new
``content_versions`` table. After this script completes, the new
store contains a superset of what the legacy store has, with the
same supersession + provenance guarantees Phase 1's dual-write
provides.

Usage (defaults to dry-run for safety):

    # Dry-run for the entire corpus — no writes, just a summary.
    python backend/scripts/backfill_content_versions.py --dry-run

    # Apply to a single entity type (useful for staged rollouts).
    python backend/scripts/backfill_content_versions.py \\
        --entity-type course --apply

    # Apply to one specific course's tree (smoke test).
    python backend/scripts/backfill_content_versions.py \\
        --course-id fce3337a-231f-4d21-a977-905bd6a2cc07 --apply

    # Real run, all entity types.
    python backend/scripts/backfill_content_versions.py --apply

Design highlights (full spec lives in the PR description that ships
with the script):

* Reuses the existing ``record_human_version`` / ``record_mt_version``
  / ``record_mt_failure`` write helpers. Those helpers are already
  idempotent on identical text / matching source_hash — running the
  backfill twice does not duplicate rows.

* Per-entity transactions: one commit per entity. Worst case a course
  with 6 fields ≈ 12 row writes per commit. Bounded blast radius if
  a single entity hits an unexpected edge case; concurrent live
  Phase 1 dual-writes that collide get caught and logged per-entity,
  the script continues with the next one.

* Per-FIELD language detection (mirrors Phase 1's dual_write helper):
  the backfill does NOT trust ``courses.source_locale`` as truth for
  child entities. Prod audit found multiple RU courses whose modules
  / chapters are authored in English; per-field detection is the only
  way to get the source row's locale correct.

* MT rows get ``source_version_id`` pointing at the human row inserted
  in the same transaction (precise cascade invalidation). When the
  legacy ``content_translations`` row's locale equals the source row's
  locale (16 such collisions in prod, identical text), the MT call
  is a no-op via the write helper's belt-and-braces "refuse to
  overwrite a human row" guard. The source row wins.

* Cohort + global announcements: no parent course, so detection-only
  with a system-default fallback. In prod, the single cohort name is
  Cyrillic and the only two announcements are course-scoped, so
  this branch is rarely exercised.

* Soft-deleted entities skipped. Orphan ``content_translations`` rows
  (entity hard-deleted, cascade missed) are never visited because the
  outer loop iterates live entities and pulls their CT rows by FK.
  A final summary query counts orphans for ops awareness.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.database import _get_engine
from app.models.content_translation import ContentTranslation
from app.models.content_version import CONTENT_VERSION_MAX_ATTEMPTS, ContentVersion
from app.services.content_versions.write import (
    record_human_version,
    record_mt_failure,
    record_mt_version,
)
from app.services.language_detection import detect_locale
from app.services.translation.registry import ENTITY_MODEL, REGISTRY

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

logger = logging.getLogger("backfill_content_versions")


# Topological order: a child can only resolve its parent course's
# source_locale if the parent is present, so iterate parents first.
# Within a type, ORDER BY id keeps each run deterministic.
_ENTITY_ORDER: tuple[str, ...] = (
    "course",
    "module",
    "chapter",
    "chapter_block",
    "quiz",
    "quiz_question",
    "quiz_option",
    "assignment",
    "announcement",
    "course_event",
    "cohort",
)


# Default for cohorts / global announcements when per-field detection
# returns None AND no parent course exists. Matches the
# ``LocaleCode`` Literal default in ``app/schemas/locale.py``.
_SYSTEM_DEFAULT_LOCALE = "ru"


@dataclass
class EntitySummary:
    human_inserted: int = 0
    human_already_present: int = 0
    mt_inserted: int = 0
    mt_already_present: int = 0
    mt_refused_human_wins: int = 0
    mt_failed_recorded: int = 0
    skipped_empty_field: int = 0
    skipped_no_locale: int = 0
    concurrent_integrity_error: int = 0


def _fallback_locale_for_entity(db: Session, entity_type: str, entity: object) -> str | None:
    """Return the parent course's ``source_locale`` for this entity,
    or ``None`` when there's no parent (cohort / global announcement).

    Mirrors ``REGISTRY[entity_type].resolve_course`` — but returns
    just the locale string instead of the Course row, to keep the
    contract tight."""
    reg = REGISTRY.get(cast("Any", entity_type))
    if reg is None:
        return None
    course = reg.resolve_course(db, entity)
    if course is None:
        return None
    return getattr(course, "source_locale", None)


def _backfill_entity(
    db: Session,
    entity_type: str,
    entity: object,
    *,
    summary: EntitySummary,
) -> None:
    """Insert all source-column rows + all overlay rows for one entity.

    Run inside the caller's transaction so the caller can commit or
    roll back (dry-run mode) per-entity.
    """
    reg = REGISTRY[cast("Any", entity_type)]
    course_fallback = _fallback_locale_for_entity(db, entity_type, entity)
    entity_id_str = str(cast("Any", entity).id)

    # ---------- Pass 1: insert source-column rows (origin='human') ----------
    # Per-field locale detection. Two fields on the same entity can land
    # in different locales — an EN title with a RU description is normal
    # for a teacher who pastes content from different sources.
    human_ids: dict[tuple[str, str], uuid.UUID] = {}
    # Key: (field_db_name, locale) → ContentVersion.id of the newly-inserted (or pre-existing) row.
    field_source_locale: dict[str, str] = {}
    for field_spec in reg.fields:
        field_db = field_spec.name
        text = getattr(entity, field_spec.attr, None)
        if text is None or not str(text).strip():
            summary.skipped_empty_field += 1
            continue
        text_str = str(text)
        detected = detect_locale(text_str)
        # Resolution order: detect → parent course's source_locale →
        # system default. Cohorts and global announcements only ever
        # reach the third step when their text is too short to classify.
        locale = detected or course_fallback or _SYSTEM_DEFAULT_LOCALE
        if locale is None:  # defensive — _SYSTEM_DEFAULT_LOCALE is set
            summary.skipped_no_locale += 1
            continue
        field_source_locale[field_db] = locale
        before = _active_count(db, entity_type, entity_id_str, field_db, locale)
        row = record_human_version(
            db,
            entity_type=entity_type,
            entity_id=entity_id_str,
            field=field_db,
            locale=locale,
            text=text_str,
        )
        human_ids[(field_db, locale)] = row.id
        after = _active_count(db, entity_type, entity_id_str, field_db, locale)
        if after > before:
            summary.human_inserted += 1
        else:
            summary.human_already_present += 1

    # ---------- Pass 2: overlay rows (content_translations → MT) ----------
    cts = (
        db.query(ContentTranslation)
        .filter(
            ContentTranslation.entity_type == entity_type,
            ContentTranslation.entity_id == entity_id_str,
        )
        .all()
    )
    for ct in cts:
        ct_field: str = str(ct.field)
        ct_locale = str(ct.locale)
        # The source row's locale for this field — looked up from
        # pass 1's in-memory map. If pass 1 skipped this field
        # (empty source text), the MT row has no source to link
        # against; we still record it with a None source_version_id
        # so the data isn't lost.
        source_locale = field_source_locale.get(ct_field)
        source_version_id = human_ids.get((ct_field, source_locale)) if source_locale else None

        # `origin='human'` rows in legacy content_translations are
        # translator overrides — preserve as human in cv. Prod audit
        # found ZERO of these, but the branch must be correct in case
        # one slips in mid-run.
        if ct.origin == "human":
            before = _active_count(db, entity_type, entity_id_str, ct_field, ct_locale)
            record_human_version(
                db,
                entity_type=entity_type,
                entity_id=entity_id_str,
                field=ct_field,
                locale=ct_locale,
                text=ct.text,
            )
            after = _active_count(db, entity_type, entity_id_str, ct_field, ct_locale)
            if after > before:
                summary.human_inserted += 1
            else:
                summary.human_already_present += 1
            continue

        # MT path. Status check FIRST so a legacy failed row with
        # empty text gets its attempts + status preserved exactly,
        # rather than being routed to ``record_mt_failure`` (which
        # resets attempts to 1 on fresh insert).
        if ct.status in ("failed", "failed_permanent"):
            _insert_mt_terminal_state(
                db,
                entity_type=entity_type,
                entity_id=entity_id_str,
                field=ct_field,
                locale=ct_locale,
                source_locale=source_locale or _SYSTEM_DEFAULT_LOCALE,
                source_hash=ct.source_hash or "",
                source_version_id=source_version_id,
                attempts=ct.attempts,
                status=ct.status,
            )
            summary.mt_failed_recorded += 1
            continue

        if not ct.text:
            # ok-status but empty text — treat as a fresh failure marker
            # so the retry queue can find it. (Shouldn't exist in healthy
            # legacy data; defensive branch.)
            record_mt_failure(
                db,
                entity_type=entity_type,
                entity_id=entity_id_str,
                field=ct_field,
                locale=ct_locale,
                source_locale=source_locale or _SYSTEM_DEFAULT_LOCALE,
                source_hash=ct.source_hash or "",
                source_version_id=source_version_id,
            )
            summary.mt_failed_recorded += 1
            continue

        # Ordinary ok translation.
        before = _active_count(db, entity_type, entity_id_str, ct_field, ct_locale)
        row = record_mt_version(
            db,
            entity_type=entity_type,
            entity_id=entity_id_str,
            field=ct_field,
            locale=ct_locale,
            text=ct.text,
            source_locale=source_locale or _SYSTEM_DEFAULT_LOCALE,
            source_hash=ct.source_hash or "",
            source_version_id=source_version_id,
        )
        after = _active_count(db, entity_type, entity_id_str, ct_field, ct_locale)
        if row.origin == "human":
            # Source row already occupies this slot (legacy CT row had
            # identical text to source — the 16 prod cases). The write
            # helper refused to overwrite. Net: cv has the human row,
            # which IS the same text. Correct semantics; not a lost row.
            summary.mt_refused_human_wins += 1
        elif after > before:
            summary.mt_inserted += 1
        else:
            summary.mt_already_present += 1


def _insert_mt_terminal_state(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    field: str,
    locale: str,
    source_locale: str,
    source_hash: str,
    source_version_id: object | None,
    attempts: int,
    status: str,
) -> None:
    """Insert an MT row in a terminal failure state, preserving
    ``attempts`` and ``status`` exactly from the legacy row.

    Bypasses ``record_mt_failure`` because that helper auto-bumps
    attempts and re-derives status. For backfill we want the exact
    legacy values transferred.
    """
    import uuid

    existing = (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == entity_id,
            ContentVersion.field == field,
            ContentVersion.locale == locale,
            ContentVersion.superseded_by.is_(None),
        )
        .one_or_none()
    )
    if existing is not None:
        # Already a row at this key — either idempotent re-run or
        # source row is here. Don't touch it.
        return
    db.add(
        ContentVersion(
            id=uuid.uuid4(),
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            locale=locale,
            text="",  # failed rows carry empty text by convention
            origin="mt",
            status=status,
            source_locale=source_locale,
            source_hash=source_hash,
            source_version_id=source_version_id,
            attempts=min(attempts, CONTENT_VERSION_MAX_ATTEMPTS),
        )
    )
    db.flush()


def _active_count(db: Session, entity_type: str, entity_id: str, field: str, locale: str) -> int:
    return (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == entity_id,
            ContentVersion.field == field,
            ContentVersion.locale == locale,
            ContentVersion.superseded_by.is_(None),
        )
        .count()
    )


def _iter_entities(db: Session, entity_type: str, *, course_id: str | None) -> Any:
    model = cast("Any", ENTITY_MODEL[cast("Any", entity_type)])
    q = db.query(model)
    # Skip soft-deleted where the column exists.
    if hasattr(model, "deleted_at"):
        q = q.filter(model.deleted_at.is_(None))
    # Optional single-course scoping for staged rollout / smoke test.
    if course_id is not None:
        if entity_type == "course":
            q = q.filter(model.id == course_id)
        elif hasattr(model, "course_id"):
            q = q.filter(model.course_id == course_id)
        # Children with no direct course_id (chapter / block / quiz /
        # question / option / assignment) need a parent join. Skip for
        # the course-id-scoped run unless extended later — the simple
        # MVP scopes only entities with a direct course_id column.
        elif entity_type not in ("course", "module", "announcement", "course_event"):
            # Fall back to filtering after the fact: we'd have to walk.
            # For the smoke-test use case it's fine to handle only
            # course-level + direct-FK entities; if the user wants the
            # full tree of one course, run the script multiple times
            # with different --entity-type values.
            return iter(())
    return q.order_by(model.id).all()


def _count_orphans(db: Session, entity_type: str) -> int:
    """Number of content_translations rows whose entity no longer exists."""
    model = cast("Any", ENTITY_MODEL[cast("Any", entity_type)])
    ct_ids = (
        db.query(ContentTranslation.entity_id).filter(ContentTranslation.entity_type == entity_type).distinct().all()
    )
    if not ct_ids:
        return 0
    living = {str(r.id) for r in db.query(model.id).all()}
    return sum(1 for (eid,) in ct_ids if str(eid) not in living)


def backfill(
    db: Session,
    *,
    apply: bool,
    entity_types: list[str] | None = None,
    course_id: str | None = None,
) -> dict[str, EntitySummary]:
    """Run the backfill across the configured entity types.

    Returns a per-entity-type summary. When ``apply=False`` (dry-run),
    every per-entity transaction is rolled back via savepoint so the
    database is left untouched.
    """
    summaries: dict[str, EntitySummary] = defaultdict(EntitySummary)
    target_types = entity_types or list(_ENTITY_ORDER)
    for entity_type in _ENTITY_ORDER:
        if entity_type not in target_types:
            continue
        entities = _iter_entities(db, entity_type, course_id=course_id)
        n_processed = 0
        for entity in entities:
            n_processed += 1
            try:
                if not apply:
                    with db.begin_nested() as savepoint:
                        _backfill_entity(db, entity_type, entity, summary=summaries[entity_type])
                        savepoint.rollback()
                else:
                    _backfill_entity(db, entity_type, entity, summary=summaries[entity_type])
                    db.commit()
            except IntegrityError:
                summaries[entity_type].concurrent_integrity_error += 1
                db.rollback()
                logger.warning(
                    "Concurrent write detected for %s:%s; skipping (live dual-write probably won)",
                    entity_type,
                    getattr(entity, "id", "?"),
                )
                continue
            except Exception:
                db.rollback()
                logger.exception("Unexpected failure on %s:%s", entity_type, getattr(entity, "id", "?"))
                raise
            if n_processed % 50 == 0:
                logger.info("Progress: %s processed=%d", entity_type, n_processed)
        orphan_count = _count_orphans(db, entity_type)
        if orphan_count:
            logger.info(
                "Orphan content_translations rows skipped (entity hard-deleted): entity_type=%s count=%d",
                entity_type,
                orphan_count,
            )
    return summaries


def _format_summary(summaries: dict[str, EntitySummary]) -> str:
    lines = ["", "=" * 60, "Backfill summary:", "=" * 60]
    totals = EntitySummary()
    for entity_type in _ENTITY_ORDER:
        s = summaries.get(entity_type)
        if s is None:
            continue
        lines.append(
            f"  {entity_type:14} "
            f"human_inserted={s.human_inserted:4d}  "
            f"human_existing={s.human_already_present:4d}  "
            f"mt_inserted={s.mt_inserted:4d}  "
            f"mt_existing={s.mt_already_present:4d}  "
            f"mt_refused_human_wins={s.mt_refused_human_wins:4d}  "
            f"mt_failed={s.mt_failed_recorded:4d}  "
            f"empty_field={s.skipped_empty_field:4d}  "
            f"concurrent_skip={s.concurrent_integrity_error:4d}"
        )
        totals.human_inserted += s.human_inserted
        totals.human_already_present += s.human_already_present
        totals.mt_inserted += s.mt_inserted
        totals.mt_already_present += s.mt_already_present
        totals.mt_refused_human_wins += s.mt_refused_human_wins
        totals.mt_failed_recorded += s.mt_failed_recorded
        totals.skipped_empty_field += s.skipped_empty_field
        totals.concurrent_integrity_error += s.concurrent_integrity_error
    lines.append("-" * 60)
    lines.append(
        f"  {'TOTAL':14} "
        f"human_inserted={totals.human_inserted:4d}  "
        f"human_existing={totals.human_already_present:4d}  "
        f"mt_inserted={totals.mt_inserted:4d}  "
        f"mt_existing={totals.mt_already_present:4d}  "
        f"mt_refused_human_wins={totals.mt_refused_human_wins:4d}  "
        f"mt_failed={totals.mt_failed_recorded:4d}  "
        f"empty_field={totals.skipped_empty_field:4d}  "
        f"concurrent_skip={totals.concurrent_integrity_error:4d}"
    )
    lines.append("=" * 60)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually commit changes. Without this flag, runs dry-run (default).",
    )
    parser.add_argument(
        "--entity-type",
        action="append",
        choices=list(_ENTITY_ORDER),
        help="Limit to this entity type (repeatable). Default: all.",
    )
    parser.add_argument(
        "--course-id",
        help="Scope to a single course's tree (for smoke tests). Only "
        "applies to entities with a direct course_id column.",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(level=args.log_level, format="%(levelname)s %(name)s: %(message)s")

    if args.apply:
        logger.info("REAL RUN — writes will be committed.")
    else:
        logger.info("DRY RUN — no writes. Use --apply to commit.")

    engine = _get_engine()
    SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with SessionFactory() as db:
        summaries = backfill(
            db,
            apply=args.apply,
            entity_types=args.entity_type,
            course_id=args.course_id,
        )
    logger.info(_format_summary(summaries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
