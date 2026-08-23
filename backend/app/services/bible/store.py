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


#: Book slug → how many chapters it has. Derived, not written down: a
#: second table of 66 numbers is a second table to get wrong, and this
#: one already has to be right — the English bundle is the reference
#: system, complete and verified at 31 102 verses across 66 books.
_chapter_counts: dict[str, int] = {}
#: Whether ``_chapter_counts`` has been built. A separate flag and not
#: ``if not _chapter_counts``, because an empty bundle is a perfectly
#: possible answer — a test that points the data directory somewhere
#: else gets one — and emptiness read as "not built yet" means the file
#: is parsed again on every call. Measured: it took the suite from 52
#: seconds to not finishing.
_chapter_counts_built = False


def chapters_in(book: str) -> int | None:
    """How many chapters ``book`` has, or ``None`` if it is not a book.

    Read off the English bundle the first time it is asked and kept.
    English because it is the one edition here that is complete and
    verified end to end; the others are the API's, and asking a network
    service how long a book is to check a citation would be absurd.

    Chapter counts do not differ between the editions this platform
    serves — the versification differences it has to care about are in
    *verse* numbering, which is what ``psalm_numbering`` exists for.
    """
    global _chapter_counts_built
    if not _chapter_counts_built:
        # Read the bundle *before* taking the lock. ``_load_locale``
        # takes the same lock, and ``threading.Lock`` is not reentrant —
        # doing it the obvious way deadlocks on the first call, which is
        # what it did: the suite stopped dead on the first test that
        # validated a reference.
        bundle = _load_locale("en")
        with _lock:
            if not _chapter_counts_built:
                for key in bundle:
                    slug, chapter, _verse = key.rsplit(".", 2)
                    _chapter_counts[slug] = max(_chapter_counts.get(slug, 0), int(chapter))
                _chapter_counts_built = True
    return _chapter_counts.get(book)


def lookup(ref: BibleRef, locale: LocaleCode) -> str | None:
    """Return the canonical verse text for ``ref`` in ``locale``,
    or ``None`` when the verse (or any part of a range) is missing."""
    data = _load_locale(locale)
    if not data:
        return None
    if ref.verse_end is None:
        return _verse(data, ref.book, ref.chapter, ref.verse_start)
    parts: list[str] = []
    for v in range(ref.verse_start, ref.verse_end + 1):
        text = _verse(data, ref.book, ref.chapter, v)
        if text is None:
            return None
        parts.append(text)
    return " ".join(parts)


#: Text that is present in the bundle but is not a verse.
#:
#: `kjv-en.json` carries `3john.1.15 == "[]"`. KJV numbers 3 John to fourteen
#: verses; other traditions have fifteen, and the bundle marks the gap with a
#: placeholder rather than omitting the key. `post_substitute` pastes whatever
#: `lookup` returns into a student's blockquote, so a lesson citing 3 John 15
#: printed a literal `[]` where Scripture should be.
#:
#: One verse rather than the Russian bundle's several thousand, and the same
#: rule applies: a placeholder is an absence, and an absence is safe — the
#: caller falls back to the author's own quotation.
_PLACEHOLDERS = frozenset({"[]", "()", "-", "—"})


def _verse(data: dict[str, str], book: str, chapter: int, verse: int) -> str | None:
    text = data.get(f"{book}.{chapter}.{verse}")
    if text is None:
        return None
    stripped = text.strip()
    if not stripped or stripped in _PLACEHOLDERS:
        return None
    return text


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


__all__ = ["chapters_in", "is_locale_bundled", "lookup", "reset_cache"]
