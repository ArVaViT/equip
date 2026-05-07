"""Lazy-loaded canonical Bible text store.

Two bundled translations live as flat ``{book.chapter.verse: text}``
JSON in ``data/``: KJV (1769) for ``en``, Synodal (1876) for ``ru``.
Both are public-domain. Files are loaded on first lookup and cached
for the lifetime of the process — they're 4-6 MB each, so a cold
startup that never reaches a translation pipeline pays nothing.

Range lookups (``acts 1:8-10``) join the verses with a single space.
A missing verse in a range yields ``None`` for the whole reference —
better to fall back to the author's quote than to return a partial
canonical text that lies about its completeness.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode
    from app.services.bible.references import BibleRef


_DATA_DIR = Path(__file__).parent / "data"
_FILES: dict[str, str] = {
    "en": "kjv-en.json",
    "ru": "synodal-ru.json",
}

_cache: dict[str, dict[str, str]] = {}
_lock = threading.Lock()


def _load_locale(locale: LocaleCode) -> dict[str, str]:
    """Read the bundled JSON for ``locale``. Idempotent + thread-safe."""
    if locale in _cache:
        return _cache[locale]
    with _lock:
        if locale in _cache:
            return _cache[locale]
        filename = _FILES.get(locale)
        if filename is None:
            # Locale not bundled — skip silently. The caller treats a
            # missing return value as "no canonical text available" and
            # falls back to the author's quote.
            _cache[locale] = {}
            return _cache[locale]
        path = _DATA_DIR / filename
        if not path.exists():
            _cache[locale] = {}
            return _cache[locale]
        _cache[locale] = json.loads(path.read_text(encoding="utf-8"))
        return _cache[locale]


def lookup(ref: BibleRef, locale: LocaleCode) -> str | None:
    """Return the canonical verse text for ``ref`` in ``locale``,
    or ``None`` when the verse (or any part of a range) is missing."""
    data = _load_locale(locale)
    if not data:
        return None
    if ref.verse_end is None:
        return data.get(f"{ref.book}.{ref.chapter}.{ref.verse_start}")
    parts: list[str] = []
    for v in range(ref.verse_start, ref.verse_end + 1):
        text = data.get(f"{ref.book}.{ref.chapter}.{v}")
        if text is None:
            return None
        parts.append(text)
    return " ".join(parts)


def is_locale_bundled(locale: LocaleCode) -> bool:
    """Whether canonical text is available for this locale at all.
    Used by the substitution layer to skip the work entirely on
    locales we haven't shipped data for."""
    return locale in _FILES


def reset_cache() -> None:
    """Test-only: clear the in-memory cache so a test that mutates the
    on-disk data files (or monkey-patches ``_FILES``) sees a fresh load.
    Production code should never call this."""
    with _lock:
        _cache.clear()


__all__ = ["is_locale_bundled", "lookup", "reset_cache"]
