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
    prefer_human: bool = False,
) -> dict[tuple[str, str], str | None]:
    """Read every active+ok ``content_versions`` row for the given
    entities + fields, then resolve each (entity, field) to a single
    text using a three-tier fallback: ``display_locale`` first, then
    ``source_locale``, then any-locale-with-earliest-created_at.

    Returns a map ``(entity_id, field) -> text or None``. ``None`` only
    appears when no active+ok row exists at any locale.

    When ``prefer_human`` is set, the any-locale tier prefers
    human-authored rows (``origin='human'``) over MT ones. The
    display-locale and source-locale tiers ignore the flag — the
    overlay system intentionally serves MT text in those locales
    when that's what's authoritative. The flag matters only for the
    ``?source=1`` editor view, where a teacher wants to see THEIR
    typed text in its source language even if an MT row at that
    locale was created earlier.

    Phase 5e-series: entities whose source columns are dropped need
    one indexed lookup per request to materialise responses; this is
    that lookup.
    """
    if not entity_ids or not fields:
        return {}
    rows = (
        db.query(
            ContentVersion.entity_id,
            ContentVersion.field,
            ContentVersion.locale,
            ContentVersion.text,
            ContentVersion.origin,
        )
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
    human_for_pair: dict[tuple[str, str], str] = {}
    for eid, field, locale, text, origin in rows:
        by_locale.setdefault((eid, field, locale), text)
        any_for_pair.setdefault((eid, field), text)
        if origin == "human":
            human_for_pair.setdefault((eid, field), text)
    resolved: dict[tuple[str, str], str | None] = {}
    for eid in entity_ids:
        for field in fields:
            any_tier = (
                human_for_pair.get((eid, field)) or any_for_pair.get((eid, field))
                if prefer_human
                else any_for_pair.get((eid, field))
            )
            resolved[(eid, field)] = (
                by_locale.get((eid, field, display_locale)) or by_locale.get((eid, field, source_locale)) or any_tier
            )
    return resolved
