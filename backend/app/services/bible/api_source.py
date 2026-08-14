"""Canonical Scripture from YouVersion, for locales we cannot ship a file for.

Why this exists rather than another vendored JSON bundle: the vendored Russian
one was misaligned — `romans.1.1` returned James — and shipped that way for
long enough to reach students (#990). A bundle is a copy of somebody else's
data that silently rots. An API is the publisher's own copy, and it also
carries the two things a bundle cannot: the licence, and the versification.

Measured against the real key on 2026-08-13:

    de → 7 editions available   (51 Luther 1912 chosen)
    uk → 1 edition available    (188 Kulish 1905 — complete, verified from
                                 Genesis through Revelation)
    ru → 143 Новый Русский Перевод, already serving verse-of-the-day in prod

English keeps its bundled file. It is healthy — 31,103 verses, 66 books, no
misattribution — and it is the hot path: an in-memory dict beats a network
call, and the translation pipeline calls `lookup` synchronously, once per
quoted verse.

**Failure is always silent and always safe.** Every path here returns `None`
on any problem — no key, timeout, 404, malformed body. `post_substitute`
treats `None` as "no canonical text" and keeps the author's own quotation,
which is the behaviour that was already correct.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING

import httpx

from app.services.bible.books import _BOOKS

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode
    from app.services.bible.references import BibleRef

logger = logging.getLogger(__name__)

API_BASE = "https://api.youversion.com/v1"

#: Locale → YouVersion bible id. Adding a locale is one line here; it is
#: deliberately not derived from `LOCALE_CODES`, because a UI language the
#: product speaks is not the same thing as a Bible edition somebody chose.
API_BIBLE_IDS: dict[str, int] = {
    "ru": 143,  # Новый Русский Перевод — modern, and what verse-of-the-day
    # already uses. Ends the split where two subsystems served
    # two different Russian Bibles.
    "de": 51,  # Luther 1912. Public domain and canonical for German
    # Protestants. Known cost: it renders διαθήκη as *Testament*
    # rather than *Bund* in most NT occurrences, so the glossary
    # must not try to override quoted Scripture.
    "uk": 188,  # Кулиш & Пулюй 1905 — the only Ukrainian edition the API
    # offers, and it is complete. Pre-1928 orthography
    # («сьвіт», «пастирь») is a real readability cost, accepted
    # because the alternative is no Ukrainian Scripture at all.
}

#: USFM book codes in the canonical 66-book order, aligned position-by-position
#: with `_BOOKS`. Zipping rather than hand-writing 66 slug→code pairs means one
#: list to get wrong instead of two — and `test_api_source.py` pins named pairs
#: so a reordering of either list fails loudly rather than quietly citing the
#: wrong book, which is the exact defect this module exists to end.
_USFM_ORDER: tuple[str, ...] = (
    "GEN",
    "EXO",
    "LEV",
    "NUM",
    "DEU",
    "JOS",
    "JDG",
    "RUT",
    "1SA",
    "2SA",
    "1KI",
    "2KI",
    "1CH",
    "2CH",
    "EZR",
    "NEH",
    "EST",
    "JOB",
    "PSA",
    "PRO",
    "ECC",
    "SNG",
    "ISA",
    "JER",
    "LAM",
    "EZK",
    "DAN",
    "HOS",
    "JOL",
    "AMO",
    "OBA",
    "JON",
    "MIC",
    "NAM",
    "HAB",
    "ZEP",
    "HAG",
    "ZEC",
    "MAL",
    "MAT",
    "MRK",
    "LUK",
    "JHN",
    "ACT",
    "ROM",
    "1CO",
    "2CO",
    "GAL",
    "EPH",
    "PHP",
    "COL",
    "1TH",
    "2TH",
    "1TI",
    "2TI",
    "TIT",
    "PHM",
    "HEB",
    "JAS",
    "1PE",
    "2PE",
    "1JN",
    "2JN",
    "3JN",
    "JUD",
    "REV",
)

SLUG_TO_USFM: dict[str, str] = {slug: code for (slug, _aliases), code in zip(_BOOKS, _USFM_ORDER, strict=True)}

#: Process-local, unbounded, never invalidated — Scripture does not change.
#: The pipeline quotes the same handful of verses across a course, so this
#: turns a per-verse network call into a per-verse-per-process one.
_cache: dict[tuple[str, str], str | None] = {}
_lock = threading.Lock()


def _usfm_ref(ref: BibleRef) -> str | None:
    book = SLUG_TO_USFM.get(ref.book)
    if book is None:
        return None
    if ref.verse_end is None:
        return f"{book}.{ref.chapter}.{ref.verse_start}"
    return f"{book}.{ref.chapter}.{ref.verse_start}-{book}.{ref.chapter}.{ref.verse_end}"


def fetch_verse(ref: BibleRef, locale: LocaleCode) -> str | None:
    """Canonical text for `ref` in `locale`, or `None` for any reason at all.

    `None` is not an error condition to handle upstream — it is the ordinary
    answer meaning "no canonical text", and the caller already falls back to
    the author's own quotation.
    """
    bible_id = API_BIBLE_IDS.get(locale)
    if bible_id is None:
        return None
    usfm = _usfm_ref(ref)
    if usfm is None:
        return None

    key = (locale, usfm)
    if key in _cache:
        return _cache[key]

    api_key = os.getenv("YOUVERSION_API_KEY")
    if not api_key:
        # No key in CI, preview and local development. Not worth a warning on
        # every quoted verse — the fallback is correct and visible.
        return None

    text: str | None = None
    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.get(
                f"{API_BASE}/bibles/{bible_id}/passages/{usfm}",
                headers={"X-YVP-App-Key": api_key},
            )
        if response.status_code == 200:
            content = response.json().get("content")
            if isinstance(content, str) and content.strip():
                text = " ".join(content.split())
        elif response.status_code != 404:
            # 404 means the verse is genuinely absent from this edition —
            # a versification difference, which is data rather than a fault.
            logger.info("Bible API %s for %s in %s", response.status_code, usfm, locale)
    except (httpx.HTTPError, ValueError):
        logger.info("Bible API unreachable for %s in %s", usfm, locale)
        return None  # Not cached: a transient outage must not poison the verse.

    with _lock:
        _cache[key] = text
    return text


__all__ = ["API_BIBLE_IDS", "SLUG_TO_USFM", "fetch_verse"]
