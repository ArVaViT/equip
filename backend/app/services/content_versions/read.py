"""Cv-primary read helpers — Phase 4 is now the only path.

The Phase 4 feature flag (``CONTENT_VERSIONS_READ_PRIMARY``) was
deleted in Phase 5a. Every overlay fetch comes from
``content_versions``; the legacy ``content_translations`` branch in
``resolve_for_display.py`` is gone.

The cv query:

    SELECT entity_type, entity_id, field, text
    FROM content_versions
    WHERE (entity_type, entity_id, field) IN :keys
      AND locale = :display_locale
      AND superseded_by IS NULL
      AND status = 'ok'

Uses ``uniq_content_versions_active`` directly (partial unique on
``superseded_by IS NULL``). Same number of round-trips as the legacy
fetcher — zero N+1 risk.

We do NOT re-detect per-field language on the read path: cv already
has the detected locale recorded at write time (Phase 1 dual-write +
Phase 3 backfill). The read trusts what's there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import tuple_

from app.models.content_version import ContentVersion

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def fetch_cv_text_bulk(
    db: Session,
    keys: list[tuple[str, str, str]],
    display_locale: str,
) -> dict[tuple[str, str, str], str]:
    """Bulk-fetch ``content_versions`` active+ok rows keyed by
    ``(entity_type, entity_id, field)`` at the given display_locale.

    Drop-in for the legacy ``fetch_overlay_triples_bulk`` — same dict
    shape so the consumer (``pick_overlay_value``) is store-agnostic.
    """
    if not keys:
        return {}
    uniq = list(dict.fromkeys(keys))
    rows = (
        db.query(ContentVersion)
        .filter(
            tuple_(
                ContentVersion.entity_type,
                ContentVersion.entity_id,
                ContentVersion.field,
            ).in_(uniq),
            ContentVersion.locale == display_locale,
            ContentVersion.superseded_by.is_(None),
            ContentVersion.status == "ok",
        )
        .all()
    )
    return {(r.entity_type, r.entity_id, r.field): r.text for r in rows}


def fetch_cv_entity_texts_with_fallback(
    db: Session,
    *,
    entity_type: str,
    entity_ids: list[str],
    fields: list[str],
    display_locale: str,
    source_locale: str,
) -> dict[tuple[str, str], str | None]:
    """Read every active+ok ``content_versions`` row for the given
    entities + fields, then resolve each (entity, field) to a single
    text using a three-tier fallback: ``display_locale`` first, then
    ``source_locale``, then any-locale-with-earliest-created_at.

    Returns a map ``(entity_id, field) -> text or None``. ``None`` only
    appears when no active+ok row exists at any locale.

    Phase 5e-series: entities whose source columns are dropped need
    one indexed lookup per request to materialise responses; this is
    that lookup. Same code path for the locale-aware list endpoints
    and the single-entity GET/POST/PUT returns.
    """
    if not entity_ids or not fields:
        return {}
    rows = (
        db.query(ContentVersion.entity_id, ContentVersion.field, ContentVersion.locale, ContentVersion.text)
        .filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id.in_(entity_ids),
            ContentVersion.field.in_(fields),
            ContentVersion.superseded_by.is_(None),
            ContentVersion.status == "ok",
        )
        .order_by(ContentVersion.entity_id, ContentVersion.field, ContentVersion.created_at)
        .all()
    )
    by_locale: dict[tuple[str, str, str], str] = {}
    any_for_pair: dict[tuple[str, str], str] = {}
    for eid, field, locale, text in rows:
        by_locale.setdefault((eid, field, locale), text)
        any_for_pair.setdefault((eid, field), text)
    resolved: dict[tuple[str, str], str | None] = {}
    for eid in entity_ids:
        for field in fields:
            resolved[(eid, field)] = (
                by_locale.get((eid, field, display_locale))
                or by_locale.get((eid, field, source_locale))
                or any_for_pair.get((eid, field))
            )
    return resolved


def fetch_cv_course_text_bulk(
    db: Session,
    *,
    course_ids: list[str],
    display_locale: str,
) -> dict[tuple[str, str], str]:
    """Course-catalog bulk variant: returns ``(course_id, field) -> text``
    for the course title + description overlay at display_locale."""
    if not course_ids:
        return {}
    rows = (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == "course",
            ContentVersion.entity_id.in_(course_ids),
            ContentVersion.locale == display_locale,
            ContentVersion.field.in_(("title", "description")),
            ContentVersion.superseded_by.is_(None),
            ContentVersion.status == "ok",
        )
        .all()
    )
    return {(r.entity_id, r.field): r.text for r in rows}
