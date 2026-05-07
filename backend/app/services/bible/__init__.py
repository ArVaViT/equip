"""Public-domain Bible canonical-text substitution for the translation pipeline.

When a teacher writes a Synodal Russian quote in a ``<blockquote>``, the
EN-locale student should see the corresponding canonical KJV English
text — not Gemini's paraphrase, and not the source-locale verse left
untouched. This package detects scripture quotations in source HTML,
swaps them for unique markers before translation, and restores them
with the canonical target-locale text after translation.

Public API:

* ``find_book(s) -> str | None`` — canonical book slug from any alias
* ``parse_references(text) -> list[ParsedReference]`` — extract refs
* ``lookup(ref, locale) -> str | None`` — canonical text or None
* ``pre_substitute(html, source_locale) -> (markered_html, subs)``
* ``post_substitute(html, subs, target_locale) -> html``

Bundled data: KJV (1769) for ``en``, Russian Synodal (1876) for ``ru``.
Both public domain. Loaded lazily on first lookup.
"""

from __future__ import annotations

from app.services.bible.books import find_book
from app.services.bible.references import BibleRef, ParsedReference, parse_references
from app.services.bible.store import lookup
from app.services.bible.substitution import (
    Substitution,
    post_substitute,
    pre_substitute,
)

__all__ = [
    "BibleRef",
    "ParsedReference",
    "Substitution",
    "find_book",
    "lookup",
    "parse_references",
    "post_substitute",
    "pre_substitute",
]
