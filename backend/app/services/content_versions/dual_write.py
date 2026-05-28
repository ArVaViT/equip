"""Shared per-field dual-write helper used by every entity write
path during Phase 1.

The pattern repeats for every translatable entity:

1. Read each translatable field's text from the entity.
2. Detect that field's language (or fall back to a caller-supplied
   locale when the detector has no signal).
3. Call ``record_human_version`` once per field.

Centralising it here keeps every call site to a 4-line invocation,
and means a future change to language-detection / fallback strategy
edits ONE function instead of N.

Reads still go to entity columns. Phase 2 introduces the dual-read
layer; Phase 4 flips reads exclusive.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.services.content_versions.write import record_human_version
from app.services.language_detection import detect_locale

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.orm import Session


def dual_write_entity_content(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    entity: object | None = None,
    fields: Iterable[str],
    fallback_locale: str | None,
    authored_by: str | uuid.UUID | None = None,
    only_fields: set[str] | None = None,
    texts: dict[str, str | None] | None = None,
) -> None:
    """Write a ``content_versions`` human row for every translatable
    field the caller wrote.

    Per-field detection: each field's locale is decided from its own
    text. Two fields on the same entity can land in different locales
    (an EN title and a RU description are normal). Detection falls
    back to ``fallback_locale`` when the field text is too short to
    classify or has no language signal.

    Two ways to supply the text per field:

    * ``texts={'title': 'Hello', 'description': None}`` — explicit
      dict keyed by field name. Required for entities whose source
      column has been dropped (Phase 5e+).
    * ``entity=<orm instance>`` — fallback path that reads
      ``getattr(entity, field)``. Backward-compat for entities whose
      source columns still exist.

    When both are set, ``texts`` wins per-field; ``entity`` fills in
    keys missing from the dict.

    ``only_fields`` filters to the fields the caller actually wrote
    (used on UPDATE so a description-only PATCH doesn't supersede
    the title row). ``None`` means "every field in ``fields``".

    ``authored_by`` is stored on the row when known. Accepts a UUID
    or a string-coerceable id.
    """
    if only_fields is None:
        target_fields: list[str] = list(fields)
    else:
        target_fields = [f for f in fields if f in only_fields]

    if not target_fields:
        return

    author_uuid = _coerce_uuid(authored_by)

    for field in target_fields:
        if texts is not None and field in texts:
            raw = texts[field]
        elif entity is not None:
            raw = getattr(entity, field, None)
        else:
            raw = None
        if not raw or not str(raw).strip():
            continue
        text_str = str(raw)
        detected = detect_locale(text_str)
        locale = detected or fallback_locale
        if locale is None:
            # No signal AND no fallback — skip. The field re-enters
            # this path the next time the entity is saved with
            # enough surrounding context to resolve a fallback.
            continue
        record_human_version(
            db,
            entity_type=entity_type,
            entity_id=entity_id,
            field=field,
            locale=locale,
            text=text_str,
            authored_by=author_uuid,
        )


def _coerce_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))
