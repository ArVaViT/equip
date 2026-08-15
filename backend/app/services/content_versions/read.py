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

from typing import TYPE_CHECKING, Literal

from sqlalchemy import tuple_

from app.models.content_version import ContentVersion, ContentVersionStatus
from app.services.translation.service import is_translation_enabled

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
            ContentVersion.status == ContentVersionStatus.OK,
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
    fallback: Literal["auto", "none", "source_then_any"] = "auto",
) -> dict[tuple[str, str], str | None]:
    """Read every active+ok ``content_versions`` row for the given
    entities + fields and resolve each (entity, field) to one text.

    ``fallback`` decides what happens when nothing exists at
    ``display_locale``:

    * ``"none"`` — the answer is ``None``. This is what a reader gets:
      nobody is served a language they did not choose, and a surface that
      receives ``None`` says "not in your language" rather than quietly
      showing another one.
    * ``"source_then_any"`` — fall through to ``source_locale``, then to
      any active locale (earliest created, so it is deterministic). This
      is for the people who need to see the text whatever language it is
      in: the teacher editing their own course, the reviewer grading a
      submission, the certificate that must print a course name. Showing
      them nothing would be hiding their own material from them.
    * ``"auto"`` (the default) — ``"none"`` where the platform actually
      translates, ``"source_then_any"`` where it does not. On a deploy
      with no provider configured there is only ever one language, so
      serving the text that exists is not substituting a language for the
      reader's: it is the only language there is.

    The old behaviour was ``"source_then_any"`` everywhere, unconditionally,
    which is how a Ukrainian student ended up reading Russian.

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
    if fallback == "auto":
        fallback = "none" if is_translation_enabled() else "source_then_any"
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
            ContentVersion.status == ContentVersionStatus.OK,
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
            wanted = by_locale.get((eid, field, display_locale))
            if wanted is not None or fallback == "none":
                resolved[(eid, field)] = wanted
                continue
            any_tier = (
                human_for_pair.get((eid, field)) or any_for_pair.get((eid, field))
                if prefer_human
                else any_for_pair.get((eid, field))
            )
            resolved[(eid, field)] = by_locale.get((eid, field, source_locale)) or any_tier
    return resolved
