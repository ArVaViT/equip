"""The three (and only three) write helpers for ``content_versions``.

* ``record_human_version`` — a teacher / admin typed new text.
  Supersedes any active row (human or MT) for the same
  (entity, field, locale) and inserts a new active human row.
  No-op when the active row already has identical text and origin
  ``human``.

* ``record_mt_version`` — the MT pipeline produced a translation.
  Same supersession rules but origin is ``mt`` and provenance
  (``source_hash``, ``source_locale``, ``source_version_id``) is
  set. NEVER supersedes a human row — that would be the MT pipeline
  silently overwriting a teacher edit. The caller (the orchestrator)
  is responsible for not requesting MT when a human row exists.

* ``record_mt_failure`` — the MT pipeline tried and failed.
  Bumps ``attempts`` on the existing active MT row (or inserts a
  new ``status='failed'`` row if there was nothing). Promotes to
  ``failed_permanent`` once ``attempts >= CONTENT_VERSION_MAX_ATTEMPTS``.
  Failures don't create version history — they update in place.

All three operate inside the caller's transaction. The chicken-and-egg
of "point old row at new row before new row exists" works because
``superseded_by`` is a ``DEFERRABLE INITIALLY DEFERRED`` FK; the
check fires at COMMIT. SQLite tests use ``PRAGMA defer_foreign_keys``
to get the same behaviour.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import text as _text

from app.models.content_version import (
    CONTENT_VERSION_MAX_ATTEMPTS,
    ContentVersion,
    ContentVersionStatus,
)
from app.services.translation.version import TRANSLATOR_VERSION

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _is_sqlite(db: Session) -> bool:
    bind = db.get_bind()
    return bind is not None and bind.dialect.name == "sqlite"


def _defer_fk_if_sqlite(db: Session) -> None:
    """SQLite test DB needs an explicit pragma to defer FK checks.

    Postgres already has the FK declared as DEFERRABLE INITIALLY
    DEFERRED at the schema level, so this is a no-op there.
    """
    if _is_sqlite(db):
        db.execute(_text("PRAGMA defer_foreign_keys = ON"))


def _get_active(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    field: str,
    locale: str,
) -> ContentVersion | None:
    """Return the single active row for this key, or ``None``."""
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


def record_human_version(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    field: str,
    locale: str,
    text: str,
    authored_by: uuid.UUID | None = None,
) -> ContentVersion:
    """Insert (or supersede + insert) a human-authored version.

    Returns the row that's now active for this key.

    Idempotent: when the active row already has identical text +
    origin ``human``, nothing changes and the existing row is
    returned. Idempotency matters because dual-write fires from
    every entity save, including re-saves with no text change.

    If the active row is MT (origin ``mt``), it gets superseded —
    a teacher typing text always wins over machine output.
    """
    if not text:
        raise ValueError("record_human_version called with empty text")
    existing = _get_active(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        locale=locale,
    )
    if existing is not None and existing.origin == "human" and existing.text == text:
        # Idempotent path — same text from the same authoring origin.
        # Refresh authored_by if it was unknown before.
        if authored_by is not None and existing.authored_by is None:
            existing.authored_by = authored_by
            db.flush()
        return existing

    new_id = uuid.uuid4()
    if existing is not None:
        _defer_fk_if_sqlite(db)
        existing.superseded_by = new_id
        db.flush()
    new_row = ContentVersion(
        id=new_id,
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        locale=locale,
        text=text,
        origin="human",
        status=ContentVersionStatus.OK,
        authored_by=authored_by,
    )
    db.add(new_row)
    db.flush()
    return new_row


def record_mt_version(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    field: str,
    locale: str,
    text: str,
    source_locale: str,
    source_hash: str,
    source_version_id: uuid.UUID | None = None,
    status: ContentVersionStatus = ContentVersionStatus.OK,
    review_reason: str | None = None,
    translator_version: int | None = None,
) -> ContentVersion:
    """Insert (or supersede + insert) a machine-translated version.

    Never overwrites a human row — if the active row is human, this
    is a no-op (the human translation wins) and the existing human
    row is returned. The orchestrator should be skipping this call
    in that case; the guard here is belt-and-braces.

    Idempotent on ``(text, source_hash, status)`` match — re-running
    MT on unchanged source is free.

    ``source_version_id`` is the FK back to the source human row's
    version id. When set, cascade invalidation can find every MT
    row derived from a now-superseded source.

    ``status`` is ``ok`` for a translation that passed the structural
    check and ``needs_review`` for one that came back and did not (see
    ``services/translation/validation.py``). A ``needs_review`` row
    keeps its text — whoever reviews it has to see what the model
    actually said — but readers filter on ``ok``, so it is not served.
    ``review_reason`` is that check's account of what is wrong.

    ``translator_version`` is which generation of the pipeline made this
    text. It is a parameter rather than a read of the constant because
    the caller that matters — a translation run — decides its generation
    once, at the start, and stamps every row it writes with that one
    number. Reading the constant here would make the stamp a property of
    *when the write happened* rather than of *which pipeline produced
    the words*, and those two stop agreeing the moment a run outlives a
    deploy. ``None`` means "whatever is in force right now", which is
    the right answer for the callers that write one row and return.
    """
    if not text:
        raise ValueError("record_mt_version called with empty text")
    version = TRANSLATOR_VERSION if translator_version is None else translator_version
    existing = _get_active(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        locale=locale,
    )
    if existing is not None and existing.origin == "human":
        # MT pipeline must not overwrite human translation. Belt-
        # and-braces; orchestrator should already skip in this case.
        logger.debug(
            "record_mt_version: refusing to overwrite human row (entity=%s:%s field=%s locale=%s)",
            entity_type,
            entity_id,
            field,
            locale,
        )
        return existing
    if (
        existing is not None
        and existing.origin == "mt"
        and existing.text == text
        and existing.source_hash == source_hash
        and existing.status == status
    ):
        # Identical MT output on an unchanged source — nothing to do.
        # Status is part of the comparison: the same text arriving
        # after a failed structural check has to be able to move the
        # row from ``ok`` to ``needs_review``.
        #
        # The stamp is still refreshed. A newer pipeline that produces
        # the same words has confirmed them, and leaving the old number
        # in place would make the row look unexamined forever — the
        # sweep would pick it up on every cycle and pay for the same
        # answer again.
        existing.translator_version = version
        return existing

    new_id = uuid.uuid4()
    if existing is not None:
        _defer_fk_if_sqlite(db)
        existing.superseded_by = new_id
        db.flush()
    new_row = ContentVersion(
        id=new_id,
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        locale=locale,
        text=text,
        origin="mt",
        status=status,
        review_reason=review_reason,
        source_locale=source_locale,
        source_hash=source_hash,
        source_version_id=source_version_id,
        translator_version=version,
    )
    db.add(new_row)
    db.flush()
    return new_row


def record_mt_failure(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    field: str,
    locale: str,
    source_locale: str,
    source_hash: str,
    source_version_id: uuid.UUID | None = None,
) -> ContentVersion:
    """Record an MT attempt that failed.

    Unlike successful versions, failures DON'T supersede — they
    update the active row in place. A failed translation is not
    version-worthy content; it's just bookkeeping so the retry
    queue can find it.

    If no active row exists: inserts a ``status='failed'`` MT row
    with ``attempts=1``. If an active MT row exists: bumps
    ``attempts``; once ``attempts >= CONTENT_VERSION_MAX_ATTEMPTS``,
    promotes to ``status='failed_permanent'``.

    Refuses to touch a human row — the active human row should not
    have its status flipped because the MT path stumbled.
    """
    existing = _get_active(
        db,
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        locale=locale,
    )
    if existing is not None and existing.origin == "human":
        logger.debug(
            "record_mt_failure: ignored (active row is human) (entity=%s:%s field=%s locale=%s)",
            entity_type,
            entity_id,
            field,
            locale,
        )
        return existing
    if existing is not None and existing.origin == "mt":
        existing.attempts += 1
        # A failed attempt is not a reason to take a good translation off
        # the page.
        #
        # This flipped the active row's status in place, and reads serve
        # only ``status='ok'``. So a row that already held a correct
        # translation was withheld from readers the moment one retry
        # failed — and after five, promoted to ``failed_permanent``,
        # which nothing retries. Production, 2026-08-20: the Gemini
        # prepayment ran out mid-rebuild, every call started returning
        # 429, and within eight minutes 98 finished translations
        # disappeared from the site at a rate of about seventy a minute.
        # German readers stopped being shown «Etwa vier Jahrhunderte» —
        # a perfectly good answer option, still sitting in the row that
        # was now marked failed.
        #
        # The bookkeeping is the point of this function and it stays: the
        # attempt is counted, the source hash is refreshed, the retry
        # queue still finds the row. What stops is treating "we could not
        # reach the translator today" as "what we published yesterday is
        # no longer fit to read". A row holding servable text keeps
        # serving it until something better replaces it.
        if existing.status != ContentVersionStatus.OK or not (existing.text or "").strip():
            existing.status = (
                ContentVersionStatus.FAILED_PERMANENT
                if existing.attempts >= CONTENT_VERSION_MAX_ATTEMPTS
                else ContentVersionStatus.FAILED
            )
        existing.source_locale = source_locale
        existing.source_hash = source_hash
        if source_version_id is not None:
            existing.source_version_id = source_version_id
        db.flush()
        return existing

    new_row = ContentVersion(
        id=uuid.uuid4(),
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        locale=locale,
        # ``failed`` rows need SOMETHING in ``text`` (NOT NULL); use
        # empty string as the sentinel. The resolve helper filters
        # out non-ok rows so this is never read by students.
        text="",
        origin="mt",
        status=ContentVersionStatus.FAILED,
        attempts=1,
        source_locale=source_locale,
        source_hash=source_hash,
        source_version_id=source_version_id,
    )
    db.add(new_row)
    db.flush()
    return new_row


def delete_entity_cv_rows(
    db: Session,
    *,
    entity_type: str,
    entity_id: str | uuid.UUID,
) -> int:
    """Delete every ``content_versions`` row (active + superseded) for one
    entity. Returns the row count.

    The cv table has no FK pointing back at the entity tables — the
    ``(entity_type, entity_id)`` pair is polymorphic, so there's nothing
    for Postgres to cascade. Hard-deletes on leaf entities (announcement,
    assignment, quiz, quiz_question, quiz_option, course_event,
    chapter_block) must call this helper explicitly to avoid orphan
    rows.

    Soft-delete entities (Course, Module, Chapter) MUST NOT call this:
    their cv rows need to survive the soft-delete so restore_course can
    bring back the original text. Only ``permanently_delete_course`` —
    which walks the tree explicitly — is allowed to call this for
    courses + modules + chapters.
    """
    eid_str = str(entity_id)
    deleted = (
        db.query(ContentVersion)
        .filter(ContentVersion.entity_type == entity_type, ContentVersion.entity_id == eid_str)
        .delete(synchronize_session=False)
    )
    # An unreleased edit to a deleted entity is text nobody can ever
    # see, promote, or find. Cleared here rather than at the five call
    # sites so a sixth one cannot forget: "delete this entity's text"
    # has to mean all of it.
    _delete_staged_rows(db, entity_type=entity_type, entity_ids=[eid_str])
    return deleted


def delete_entities_cv_rows(
    db: Session,
    *,
    entity_type: str,
    entity_ids: Sequence[str | uuid.UUID],
) -> int:
    """Bulk variant of ``delete_entity_cv_rows`` — one ``IN``-list DELETE
    for many entities of the same type (e.g. every question of a quiz
    being hard-deleted). Same caveats apply: leaf entities only, never
    soft-delete entities. Returns the row count.
    """
    if not entity_ids:
        return 0
    id_strs = [str(eid) for eid in entity_ids]
    deleted = (
        db.query(ContentVersion)
        .filter(ContentVersion.entity_type == entity_type, ContentVersion.entity_id.in_(id_strs))
        .delete(synchronize_session=False)
    )
    _delete_staged_rows(db, entity_type=entity_type, entity_ids=id_strs)
    return deleted


def _delete_staged_rows(db: Session, *, entity_type: str, entity_ids: list[str]) -> int:
    """Drop any in-flight edits for these entities.

    Imported locally: ``staged_edits`` reads from this module's
    ``record_human_version`` when it promotes, and a module-level
    import in both directions is a cycle.
    """
    from app.models.staged_content_version import StagedContentVersion

    return (
        db.query(StagedContentVersion)
        .filter(
            StagedContentVersion.entity_type == entity_type,
            StagedContentVersion.entity_id.in_(entity_ids),
        )
        .delete(synchronize_session=False)
    )
