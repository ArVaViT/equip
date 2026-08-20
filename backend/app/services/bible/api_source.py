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
on any problem — no key, timeout, 404, malformed body, and now a body that
parses but is not a verse. `post_substitute` treats `None` as "no canonical
text" and keeps the author's own quotation, which is the behaviour that was
already correct.

That last case is the one this module used to have no answer for. A 200 with
a well-formed JSON body was taken as Scripture and pasted into a reader's
page, and Куліш 1905 answers Psalm 23:1 with `Г осподь пастирь мій` — the
psalm's opening capital, set apart from the word it belongs to. See
`well_formed.malformed_fragment` for what is checked and, more to the point,
for what deliberately is not.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import TYPE_CHECKING

import httpx

from app.services.bible.books import _BOOKS
from app.services.bible.psalm_numbering import remap_psalm
from app.services.bible.well_formed import malformed_fragment

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode
    from app.services.bible.references import BibleRef

logger = logging.getLogger(__name__)

API_BASE = "https://api.youversion.com/v1"

#: Locale → YouVersion bible id. Adding a locale is one line here; it is
#: deliberately not derived from `LOCALE_CODES`, because a UI language the
#: product speaks is not the same thing as a Bible edition somebody chose.
#: Locales whose bundled file may stand in when the API cannot answer.
#: Only English qualifies: its file is complete and verified against the
#: reference. Russian's is misaligned and would quote the wrong book;
#: German and Ukrainian have no file at all.
TRUSTED_BUNDLE_LOCALES: frozenset[str] = frozenset({"en"})

API_BIBLE_IDS: dict[str, int] = {
    "ru": 143,  # Новый Русский Перевод — modern, and what verse-of-the-day
    # already uses. Ends the split where two subsystems served
    # two different Russian Bibles.
    "de": 2351,  # Elberfelder (bibelkommentare.de edition). Literal, which
    # is what a Bible school quoting a verse to study it needs,
    # and — the reason for the change — written in current
    # orthography.
    #
    # This was Luther 1912 (id 51) until an editor read the
    # German corpus and counted `daß` in 35 of 252 Daily
    # Challenge explanations, alongside `ward`, `gen Himmel`
    # and `Jesu Christo`. To a German reader that is not
    # biblical register; the 1996 reform abolished it, so it
    # reads as a spelling mistake — in the one part of the page
    # that is supposed to be authoritative. Verified against
    # the live API: Luther 1912 returns "daß er seinen
    # eingeborenen Sohn gab", this edition returns "dass".
    #
    # Hoffnung für alle (id 73) was the other candidate and is
    # the more familiar book in German free churches, but it
    # is a dynamic paraphrase — "Gott hat die Menschen so sehr
    # geliebt" for John 3:16 — and a course that teaches how to
    # read a verse closely cannot quote a translation that has
    # already done the reading.
    "en": 3034,  # Berean Standard Bible. English previously had no API
    # edition at all and fell through to the bundled KJV, which
    # is why 80 of 252 English explanations carry `spake`,
    # `saith`, `unto`, `thee` — Early Modern English inside a
    # product whose every other sentence is contemporary.
    # BSB is modern, close to the text, and freely licensed.
    "uk": 188,  # Кулиш & Пулюй 1905 — still the ONLY Ukrainian edition the
    # API offers (verified 2026-08-19: one result for `ukr`).
    # Its pre-1928 orthography is a genuine cost — 90 of 252
    # Ukrainian explanations carry `ї` inside words (`малолїток`,
    # `дїло`), 16 carry `сьв`. A Ukrainian reader does not see an
    # old translation; they see a broken one. There is nothing to
    # switch to, so this stays until the API offers Огієнко or
    # a modern edition, and it is the strongest argument for
    # asking for one.
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
    # ``JHN.3.14-15``, not ``JHN.3.14-JHN.3.15``. The fully-qualified form
    # reads like the obvious one and answers 404 for every range — which
    # meant every quotation spanning two verses fell back to the author's
    # own language. Verified against the live API on 2026-08-15: the short
    # form returns both verses joined, the long form returns nothing.
    return f"{book}.{ref.chapter}.{ref.verse_start}-{ref.verse_end}"


def fetch_verse(ref: BibleRef, locale: LocaleCode) -> str | None:
    """Canonical text for `ref` in `locale`, or `None` for any reason at all.

    `None` is not an error condition to handle upstream — it is the ordinary
    answer meaning "no canonical text", and the caller already falls back to
    the author's own quotation.
    """
    bible_id = API_BIBLE_IDS.get(locale)
    if bible_id is None:
        return None
    # Hebrew numbers in, this edition's numbers out. A Septuagint-numbered
    # bible does not refuse a Hebrew psalm reference — it answers a
    # different psalm, fluently, and nothing reports a problem. ``None``
    # means the two systems split that psalm and no honest mapping exists.
    localized = remap_psalm(ref, locale)
    if localized is None:
        return None
    usfm = _usfm_ref(localized)
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
                folded = " ".join(content.split())
                # The publisher answered, and the answer is not a verse.
                # Куліш 1905 comes back with the initial capital of a
                # psalm's first word set apart from the rest of it —
                # ``Г осподь пастирь мій`` — and that text was pasted
                # into a Ukrainian reader's page as Scripture, on a row
                # stored as ``ok``, because nothing looked at it.
                #
                # This is checked *here*, where the text enters the
                # process, rather than at substitution or in validation.
                # Here it is one fact about one string and every caller
                # already knows what ``None`` means; at substitution it
                # would guard one of the three callers and leave the
                # rest holding the same broken text; in validation it
                # would arrive as a verdict on the translation, which is
                # the wrong artifact — the model did nothing wrong — and
                # would park a whole question a reader could otherwise
                # answer.
                #
                # Not cached as text and not repaired: see
                # ``well_formed`` for why joining the halves is a
                # judgement a program cannot make.
                broken = malformed_fragment(folded, locale)
                if broken is None:
                    text = folded
                else:
                    logger.warning(
                        "verse_malformed usfm=%s locale=%s fragment=%r",
                        usfm,
                        locale,
                        broken,
                    )
        elif response.status_code != 404:
            # Anything that is not 200 or 404 is the service having a
            # moment — rate limiting, a bad gateway, an expired key — and
            # says nothing about whether this verse exists. Returning
            # without caching is the whole point: a 429 during a backfill
            # would otherwise mean "this verse has no text" for the rest
            # of the run, and every quotation of it would quietly fall
            # back to the author's language.
            logger.info("Bible API %s for %s in %s", response.status_code, usfm, locale)
            return None
        # 404 means the verse is genuinely absent from this edition — a
        # versification difference, which is data rather than a fault, and
        # worth remembering so we do not ask again.
    except (httpx.HTTPError, ValueError):
        logger.info("Bible API unreachable for %s in %s", usfm, locale)
        return None  # Not cached: a transient outage must not poison the verse.

    with _lock:
        _cache[key] = text
    return text


__all__ = ["API_BIBLE_IDS", "SLUG_TO_USFM", "fetch_verse"]
