"""Verse of the Day service backed by the YouVersion Platform API.

Selects one of ~250 curated, doctrinally-neutral, evergreen passages by
day-of-year so every visitor sees the same verse on the same calendar
date. Fetches the actual text in the requested locale (BSB for English,
NRT for Russian) and caches per-day per-locale in process memory — at
most two YouVersion calls per Python process per day.

The YouVersion key is non-commercial-licensed. When ``YOUVERSION_API_KEY``
is unset (CI, local dev without setup), ``get_verse_of_the_day`` raises
``VerseOfTheDayUnavailable`` so the route can return 404 and the
frontend can quietly hide the card — never block the dashboard on this.
"""

from __future__ import annotations

import datetime as dt
import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

import httpx

from app.core.config import settings

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode

logger = logging.getLogger(__name__)

YOUVERSION_API_BASE = "https://api.youversion.com/v1"
# Bible IDs (verified 2026-05-14 via /v1/bibles?language_ranges[]=eng/rus):
#  * 3034 — Berean Standard Bible (public domain, modern English)
#  * 143  — Новый Русский Перевод (modern Russian)
# If we add more locales, extend this map; the route will respond 404 for
# any locale not represented here.
_BIBLE_ID_BY_LOCALE: dict[str, int] = {
    "en": 3034,
    "ru": 143,
}

# 250 well-known, evergreen passages covering salvation, hope, comfort,
# love, faith, wisdom, prayer, and perseverance. Chosen to be ecumenical
# (no denomination-specific proof texts) and to translate cleanly across
# every modern Bible. Each entry is in YouVersion's USFM book-code form
# (e.g. ``JHN.3.16``).
_VERSES: tuple[str, ...] = (
    # ── Gospels (40) ────────────────────────────────────────────────
    "MAT.5.3",
    "MAT.5.4",
    "MAT.5.5",
    "MAT.5.6",
    "MAT.5.7",
    "MAT.5.8",
    "MAT.5.9",
    "MAT.5.14",
    "MAT.5.16",
    "MAT.6.9",
    "MAT.6.33",
    "MAT.7.7",
    "MAT.7.12",
    "MAT.11.28",
    "MAT.16.24",
    "MAT.18.20",
    "MAT.22.37",
    "MAT.22.39",
    "MAT.28.19",
    "MAT.28.20",
    "MRK.10.27",
    "MRK.10.45",
    "MRK.11.24",
    "MRK.12.30",
    "LUK.1.37",
    "LUK.6.27",
    "LUK.6.31",
    "LUK.6.38",
    "LUK.9.23",
    "LUK.10.27",
    "LUK.12.32",
    "JHN.1.1",
    "JHN.3.16",
    "JHN.3.17",
    "JHN.8.32",
    "JHN.10.10",
    "JHN.13.34",
    "JHN.14.6",
    "JHN.14.27",
    "JHN.15.13",
    # ── Acts (5) ────────────────────────────────────────────────────
    "ACT.1.8",
    "ACT.2.21",
    "ACT.4.12",
    "ACT.16.31",
    "ACT.20.35",
    # ── Pauline epistles (50) ───────────────────────────────────────
    "ROM.1.16",
    "ROM.5.1",
    "ROM.5.8",
    "ROM.6.23",
    "ROM.8.1",
    "ROM.8.28",
    "ROM.8.31",
    "ROM.8.37",
    "ROM.8.38",
    "ROM.8.39",
    "ROM.10.9",
    "ROM.10.17",
    "ROM.12.1",
    "ROM.12.2",
    "ROM.12.12",
    "ROM.12.21",
    "ROM.15.13",
    "1CO.10.13",
    "1CO.13.4",
    "1CO.13.7",
    "1CO.13.13",
    "1CO.15.58",
    "1CO.16.13",
    "2CO.4.16",
    "2CO.4.17",
    "2CO.5.7",
    "2CO.5.17",
    "2CO.9.7",
    "2CO.12.9",
    "GAL.2.20",
    "GAL.5.22",
    "GAL.5.23",
    "GAL.6.9",
    "EPH.2.8",
    "EPH.2.10",
    "EPH.4.2",
    "EPH.4.32",
    "EPH.6.10",
    "PHP.1.6",
    "PHP.2.3",
    "PHP.4.4",
    "PHP.4.6",
    "PHP.4.7",
    "PHP.4.8",
    "PHP.4.13",
    "PHP.4.19",
    "COL.3.2",
    "COL.3.13",
    "COL.3.17",
    "COL.3.23",
    # ── 1-2 Thess / Pastorals / Philemon (10) ───────────────────────
    "1TH.5.16",
    "1TH.5.17",
    "1TH.5.18",
    "2TH.3.3",
    "1TI.4.12",
    "1TI.6.12",
    "2TI.1.7",
    "2TI.3.16",
    "TIT.3.5",
    "PHM.1.7",
    # ── Hebrews + General epistles (25) ─────────────────────────────
    "HEB.4.12",
    "HEB.4.16",
    "HEB.10.23",
    "HEB.11.1",
    "HEB.11.6",
    "HEB.12.1",
    "HEB.12.2",
    "HEB.13.5",
    "HEB.13.8",
    "JAS.1.2",
    "JAS.1.5",
    "JAS.1.17",
    "JAS.1.22",
    "JAS.4.7",
    "JAS.4.8",
    "JAS.5.16",
    "1PE.1.3",
    "1PE.3.15",
    "1PE.4.10",
    "1PE.5.6",
    "1PE.5.7",
    "2PE.3.9",
    "1JN.1.9",
    "1JN.3.1",
    "1JN.4.7",
    "1JN.4.8",
    "1JN.4.16",
    "1JN.4.18",
    "1JN.4.19",
    "1JN.5.4",
    # ── Revelation (4) ──────────────────────────────────────────────
    "REV.3.20",
    "REV.21.4",
    "REV.21.5",
    "REV.22.13",
    # ── Psalms (50) ─────────────────────────────────────────────────
    "PSA.1.1",
    "PSA.1.2",
    "PSA.4.8",
    "PSA.16.8",
    "PSA.16.11",
    "PSA.18.2",
    "PSA.19.1",
    "PSA.19.14",
    "PSA.20.4",
    "PSA.23.1",
    "PSA.23.4",
    "PSA.23.6",
    "PSA.27.1",
    "PSA.27.14",
    "PSA.28.7",
    "PSA.30.5",
    "PSA.32.8",
    "PSA.34.4",
    "PSA.34.8",
    "PSA.34.18",
    "PSA.37.4",
    "PSA.37.5",
    "PSA.37.7",
    "PSA.42.1",
    "PSA.42.11",
    "PSA.46.1",
    "PSA.46.10",
    "PSA.51.10",
    "PSA.55.22",
    "PSA.56.3",
    "PSA.62.1",
    "PSA.62.5",
    "PSA.84.10",
    "PSA.86.5",
    "PSA.90.12",
    "PSA.91.1",
    "PSA.91.2",
    "PSA.91.11",
    "PSA.94.19",
    "PSA.103.1",
    "PSA.103.12",
    "PSA.118.24",
    "PSA.119.11",
    "PSA.119.105",
    "PSA.121.1",
    "PSA.121.2",
    "PSA.121.7",
    "PSA.139.14",
    "PSA.139.23",
    "PSA.143.8",
    # ── Proverbs (20) ───────────────────────────────────────────────
    "PRO.3.5",
    "PRO.3.6",
    "PRO.3.9",
    "PRO.4.23",
    "PRO.10.12",
    "PRO.11.25",
    "PRO.15.1",
    "PRO.16.3",
    "PRO.16.9",
    "PRO.17.17",
    "PRO.17.22",
    "PRO.18.10",
    "PRO.18.21",
    "PRO.19.21",
    "PRO.22.6",
    "PRO.27.17",
    "PRO.29.25",
    "PRO.31.25",
    "PRO.31.26",
    "PRO.31.30",
    # ── Wisdom & Prophets (35) ──────────────────────────────────────
    "ECC.3.1",
    "ECC.3.11",
    "ECC.4.9",
    "ECC.4.12",
    "ECC.7.8",
    "ECC.11.5",
    "ECC.12.13",
    "ISA.9.6",
    "ISA.26.3",
    "ISA.40.8",
    "ISA.40.29",
    "ISA.40.31",
    "ISA.41.10",
    "ISA.41.13",
    "ISA.43.2",
    "ISA.43.18",
    "ISA.43.19",
    "ISA.53.5",
    "ISA.55.8",
    "ISA.55.9",
    "ISA.55.11",
    "ISA.58.11",
    "ISA.61.1",
    "JER.17.7",
    "JER.29.11",
    "JER.29.12",
    "JER.29.13",
    "JER.31.3",
    "JER.32.27",
    "JER.33.3",
    "LAM.3.22",
    "LAM.3.23",
    "EZK.36.26",
    "DAN.2.21",
    "DAN.10.19",
    # ── Torah & Historical books (15) ───────────────────────────────
    "GEN.1.1",
    "GEN.1.27",
    "GEN.28.15",
    "GEN.50.20",
    "EXO.14.14",
    "EXO.15.2",
    "EXO.20.12",
    "DEU.6.5",
    "DEU.31.6",
    "DEU.31.8",
    "JOS.1.7",
    "JOS.1.9",
    "JOS.24.15",
    "1CH.16.34",
    "2CH.7.14",
    # ── Job, Minor prophets (6) ─────────────────────────────────────
    "JOB.19.25",
    "MIC.6.8",
    "HAB.3.19",
    "ZEP.3.17",
    "ZEC.4.6",
    "MAL.3.10",
)


class VerseOfTheDayUnavailable(Exception):
    """Raised when the service cannot satisfy a request (no API key,
    YouVersion outage, unsupported locale). The route handler maps this
    to a 404; the frontend hides the card silently. Never user-facing.
    """


class VerseNotInBible(Exception):
    """Distinct from ``VerseOfTheDayUnavailable``: the upstream Bible
    simply doesn't carry this reference. Used to drive the
    Septuagint/Masoretic fallback walk for locales whose Psalm
    numbering doesn't match our catalog's (NRT in particular)."""


# Hebrew Psalm chapter → Septuagint chapter for the simple-offset
# range. Outside this range the mapping is non-injective (chapters
# 9-10, 114-116, 147 either combine or split), so we refuse those
# rather than serve a different verse. Catalog references in the
# "complex" range raise ``VerseNotInBible`` for Septuagint-numbered
# bibles, which triggers the walk-forward to the next clean entry.
_SEPTUAGINT_PSALM_OFFSET_RANGE = (11, 113, 117, 146)
_SEPTUAGINT_LOCALES = frozenset({"ru"})


def _remap_ref_for_locale(ref: str, locale: LocaleCode) -> str | None:
    """Translate a catalog (Hebrew-numbered) reference into the
    upstream-bible's numbering for the given locale.

    Returns ``None`` when the reference falls in a chapter where
    Hebrew↔Septuagint psalm splits/combines (Hebrew 9, 10, 114, 115,
    116, 147) — the caller treats that as "not in this bible" and
    advances. Everything else maps cleanly: 1-8 and 148-150 are
    identical across both numbering systems; 11-113 and 117-146 take
    a -1 offset for Septuagint-numbered bibles like NRT.
    """
    if locale not in _SEPTUAGINT_LOCALES:
        return ref
    if not ref.startswith("PSA."):
        return ref
    try:
        _, chapter_str, verse_str = ref.split(".", 2)
        chapter = int(chapter_str)
    except (ValueError, IndexError):
        return ref
    low_a, high_a, low_b, high_b = _SEPTUAGINT_PSALM_OFFSET_RANGE
    if 1 <= chapter <= 8 or 148 <= chapter <= 150:
        return ref
    if low_a <= chapter <= high_a or low_b <= chapter <= high_b:
        return f"PSA.{chapter - 1}.{verse_str}"
    # Complex chapters (Hebrew 9, 10, 114, 115, 116, 147) where the
    # split/combine boundary makes a clean per-verse remap impossible.
    return None


@dataclass(frozen=True)
class VerseOfTheDay:
    reference: str
    """Localized reference returned by YouVersion (e.g. ``John 3:16`` or
    ``От Иоанна 3:16``)."""

    text: str
    """Verse text, plain (no markup)."""

    version: str
    """Short translation abbreviation (``BSB``, ``NRT``)."""

    locale: LocaleCode
    """The locale this verse was rendered in (``en`` or ``ru``)."""

    date: str
    """ISO-8601 date this verse was selected for, in UTC. Two clients
    hitting near midnight UTC can briefly see different verses; in
    practice the cache is per-day per-locale and the bound is < 24 h."""


# (date, locale) -> VerseOfTheDay. Lock-guarded for the request burst
# right after a cold start; never bigger than a handful of entries.
_CACHE: dict[tuple[str, str], VerseOfTheDay] = {}
_CACHE_LOCK = threading.Lock()


def _pick_reference(date: dt.date) -> str:
    """Deterministic verse for a calendar day. Ordinal days since the
    Common Era epoch modulo the catalog size — everyone, everywhere,
    sees the same verse on a given UTC date."""
    return _VERSES[date.toordinal() % len(_VERSES)]


# Cap on how far we walk forward when a verse is missing in the target
# bible. Eight is plenty: a contiguous run of eight missing references
# across the curated catalog would mean something far worse than a
# Septuagint/Masoretic mismatch (more like the bible itself is dead),
# and at that point silent-hide is the right behaviour anyway.
_FALLBACK_WALK_CAP = 8


def _pick_reference_offset(date: dt.date, offset: int) -> str:
    """Pick the ``offset``-th-after-today reference. Wraps via modulo
    so the walk-forward fallback can't run off the end of the
    catalog. Together with ``_FALLBACK_WALK_CAP`` this makes the
    fallback bounded and deterministic for a given (date, locale)."""
    return _VERSES[(date.toordinal() + offset) % len(_VERSES)]


def _strip_html(html: str) -> str:
    """YouVersion ``content`` may include a single ``<p>`` wrapper and
    occasional ``<span>`` markers. We render scripture as plain prose in
    the card, so collapse to text. The verse references themselves never
    contain user-supplied markup, so a naive strip is safe."""
    import re

    text = re.sub(r"<[^>]+>", "", html)
    # Collapse whitespace runs (some YouVersion responses contain
    # newlines inside <p>) so the card renders as a single tidy line.
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _fetch_passage(api_key: str, bible_id: int, ref: str) -> tuple[str, str]:
    """Return ``(localized_reference, plain_text)`` from YouVersion.

    Wrapped here so tests can monkeypatch this single function.

    Raises ``VerseNotInBible`` when YouVersion returns 404 — the bible
    is fine, the reference just doesn't exist in this translation
    (typically a Psalm versification difference). Callers can walk
    forward in the catalog to find the next valid ref. Any other
    non-200 status raises ``VerseOfTheDayUnavailable`` (treated as a
    transient outage, not a content gap).
    """
    url = f"{YOUVERSION_API_BASE}/bibles/{bible_id}/passages/{ref}"
    try:
        with httpx.Client(timeout=8.0) as client:
            response = client.get(url, headers={"X-YVP-App-Key": api_key})
    except httpx.HTTPError:
        # Transport-level failure (timeout, connection refused, DNS) — the
        # call never produced a status. This is precisely the outage the
        # API-budget dashboard most needs to see, yet the per-call metric
        # below only fired once we had a response. Emit a fatal data point
        # (status_code=0 = "no response") before re-raising so an outage
        # registers. Metric failure must never mask the original error.
        try:
            from app.core.metrics import increment

            increment(
                "equip.youversion.api_calls_total",
                bible_id=str(bible_id),
                outcome="fatal",
                status_code="0",
            )
        except Exception:
            pass
        raise
    # Emit per-call API metric BEFORE the status branches so the dashboard
    # sees every call, not just the 200s. Tagged with bible_id (which
    # locale) + outcome (which budget bucket: 200 = ok, 404 = not_in_bible
    # which we walk past in the caller, 5xx = outage). Wrapped in
    # try/except so a metric failure cannot break VOD rendering.
    try:
        from app.core.metrics import increment

        outcome = (
            "success" if response.status_code == 200 else ("not_in_bible" if response.status_code == 404 else "fatal")
        )
        increment(
            "equip.youversion.api_calls_total",
            bible_id=str(bible_id),
            outcome=outcome,
            status_code=str(response.status_code),
        )
    except Exception:
        pass
    if response.status_code == 404:
        raise VerseNotInBible(f"YouVersion has no {ref} for bible {bible_id}")
    if response.status_code != 200:
        raise VerseOfTheDayUnavailable(f"YouVersion responded {response.status_code} for {ref} (bible {bible_id})")
    payload = response.json()
    reference = str(payload.get("reference") or "")
    content = str(payload.get("content") or "")
    if not reference or not content:
        raise VerseOfTheDayUnavailable("YouVersion response missing reference or content")
    return reference, _strip_html(content)


_VERSION_NAME = {3034: "BSB", 143: "NRT"}


def get_verse_of_the_day(locale: LocaleCode, *, today: dt.date | None = None) -> VerseOfTheDay:
    """Return the verse for the given locale and (UTC) calendar day.

    ``today`` is injectable for tests; production passes ``None`` to use
    ``datetime.datetime.now(dt.UTC).date()``. Raises
    ``VerseOfTheDayUnavailable`` if the API key is missing, the locale is
    unsupported, or YouVersion is unreachable.
    """
    if today is None:
        today = dt.datetime.now(dt.UTC).date()

    bible_id = _BIBLE_ID_BY_LOCALE.get(locale)
    if bible_id is None:
        raise VerseOfTheDayUnavailable(f"Unsupported locale: {locale!r}")

    api_key = settings.YOUVERSION_API_KEY.get_secret_value() if settings.YOUVERSION_API_KEY else None
    if not api_key:
        raise VerseOfTheDayUnavailable("YOUVERSION_API_KEY is not configured")

    date_iso = today.isoformat()
    cache_key = (date_iso, locale)

    cached = _CACHE.get(cache_key)
    if cached is not None:
        return cached

    # Septuagint/Masoretic Psalm numbering differs between Russian
    # NRT and our canonical-English (Hebrew-numbered) catalog. For the
    # simple-offset range we remap chapter X → X-1 so the content
    # matches what BSB returns for the same catalog reference;
    # complex split/combine boundaries (Hebrew 9-10, 114-116, 147)
    # raise ``VerseNotInBible`` so the walk advances to a clean entry.
    # The walk also fires on genuine 404s (verse missing from the
    # bible entirely). The deterministic offset means every client
    # lands on the same fallback for the same UTC day.
    last_not_in_bible: VerseNotInBible | None = None
    localized_ref: str | None = None
    text: str | None = None
    for offset in range(_FALLBACK_WALK_CAP):
        catalog_ref = _pick_reference_offset(today, offset)
        upstream_ref = _remap_ref_for_locale(catalog_ref, locale)
        if upstream_ref is None:
            last_not_in_bible = VerseNotInBible(
                f"{catalog_ref} falls in the complex Septuagint/Masoretic boundary for locale {locale!r}"
            )
            continue
        try:
            localized_ref, text = _fetch_passage(api_key, bible_id, upstream_ref)
            break
        except VerseNotInBible as exc:
            last_not_in_bible = exc
            continue
        except httpx.HTTPError as exc:
            # Don't pollute logs with a stack trace on the happy path of
            # "YouVersion blipped"; the route already maps this to 404.
            logger.warning("YouVersion request failed: %s", exc)
            raise VerseOfTheDayUnavailable("YouVersion request failed") from exc
    if localized_ref is None or text is None:
        # Catalog exhausted — every ref in the walk was missing. Logging
        # the last seen 404 helps spot catalog rot if it ever happens.
        logger.warning("VOTD walk cap exceeded for locale %s: %s", locale, last_not_in_bible)
        raise VerseOfTheDayUnavailable(
            f"No reference in catalog available in bible {bible_id}; last error: {last_not_in_bible}"
        )

    verse = VerseOfTheDay(
        reference=localized_ref,
        text=text,
        version=_VERSION_NAME.get(bible_id, ""),
        locale=locale,
        date=date_iso,
    )

    with _CACHE_LOCK:
        # Bound the cache: only ever keep entries for "today" — that's
        # at most one per locale, two total. Drop yesterday's entries
        # whenever we add today's. Tiny cost; no risk of unbounded growth.
        for k in list(_CACHE):
            if k[0] != date_iso:
                _CACHE.pop(k, None)
        _CACHE[cache_key] = verse

    return verse


def _reset_cache_for_tests() -> None:
    """Test-only helper. Importable by ``tests/test_verse_of_the_day.py``
    to start each case from a known state."""
    with _CACHE_LOCK:
        _CACHE.clear()
