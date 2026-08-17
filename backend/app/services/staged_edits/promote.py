"""The moment an edit becomes visible — in every language, at once.

A field is promoted when it is whole: the teacher's new text, plus an
``ok`` translation of *that exact text* in every other language the
platform serves. Both halves matter. Without the "of that exact text"
part, a second edit arriving mid-flight could be published alongside
translations of the first one — the failure mode this whole mechanism
exists to prevent, reintroduced from the inside.

Promotion writes through the ordinary ``content_versions`` helpers, so
supersession, provenance, and history behave exactly as they do for any
other write. Then the staged rows are deleted: they have no meaning
once released, and an empty table is how "nothing is in flight" is
stated.

One transaction per field. Not per course — a course-wide commit would
mean one blocked field holds back every other edit — and not per row,
which is the whole point: a reader must never catch the field
half-changed, with Ukrainian updated and German not.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.models.content_version import ContentVersionStatus
from app.models.staged_content_version import StagedContentVersion
from app.services.content_versions.write import record_human_version, record_mt_version
from app.services.staged_edits.read import staged_status_for_course
from app.services.translation.hash import compute_source_hash

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.course import Course

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PromotionReport:
    """What one sweep did."""

    promoted_fields: int = 0
    waiting_fields: int = 0
    blocked_fields: int = 0

    @property
    def anything_promoted(self) -> bool:
        return self.promoted_fields > 0


def promote_ready_fields(db: Session, course: Course) -> PromotionReport:
    """Release every in-flight edit of ``course`` that is whole.

    Safe to call often and on a course with nothing staged: one indexed
    query answers "nothing to do".
    """
    statuses = staged_status_for_course(db, course)
    if not statuses:
        return PromotionReport()

    promoted = 0
    waiting = 0
    blocked = 0
    for status in statuses:
        if status.state == "blocked":
            blocked += 1
            continue
        if status.state != "ready":
            waiting += 1
            continue
        if _promote_one_field(
            db,
            course_id=str(course.id),
            entity_type=status.entity_type,
            entity_id=status.entity_id,
            field=status.field,
        ):
            promoted += 1
        else:
            waiting += 1

    if promoted or blocked:
        logger.info(
            "staged_edits: course %s promoted=%d waiting=%d blocked=%d",
            course.id,
            promoted,
            waiting,
            blocked,
        )
    return PromotionReport(promoted_fields=promoted, waiting_fields=waiting, blocked_fields=blocked)


def _promote_one_field(
    db: Session,
    *,
    course_id: str,
    entity_type: str,
    entity_id: str,
    field: str,
) -> bool:
    """Move one field's staged rows into ``content_versions``.

    Returns False without writing anything if the field turns out not to
    be promotable after all — the teacher saved again between the status
    read and this call, and the translations on hand now belong to text
    that is no longer current. Re-checked here rather than trusted from
    the caller because those two moments are not the same moment.
    """
    rows = (
        db.query(StagedContentVersion)
        .filter(
            StagedContentVersion.entity_type == entity_type,
            StagedContentVersion.entity_id == entity_id,
            StagedContentVersion.field == field,
        )
        .with_for_update()
        .all()
    )
    human = next((r for r in rows if r.origin == "human"), None)
    if human is None:
        return False

    expected_hash = compute_source_hash(human.text, locale=human.locale)
    translations = [
        r for r in rows if r.origin == "mt" and r.status == ContentVersionStatus.OK and r.source_hash == expected_hash
    ]

    # The human text lands first so the translations recorded below can
    # point their provenance at it.
    record_human_version(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        locale=human.locale,
        text=human.text,
        authored_by=human.authored_by,
    )
    for row in translations:
        record_mt_version(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            locale=row.locale,
            text=row.text,
            source_locale=row.source_locale or human.locale,
            source_hash=row.source_hash or expected_hash,
            status=ContentVersionStatus.OK,
        )

    for row in rows:
        db.delete(row)
    db.commit()
    logger.info(
        "staged_edits: released %s:%s field=%s in %d languages",
        entity_type,
        entity_id,
        field,
        len(translations) + 1,
    )
    return True


def promote_staged_entity_unconditionally(db: Session, *, course_id: str) -> int:
    """Release everything staged for a course, translated or not.

    For the one case where holding an edit back stops making sense: the
    course leaves ``published``. Nobody is reading it any more, so there
    is no mid-change view to protect, and edits left in the staging
    table would be invisible to the teacher's own draft — they would
    have to retype work they had already done.

    The half-translated fields this releases are then handled by the
    ordinary publication gate: the course cannot return to the catalog
    until every language is whole again.

    Returns the number of fields released.
    """
    rows = db.query(StagedContentVersion).filter(StagedContentVersion.course_id == course_id).with_for_update().all()
    if not rows:
        return 0

    by_field: dict[tuple[str, str, str], list[StagedContentVersion]] = {}
    for row in rows:
        by_field.setdefault((row.entity_type, row.entity_id, row.field), []).append(row)

    released = 0
    for (entity_type, entity_id, field), group in by_field.items():
        human = next((r for r in group if r.origin == "human"), None)
        if human is None:
            continue
        record_human_version(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            locale=human.locale,
            text=human.text,
            authored_by=human.authored_by,
        )
        expected_hash = compute_source_hash(human.text, locale=human.locale)
        for row in group:
            if row.origin != "mt" or row.status != ContentVersionStatus.OK or row.source_hash != expected_hash:
                continue
            record_mt_version(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                field=field,
                locale=row.locale,
                text=row.text,
                source_locale=row.source_locale or human.locale,
                source_hash=row.source_hash or expected_hash,
                status=ContentVersionStatus.OK,
            )
        released += 1

    for row in rows:
        db.delete(row)
    db.commit()
    logger.info("staged_edits: course %s left published; released %d held fields as-is", course_id, released)
    return released


__all__ = [
    "PromotionReport",
    "promote_ready_fields",
    "promote_staged_entity_unconditionally",
]
