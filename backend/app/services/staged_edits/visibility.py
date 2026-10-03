"""Content that exists but has never been released: readers do not see it.

An *edit* to a live course is held in the staging table while the old
text keeps being served, and readers notice nothing. *New* content on a
live course goes through the same table — and has no old text to fall
back on. Until 2026-10-03 that showed through everywhere a reader looked:
a new announcement listed as an empty title over an empty body, a new
chapter appeared in the tree under its spine title and opened as an empty
lesson, and that empty lesson counted towards «chapters to read» and —
for a quiz chapter — against the student's progress and grade.

The rule, stated once: an entity whose text field has a held human edit
and no released row at all is *awaiting its first release*, and a reader
is not shown it. The author, the course owner and an admin still see it,
through the same surfaces that already show them their own held edits
(``include_author_edits`` / ``?source=1``).

Why the staging table is consulted at all — the reading path otherwise
never names it. The alternative, «visible means some ``content_versions``
row exists», is true of everything production writes, but it would also
hide every row that predates the cv tables and was never translatable,
and it would do so silently. Asking «is a first release pending?» hides
exactly what is provably held and nothing else; and it is asked for
existence only, never for text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import and_, select, tuple_

from app.models.content_version import ContentVersion, ContentVersionStatus
from app.models.course import Chapter
from app.models.staged_content_version import StagedContentVersion

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import InstrumentedAttribute, Session
    from sqlalchemy.sql import ColumnElement


def awaiting_first_release(
    db: Session,
    *,
    entity_type: str,
    fields: Sequence[str],
    entity_ids: Sequence[str] | None = None,
) -> set[str]:
    """Ids of the entities a reader must not be shown yet.

    An entity qualifies when any one of ``fields`` has a held human edit
    and no active ``ok`` row in any language — the text was written and
    nothing of it has ever reached readers. A held edit to a field that
    *has* a released row is an ordinary edit in flight: the entity stays
    visible with its previous wording.

    ``entity_ids`` narrows the question to the rows a page is about to
    render. Without it, every held entity of the type is returned — the
    shape a list route needs to exclude rows *before* paginating, so a
    page is never short by the rows it hid. The staging table is empty at
    rest and holds a handful of rows otherwise, so that is one small query
    either way.
    """
    if not fields or (entity_ids is not None and not entity_ids):
        return set()
    held_query = db.query(StagedContentVersion.entity_id, StagedContentVersion.field).filter(
        StagedContentVersion.entity_type == entity_type,
        StagedContentVersion.field.in_(list(fields)),
        StagedContentVersion.origin == "human",
    )
    if entity_ids is not None:
        held_query = held_query.filter(StagedContentVersion.entity_id.in_(list(entity_ids)))
    held = {(eid, field) for eid, field in held_query.all()}
    if not held:
        return set()
    released = {
        (eid, field)
        for eid, field in db.query(ContentVersion.entity_id, ContentVersion.field)
        .filter(
            ContentVersion.entity_type == entity_type,
            tuple_(ContentVersion.entity_id, ContentVersion.field).in_(list(held)),
            ContentVersion.superseded_by.is_(None),
            ContentVersion.status == ContentVersionStatus.OK,
        )
        .all()
    }
    return {eid for eid, _field in held - released}


def awaiting_first_release_sql(
    entity_type: str,
    id_column: InstrumentedAttribute[str] | ColumnElement[str],
    field: str,
) -> ColumnElement[bool]:
    """The same predicate as a WHERE clause, for the queries that count.

    Only for tables keyed by text: ``entity_id`` is text in both version
    tables, and comparing it to a uuid column needs a cast whose spelling
    differs between Postgres and SQLite (see ``purge_orphans``). Chapters
    are keyed by text, and chapters are what every denominator counts.
    """
    held = (
        select(StagedContentVersion.id)
        .where(
            StagedContentVersion.entity_type == entity_type,
            StagedContentVersion.entity_id == id_column,
            StagedContentVersion.field == field,
            StagedContentVersion.origin == "human",
        )
        .exists()
    )
    released = (
        select(ContentVersion.id)
        .where(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == id_column,
            ContentVersion.field == field,
            ContentVersion.superseded_by.is_(None),
            ContentVersion.status == ContentVersionStatus.OK,
        )
        .exists()
    )
    return and_(held, ~released)


def chapter_awaits_first_release() -> ColumnElement[bool]:
    """``Chapter`` rows a reader must not be shown — or counted against — yet.

    Every place that counts a course's chapters for a student applies
    this beside ``deleted_at IS NULL``: a lesson nobody can open is not
    one they can be behind on.
    """
    return awaiting_first_release_sql("chapter", Chapter.id, "title")


def chapter_is_held(db: Session, chapter_id: str) -> bool:
    """The same question for one chapter a reader reached by id.

    A chapter that is not in a student's tree must not be one URL away
    from them either: until 2026-10-03 the lesson, its blocks and its
    quiz all answered to the id, and an attempt on a held quiz counted
    the moment the quiz was released.
    """
    return db.query(Chapter.id).filter(Chapter.id == chapter_id, chapter_awaits_first_release()).first() is not None


__all__ = [
    "awaiting_first_release",
    "awaiting_first_release_sql",
    "chapter_awaits_first_release",
    "chapter_is_held",
]
