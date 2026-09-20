"""Retention for superseded machine translations.

``content_versions`` has never destroyed a version: an update supersedes
the old row instead of overwriting it, so the history of a text stays
readable. That is the right rule for what a person wrote. It is an
expensive rule for what a machine produced, because a machine will
produce it again — and this module is where that rule stops applying to
machine output.

The measurement that prompted this (production, 2026-09-20):

===========================  =======  =======
rows                          count     size
===========================  =======  =======
human, live                    5 308   1.5 MB
human, superseded                 93    65 kB
machine, live                  9 534   3.4 MB
**machine, superseded**       16 604   9.0 MB
===========================  =======  =======

Two thirds of the table is machine output no reader can reach and no
pipeline will read again, and every row of it is reproducible from the
human source it was translated from at about half a second per string.
On the heaviest course — «Книга Деяний Апостолов» — superseded machine
rows are 3.2 MB of its 3.7 MB.

So: keep them for a while, because a translation that went wrong is
worth reading while anyone still remembers the change that caused it,
and drop them after that. Human history is never touched, at any age.

Safety is most of this module, because two columns point *at* the rows
it deletes:

* ``superseded_by`` — the version chain. Deleting a row that another row
  points at sets that pointer to NULL (``ON DELETE SET NULL``), and a row
  whose ``superseded_by`` is NULL is by definition the **live** one. That
  is not a lost pointer, it is a resurrected text: a reader would be
  served a superseded translation, and the partial unique index
  ``uniq_content_versions_active`` would refuse the group's next
  legitimate write because it now holds two live rows.
* ``source_version_id`` — the exact version an MT row was translated
  from. Production has 162 rows pointing at a machine row rather than a
  human one, so this is not hypothetical either.

Both are handled the same way: work in whole groups — one text, one
language — and prune a group only when nothing outside the delete set
points into it. A group holding even one pinned row is skipped entire,
and comes back on a later tick once the pin is gone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from app.models.content_version import ContentVersion

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class PruneReport:
    """What one pass did.

    ``skipped`` counts groups deliberately left alone because something
    still pointed into them. That is an expected outcome, not an error.
    """

    rows: int = 0
    groups: int = 0
    skipped: int = 0

    @property
    def did_work(self) -> bool:
        return bool(self.rows)


def prune_superseded_machine_translations(
    db: Session,
    *,
    older_than_days: int,
    max_groups: int,
) -> PruneReport:
    """Delete superseded ``origin='mt'`` rows past the retention window,
    in whole groups, at most ``max_groups`` groups per call.

    A group is only eligible while it still has a live row. Without that
    check, a group whose live row is gone (an entity soft-deleted after
    its texts were written) would have its tail promoted to live by the
    ``ON DELETE SET NULL``, which is the one outcome this module must
    never produce.

    Commits when it deletes. Rolls nothing back — a failure leaves the
    caller's session untouched, because the only write is the delete.
    """
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    live = aliased(ContentVersion)
    group_has_a_live_row = (
        select(1)
        .where(
            live.entity_type == ContentVersion.entity_type,
            live.entity_id == ContentVersion.entity_id,
            live.field == ContentVersion.field,
            live.locale == ContentVersion.locale,
            live.superseded_by.is_(None),
        )
        .exists()
    )
    prunable = (
        ContentVersion.origin == "mt",
        ContentVersion.superseded_by.is_not(None),
        ContentVersion.updated_at < cutoff,
        group_has_a_live_row,
    )

    # Oldest group first, whole groups only: a budget that cut a group in
    # half would leave exactly the dangling pointer this module exists to
    # avoid. The ordering is also what makes successive ticks advance
    # instead of re-reading the same page.
    groups = db.execute(
        select(
            ContentVersion.entity_type,
            ContentVersion.entity_id,
            ContentVersion.field,
            ContentVersion.locale,
        )
        .where(*prunable)
        .group_by(
            ContentVersion.entity_type,
            ContentVersion.entity_id,
            ContentVersion.field,
            ContentVersion.locale,
        )
        .order_by(func.min(ContentVersion.updated_at))
        .limit(max_groups)
    ).all()
    if not groups:
        return PruneReport()

    doomed_by_group: dict[tuple[str, str, str, str], list[uuid.UUID]] = {}
    for entity_type, entity_id, field, locale in groups:
        ids = (
            db.execute(
                select(ContentVersion.id).where(
                    *prunable,
                    ContentVersion.entity_type == entity_type,
                    ContentVersion.entity_id == entity_id,
                    ContentVersion.field == field,
                    ContentVersion.locale == locale,
                )
            )
            .scalars()
            .all()
        )
        if ids:
            doomed_by_group[(entity_type, entity_id, field, locale)] = list(ids)

    pinned = _rows_pointed_at_from_outside(db, {i for ids in doomed_by_group.values() for i in ids})
    skipped = 0
    for key, ids in list(doomed_by_group.items()):
        if pinned.intersection(ids):
            del doomed_by_group[key]
            skipped += 1

    doomed = [i for ids in doomed_by_group.values() for i in ids]
    if not doomed:
        return PruneReport(skipped=skipped)

    db.query(ContentVersion).filter(ContentVersion.id.in_(doomed)).delete(synchronize_session=False)
    db.commit()
    return PruneReport(rows=len(doomed), groups=len(doomed_by_group), skipped=skipped)


def _rows_pointed_at_from_outside(db: Session, doomed: set[uuid.UUID]) -> set[uuid.UUID]:
    """Of ``doomed``, the rows a surviving row still points at.

    A pointer from one doomed row to another is not a pin — both are
    going — so only rows outside the set are asked.
    """
    if not doomed:
        return set()
    ids = list(doomed)
    rows = db.execute(
        select(ContentVersion.superseded_by, ContentVersion.source_version_id).where(
            ContentVersion.id.not_in(ids),
            or_(
                ContentVersion.superseded_by.in_(ids),
                ContentVersion.source_version_id.in_(ids),
            ),
        )
    ).all()
    pinned: set[uuid.UUID] = set()
    for superseded_by, source_version_id in rows:
        if superseded_by in doomed:
            pinned.add(superseded_by)
        if source_version_id in doomed:
            pinned.add(source_version_id)
    return pinned
