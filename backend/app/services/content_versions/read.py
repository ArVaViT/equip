"""Phase 4 cv-primary read helpers + env-flag gate.

When ``CONTENT_VERSIONS_READ_PRIMARY=1``, the canonical overlay
fetchers in ``resolve_for_display.py`` route through these helpers
instead of querying the legacy ``content_translations`` table.
Same dict shape returned either way — call sites stay untouched.

Default: flag is OFF. Phase 4's first PR ships the new path dark;
ops bumps the env var to enable. Rollback is one env-var flip + a
redeploy (no code revert needed).

The cv query mirrors the legacy one but hits ``content_versions``:

    SELECT entity_type, entity_id, field, text
    FROM content_versions
    WHERE (entity_type, entity_id, field) IN :keys
      AND locale = :display_locale
      AND superseded_by IS NULL
      AND status = 'ok'

Uses ``uniq_content_versions_active`` directly (partial unique on
``superseded_by IS NULL``). Same number of round-trips as the legacy
fetcher — Phase 4 has zero N+1 risk.

We do NOT re-detect per-field language on the read path: cv already
has the detected locale recorded at write time (Phase 1 dual-write +
Phase 3 backfill). The read trusts what's there.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from sqlalchemy import tuple_

from app.models.content_version import ContentVersion

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# Read once at import time — flag changes require a redeploy / worker
# restart, which is fine for a phased migration. Tests override via
# ``set_read_primary`` to flip behavior per-test without monkey-
# patching the module constant directly.
_READ_PRIMARY: bool = os.environ.get("CONTENT_VERSIONS_READ_PRIMARY", "0").strip() in ("1", "true", "True")


def set_read_primary(value: bool) -> None:
    """Test-only override for the cv-primary read flag.

    Production code reads ``CONTENT_VERSIONS_READ_PRIMARY`` from the
    environment at import time. Tests use this hook to flip the flag
    per-test without monkey-patching the constant directly.
    """
    global _READ_PRIMARY
    _READ_PRIMARY = bool(value)


def read_from_content_versions() -> bool:
    """Return True when the resolver should source overlay rows from
    ``content_versions``. False = read from the legacy
    ``content_translations`` table (Phase 0-3 behaviour)."""
    return _READ_PRIMARY


def fetch_cv_text_bulk(
    db: Session,
    keys: list[tuple[str, str, str]],
    display_locale: str,
) -> dict[tuple[str, str, str], str]:
    """Bulk-fetch ``content_versions`` active+ok rows keyed by
    ``(entity_type, entity_id, field)`` at the given display_locale.

    Drop-in replacement for ``fetch_overlay_triples_bulk`` — returns
    the same dict shape so the consumer (``pick_overlay_value``) is
    locale- and store-agnostic.
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


def fetch_cv_course_text_bulk(
    db: Session,
    *,
    course_ids: list[str],
    display_locale: str,
) -> dict[tuple[str, str], str]:
    """Course-catalog bulk variant: returns ``(course_id, field) -> text``
    for the course title + description overlay at display_locale.

    Drop-in replacement for ``batch_fetch_course_translations``.
    """
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
