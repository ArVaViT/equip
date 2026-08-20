"""Where a translation pass reads and writes — live, or held back.

The pipeline does the same work in two situations that differ only in
who is allowed to see the result:

* **Live.** A draft course, a first publication, a platform-wide Daily
  Challenge. Nobody is reading the old text and waiting, so a
  translation is servable the moment it passes its check. Rows go
  straight into ``content_versions``.
* **Staged.** An edit to a course students are reading right now. The
  new text and its translations wait together in
  ``staged_content_versions`` until the field is whole, then land in
  ``content_versions`` in one step — so no reader ever sees a sentence
  whose other languages still describe the sentence it replaced.

Everything else about the pass is identical: the same short-circuits,
the same validation, the same budget, the same prompt. Rather than
fork the orchestrator — two copies of the rules is two sets of rules
within a month — the destination is a parameter. This module is that
parameter: a tiny protocol with one implementation each.

The read side matters as much as the write side. ``active_row`` is
what the orchestrator consults to decide "is this already done?", and
its answer differs by store:

* Live asks ``content_versions`` alone.
* Staged asks ``staged_content_versions`` first, and falls back to
  the live row when it is human-authored — a translation somebody
  typed by hand is not something the machine may overwrite, staged or
  otherwise. That single fallback is why a hand-translated field does
  not deadlock the edit that follows it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import tuple_

from app.models.content_version import ContentVersion, ContentVersionStatus
from app.models.staged_content_version import StagedContentVersion
from app.services.content_versions import record_mt_failure, record_mt_version
from app.services.translation.version import TRANSLATOR_VERSION

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session


@dataclass(frozen=True, slots=True)
class ActiveRow:
    """What the orchestrator needs to know about what is already there.

    Deliberately not the ORM object: the two stores hold different
    types, and the decisions being made — human or machine, up to date
    or not, terminally failed or retryable — need exactly these four
    facts.
    """

    origin: str
    status: str
    source_hash: str | None
    #: Which pipeline generation produced it. A row below the current
    #: version is not an answer, however unchanged its source is.
    translator_version: int = 0
    #: What it says. No decision in ``_decide`` reads this — it is here
    #: for ``term_memory``, which learns what this course has already
    #: called things by lining a translation up against the source that
    #: produced it. Carried on a query that had to run anyway, which is
    #: the entire reason the memory costs no statements: see
    #: ``executor._seed_memory``.
    text: str | None = None


class VersionStore(Protocol):
    """Read/write surface the orchestrator uses. Two implementations."""

    name: str

    def active_row(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: str,
        field: str,
        locale: str,
    ) -> ActiveRow | None: ...

    def active_rows(
        self,
        db: Session,
        keys: list[tuple[str, str, str, str]],
    ) -> dict[tuple[str, str, str, str], ActiveRow]: ...

    def record_success(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: str,
        field: str,
        locale: str,
        text: str,
        source_locale: str,
        source_hash: str,
        status: ContentVersionStatus,
        review_reason: str | None,
    ) -> None: ...

    def record_failure(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: str,
        field: str,
        locale: str,
        source_locale: str,
        source_hash: str,
    ) -> None: ...


def _live_active(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    field: str,
    locale: str,
) -> ContentVersion | None:
    return (
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


def _find_active_source_version_id(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    field: str,
    source_locale: str,
) -> uuid.UUID | None:
    """The id of the human row this translation derives from, when it
    exists — the provenance link that makes cascade invalidation exact."""
    return (
        db.query(ContentVersion.id)
        .filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == entity_id,
            ContentVersion.field == field,
            ContentVersion.locale == source_locale,
            ContentVersion.superseded_by.is_(None),
        )
        .scalar()
    )


class LiveStore:
    """Writes straight into ``content_versions`` — servable at once.

    This is what the pipeline has always done; the class only gives it
    a name so the staged path can be its peer rather than its fork.
    """

    name = "live"

    def active_row(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: str,
        field: str,
        locale: str,
    ) -> ActiveRow | None:
        row = _live_active(db, entity_type=entity_type, entity_id=entity_id, field=field, locale=locale)
        if row is None:
            return None
        return ActiveRow(
            origin=row.origin,
            status=row.status,
            source_hash=row.source_hash,
            translator_version=row.translator_version,
            text=row.text,
        )

    def active_rows(
        self,
        db: Session,
        keys: list[tuple[str, str, str, str]],
    ) -> dict[tuple[str, str, str, str], ActiveRow]:
        """Every one of these rows in as few queries as the driver allows.

        The per-row version of this asked the database once per task,
        which reads fine for a course of thirty fields and stops being
        a detail at three thousand: at a round trip apiece it spent the
        worker's entire budget deciding what to do and never got as far
        as doing it. A whole catalogue re-translation exposed that in
        the first minute.

        Chunked because a query is not a place to put ten thousand
        parameters — bind-parameter limits are real and the planner
        stops helping long before them.
        """
        if not keys:
            return {}
        found: dict[tuple[str, str, str, str], ActiveRow] = {}
        chunk = 500
        for start in range(0, len(keys), chunk):
            window = keys[start : start + chunk]
            rows = (
                db.query(
                    ContentVersion.entity_type,
                    ContentVersion.entity_id,
                    ContentVersion.field,
                    ContentVersion.locale,
                    ContentVersion.origin,
                    ContentVersion.status,
                    ContentVersion.source_hash,
                    ContentVersion.translator_version,
                    ContentVersion.text,
                )
                .filter(
                    tuple_(
                        ContentVersion.entity_type,
                        ContentVersion.entity_id,
                        ContentVersion.field,
                        ContentVersion.locale,
                    ).in_(window),
                    ContentVersion.superseded_by.is_(None),
                )
                .all()
            )
            for entity_type, entity_id, field, locale, origin, status, source_hash, version, text in rows:
                found[(entity_type, entity_id, field, locale)] = ActiveRow(
                    origin=origin,
                    status=status,
                    source_hash=source_hash,
                    translator_version=version,
                    text=text,
                )
        return found

    def record_success(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: str,
        field: str,
        locale: str,
        text: str,
        source_locale: str,
        source_hash: str,
        status: ContentVersionStatus = ContentVersionStatus.OK,
        review_reason: str | None = None,
    ) -> None:
        if not text:
            return
        record_mt_version(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            locale=locale,
            text=text,
            source_locale=source_locale,
            source_hash=source_hash,
            source_version_id=_find_active_source_version_id(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                field=field,
                source_locale=source_locale,
            ),
            status=status,
            review_reason=review_reason,
        )

    def record_failure(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: str,
        field: str,
        locale: str,
        source_locale: str,
        source_hash: str,
    ) -> None:
        record_mt_failure(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            locale=locale,
            source_locale=source_locale,
            source_hash=source_hash,
            source_version_id=_find_active_source_version_id(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                field=field,
                source_locale=source_locale,
            ),
        )


class StagedStore:
    """Writes into ``staged_content_versions`` — held until the field is
    whole in every language.

    No supersession and no history: an edit nobody has seen yet has no
    reader whose view must stay stable, so a re-translation overwrites.

    Constructed per course rather than shared, because every staged row
    records which course it belongs to and the orchestrator — which
    works one entity at a time — has no reason to know.
    """

    name = "staged"

    def __init__(self, course_id: str) -> None:
        self.course_id = course_id

    def active_row(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: str,
        field: str,
        locale: str,
    ) -> ActiveRow | None:
        staged = _staged_row(db, entity_type=entity_type, entity_id=entity_id, field=field, locale=locale)
        if staged is not None:
            return ActiveRow(
                origin=staged.origin,
                status=staged.status,
                source_hash=staged.source_hash,
                translator_version=staged.translator_version,
                text=staged.text,
            )

        # Nothing staged for this locale yet. One live row still binds
        # us: a translation a person typed. The machine never overwrites
        # those, and staging is not a loophole in that rule — so report
        # it and let the orchestrator skip, exactly as it would live.
        # (A live *machine* row says nothing: it translates the text
        # this edit replaces, which is precisely what we are redoing.)
        live = _live_active(db, entity_type=entity_type, entity_id=entity_id, field=field, locale=locale)
        if live is not None and live.origin == "human":
            # A human translation is authoritative regardless of which
            # pipeline generation is current — it was never made by one.
            return ActiveRow(
                origin="human",
                status=live.status,
                source_hash=live.source_hash,
                translator_version=TRANSLATOR_VERSION,
                text=live.text,
            )
        return None

    def active_rows(
        self,
        db: Session,
        keys: list[tuple[str, str, str, str]],
    ) -> dict[tuple[str, str, str, str], ActiveRow]:
        """Staged rows first, then the live human rows that still bind us.

        A staged edit is a course at a time, so the volume here is
        smaller than the live path's — but the same round-trip
        arithmetic applies, and one shape for both stores is one shape
        to reason about.
        """
        if not keys:
            return {}
        found: dict[tuple[str, str, str, str], ActiveRow] = {}
        chunk = 500
        for start in range(0, len(keys), chunk):
            window = keys[start : start + chunk]
            staged_rows = (
                db.query(
                    StagedContentVersion.entity_type,
                    StagedContentVersion.entity_id,
                    StagedContentVersion.field,
                    StagedContentVersion.locale,
                    StagedContentVersion.origin,
                    StagedContentVersion.status,
                    StagedContentVersion.source_hash,
                    StagedContentVersion.translator_version,
                    StagedContentVersion.text,
                )
                .filter(
                    tuple_(
                        StagedContentVersion.entity_type,
                        StagedContentVersion.entity_id,
                        StagedContentVersion.field,
                        StagedContentVersion.locale,
                    ).in_(window),
                    StagedContentVersion.course_id == self.course_id,
                )
                .all()
            )
            for entity_type, entity_id, field, locale, origin, status, source_hash, version, text in staged_rows:
                found[(entity_type, entity_id, field, locale)] = ActiveRow(
                    origin=origin,
                    status=status,
                    source_hash=source_hash,
                    translator_version=version,
                    text=text,
                )

        # Only for keys nothing was staged against: a live *machine* row
        # says nothing here, because it translates the text this edit
        # replaces. A live human row does — it is never overwritten.
        remaining = [key for key in keys if key not in found]
        for start in range(0, len(remaining), chunk):
            window = remaining[start : start + chunk]
            live_rows = (
                db.query(
                    ContentVersion.entity_type,
                    ContentVersion.entity_id,
                    ContentVersion.field,
                    ContentVersion.locale,
                    ContentVersion.status,
                    ContentVersion.source_hash,
                    ContentVersion.text,
                )
                .filter(
                    tuple_(
                        ContentVersion.entity_type,
                        ContentVersion.entity_id,
                        ContentVersion.field,
                        ContentVersion.locale,
                    ).in_(window),
                    ContentVersion.superseded_by.is_(None),
                    ContentVersion.origin == "human",
                )
                .all()
            )
            for entity_type, entity_id, field, locale, status, source_hash, text in live_rows:
                found[(entity_type, entity_id, field, locale)] = ActiveRow(
                    origin="human",
                    status=status,
                    source_hash=source_hash,
                    translator_version=TRANSLATOR_VERSION,
                    text=text,
                )
        return found

    def record_success(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: str,
        field: str,
        locale: str,
        text: str,
        source_locale: str,
        source_hash: str,
        status: ContentVersionStatus = ContentVersionStatus.OK,
        review_reason: str | None = None,
    ) -> None:
        if not text:
            return
        _upsert_staged(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            course_id=self.course_id,
            field=field,
            locale=locale,
            text=text,
            origin="mt",
            status=str(status),
            review_reason=review_reason,
            source_locale=source_locale,
            source_hash=source_hash,
            attempts=0,
        )

    def record_failure(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: str,
        field: str,
        locale: str,
        source_locale: str,
        source_hash: str,
    ) -> None:
        from app.models.content_version import CONTENT_VERSION_MAX_ATTEMPTS

        existing = _staged_row(db, entity_type=entity_type, entity_id=entity_id, field=field, locale=locale)
        attempts = (existing.attempts if existing is not None else 0) + 1
        status = (
            ContentVersionStatus.FAILED_PERMANENT
            if attempts >= CONTENT_VERSION_MAX_ATTEMPTS
            else ContentVersionStatus.FAILED
        )
        _upsert_staged(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            course_id=self.course_id,
            field=field,
            locale=locale,
            # A failure has no text. Empty string is the sentinel, same
            # as the live table uses; promotion only ever reads ``ok``
            # rows, so it is never mistaken for content.
            text=existing.text if existing is not None else "",
            origin="mt",
            status=str(status),
            review_reason=None,
            source_locale=source_locale,
            source_hash=source_hash,
            attempts=attempts,
        )


def _staged_row(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    field: str,
    locale: str,
) -> StagedContentVersion | None:
    return (
        db.query(StagedContentVersion)
        .filter(
            StagedContentVersion.entity_type == entity_type,
            StagedContentVersion.entity_id == entity_id,
            StagedContentVersion.field == field,
            StagedContentVersion.locale == locale,
        )
        .one_or_none()
    )


def _upsert_staged(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    course_id: str,
    field: str,
    locale: str,
    text: str,
    origin: str,
    status: str,
    review_reason: str | None,
    source_locale: str | None,
    source_hash: str | None,
    attempts: int,
    authored_by: uuid.UUID | None = None,
) -> StagedContentVersion:
    """Insert or overwrite the one row for this key."""
    row = _staged_row(db, entity_type=entity_type, entity_id=entity_id, field=field, locale=locale)
    if row is None:
        row = StagedContentVersion(
            entity_type=entity_type,
            entity_id=entity_id,
            course_id=course_id,
            field=field,
            locale=locale,
            text=text,
            origin=origin,
            status=status,
            review_reason=review_reason,
            source_locale=source_locale,
            source_hash=source_hash,
            attempts=attempts,
            authored_by=authored_by,
            # A staged machine row carries its generation for the same
            # reason a live one does: an edit sitting in review must not
            # be promoted carrying the quality of an older pipeline.
            # Human rows are stamped too and simply never re-translated.
            translator_version=TRANSLATOR_VERSION,
        )
        db.add(row)
    else:
        row.text = text
        row.origin = origin
        row.status = status
        row.review_reason = review_reason
        row.source_locale = source_locale
        row.source_hash = source_hash
        row.attempts = attempts
        row.translator_version = TRANSLATOR_VERSION
        if authored_by is not None:
            row.authored_by = authored_by
    db.flush()
    return row


LIVE_STORE = LiveStore()


__all__ = [
    "LIVE_STORE",
    "ActiveRow",
    "LiveStore",
    "StagedStore",
    "VersionStore",
    "_upsert_staged",
]
