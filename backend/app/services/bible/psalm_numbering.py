# ruff: noqa: RUF002, RUF003
# The edition names in the prose are Cyrillic because that is their name.
"""Hebrew and Septuagint number the Psalms differently, and the difference is silent.

A bible that follows the other system does not answer "no such psalm" —
it answers a *different psalm*, in fluent prose, with the right shape.
Ask a Septuagint-numbered edition for Psalm 23 and it returns "The earth
is the Lord's", which is Hebrew 24, and nothing anywhere reports a
problem.

The platform's references are Hebrew-numbered, because English editions
are. So every lookup into a Septuagint-numbered edition has to be
translated first, and every one that is not is a quiet misquotation.

This lived inside ``verse_of_the_day`` and covered exactly one surface.
Meanwhile ``bible/api_source`` — which serves the substitution layer,
and through it every quoted verse in every course and every Daily
Challenge explanation — asked the Russian edition for Hebrew numbers
directly. Checked on 2026-08-15: Psalm 23:1 in Russian came back as
"Господня земля и всё, что наполняет её". The shepherd psalm, quoted as
the earth being the Lord's, to every Russian reader.

The chapter rule is not enough
------------------------------
The first fix here subtracted one from the chapter across two bands, and
that is the rule everyone quotes. Measured against the live edition on
2026-08-16, it is wrong in three ways at once:

* **the verse moves too.** Hebrew 34:8 is not 33:8 but 33:9, because the
  superscription is unnumbered in Hebrew and numbered in the Slavic
  tradition. Ask for 33:8 and you get the previous line — again, fluent,
  plausible, and not what was cited.
* **the shift is not constant inside a psalm.** Psalm 18 verse 1 shifts
  by nothing and its other forty-nine verses by one.
* **agreeing on the chapter does not mean agreeing on the verse.** Psalm
  3 has the same number in both systems and its verses are still off by
  one; the old ``1-8`` identity band quoted every one of them wrongly.

So the mapping is a table, verse by verse, derived from the markers the
Synodal text carries for exactly this purpose — see
``scripts/derive_psalm_numbering.py``. A reference absent from the table
is one where the two systems agree: Psalms 1, 2, 148, 149 and 150.

The table also settles the psalms the band rule had to refuse. Hebrew 10
is not a separate psalm in the Slavic tradition — Hebrew 10:1 is Slavic
9:22 — and Hebrew 116 is split, its first verse landing at 114:1. Those
used to answer ``None``, which meant a Russian reader was shown the
author's untranslated verse instead.

Three systems, not two
----------------------
The chapter is not the only place editions disagree, and for a year this
module recorded only the chapter. There are three systems among the four
editions served here:

* **reference** — the English editions'. Neither the Septuagint's
  chapters nor the heading's verses. This is the system every reference
  on the platform is written in.
* **masoretic** — Elberfelder. English chapters, and the psalm's
  heading numbered as a verse of its own where it is long enough to be
  one.
* **septuagint** — НРТ. Both at once, which is why the table above maps
  chapter *and* verse and has always carried the heading shift for
  Russian.

The middle one is new here, and it was missing rather than decided: the
German and Ukrainian editions were probed in 2026-08 at every reference
where the *chapters* disagree, they answered like the English one, and
"not Septuagint" was read as "nothing to remap". Measured over the live
catalogue on 2026-08-22, four of the twelve psalms a reader can reach
were quoted in German at the wrong verse — "(Dem Vorsänger. Ein Psalm
von David.)" standing where the explanation beneath it discusses a plea
for mercy, and no psalm anywhere on the page. Ukrainian looks like the
same case and is not; see ``SUPERSCRIPTION_NUMBERING_LOCALES``, which is
where the difference is written down, and
``scripts/derive_psalm_superscription_verses.py``, which is where the
table comes from.

Which editions are which was measured, not assumed — see
``SEPTUAGINT_LOCALES``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Final

from app.services.bible.references import BibleRef

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode

_TABLE_PATH: Final = Path(__file__).resolve().parent / "data" / "psalm_hebrew_to_septuagint.json"
_SUPERSCRIPTION_PATH: Final = Path(__file__).resolve().parent / "data" / "psalm_superscription_verses.json"

#: Editions that number the Psalms the Septuagint way.
#:
#: Checked against the live API on 2026-08-15 at every reference where
#: the systems disagree, rather than inferred from the language. НРТ
#: answers Hebrew 23 with Hebrew 24's text and gives the shepherd psalm
#: at 22 — Septuagint. Luther 1912 and Куліш answer every probe the way
#: the Hebrew-numbered English edition does, so neither is remapped.
#:
#: The Ukrainian result is the reason this is measured: a Slavic edition
#: is not automatically Septuagint-numbered, and assuming it was would
#: have been reasonable, confident, and wrong.
SEPTUAGINT_LOCALES: Final[frozenset[str]] = frozenset({"ru"})

#: Editions that number a psalm's *heading* as a verse while keeping the
#: Hebrew chapter numbers.
#:
#: The chapter is not the only place two editions can disagree, and
#: ``SEPTUAGINT_LOCALES`` only ever recorded the chapter. German and
#: Ukrainian were checked against the live API on 2026-08-15 at every
#: reference where the *chapters* disagree, they matched the English
#: edition, and the conclusion drawn was that nothing about them needed
#: remapping. The verses were never asked about.
#:
#: Elberfelder disagrees. Measured over the live catalogue on
#: 2026-08-22: it answered Psalms 8:1, 19:1, 22:1 and 51:1 with the
#: heading and nothing else — four Daily Challenge questions whose
#: explanation discusses a verse the reader was never shown. Confirmed
#: against the live API the same day at the shifted references: 8:2 is
#: "HERR, unser Herr, wie herrlich ist dein Name", 19:2 "Die Himmel
#: erzählen die Herrlichkeit Gottes", 22:2 "Mein Gott, mein Gott, warum
#: hast du mich verlassen", 51:3 "Sei mir gnädig, o Gott" — the four
#: verses those questions are about, at the four numbers this table
#: predicts.
#:
#: **Ukrainian is not here, and that was worth four calls to find out.**
#: Куліш looks like it should be: its Psalm 51:1 also opens with the
#: choirmaster's rubric. But it opens with the rubric *and then the
#: verse*, and asked for 51:3 it answers "Знаю бо переступи мої" — the
#: third verse in English numbering, not the first. It merges the
#: heading into verse 1 rather than numbering it, so its numbers are
#: the platform's own and shifting them would quote the wrong verse in
#: nine psalms to fix the punctuation of nine others. What is wrong
#: with those nine is a different defect and is written up as one; see
#: ``api_source._without_edition_heading``.
#:
#: Russian is not listed because it is already covered: the Septuagint
#: table maps chapter and verse together, and the Slavic numbering it
#: maps into is Masoretic in its verses. Listing it here would shift
#: those references twice.
SUPERSCRIPTION_NUMBERING_LOCALES: Final[frozenset[str]] = frozenset({"de"})


@lru_cache(maxsize=1)
def _table() -> dict[str, tuple[int, int]]:
    raw: dict[str, str] = json.loads(_TABLE_PATH.read_text(encoding="utf-8"))
    parsed: dict[str, tuple[int, int]] = {}
    for hebrew, septuagint in raw.items():
        chapter, verse = septuagint.split(".")
        parsed[hebrew] = (int(chapter), int(verse))
    return parsed


def _lookup(chapter: int, verse: int) -> tuple[int, int]:
    """Where ``chapter:verse`` lands, identical numbering if unlisted."""
    return _table().get(f"{chapter}.{verse}", (chapter, verse))


@lru_cache(maxsize=1)
def _superscription_table() -> dict[int, int]:
    raw: dict[str, int] = json.loads(_SUPERSCRIPTION_PATH.read_text(encoding="utf-8"))
    return {int(chapter): offset for chapter, offset in raw.items()}


def superscription_verses(chapter: int) -> int:
    """How many verses this psalm's heading occupies where it is numbered.

    Nought for the psalms that carry no heading and for the psalms whose
    heading shares verse 1 with the opening line — 88 of the 150, which
    is why nine of the twelve psalms in the live catalogue were wrong and
    three were right. See ``scripts/derive_psalm_superscription_verses``
    for where the table comes from and why it is derived rather than
    typed.
    """
    return _superscription_table().get(chapter, 0)


@lru_cache(maxsize=1)
def _inverse_table() -> dict[str, tuple[tuple[int, int], ...]]:
    """The same table read backwards: Septuagint numbers to Hebrew ones.

    Needed because remapping is not only something we do on the way
    *out*. A lesson written in Russian carries the numbers a Synodal
    Bible prints — that is what its author was reading — and everything
    that compares it to a German or English translation has to know
    which system it started in.

    All but one entry inverts cleanly. Hebrew 13:5 and 13:6 both land on
    Septuagint 12:6, so that one Septuagint verse answers with two
    Hebrew ones and callers get a tuple rather than a single pair. A
    caller that has to pick one is asking a question the editions do not
    answer.
    """
    inverse: dict[str, list[tuple[int, int]]] = {}
    for hebrew, septuagint in _table().items():
        chapter, verse = hebrew.split(".")
        inverse.setdefault(f"{septuagint[0]}.{septuagint[1]}", []).append((int(chapter), int(verse)))
    return {key: tuple(sorted(value)) for key, value in inverse.items()}


def _hebrew_candidates(chapter: int, verse: int) -> tuple[tuple[int, int], ...]:
    """Where a Septuagint ``chapter:verse`` lands in Hebrew numbering."""
    return _inverse_table().get(f"{chapter}.{verse}", ((chapter, verse),))


def remap_psalm(ref: BibleRef, locale: LocaleCode | str) -> BibleRef | None:
    """Return ``ref`` as ``locale``'s edition numbers it.

    ``None`` means "this edition cannot be asked for this reference":
    the only remaining case is a range whose ends fall in two different
    psalms once remapped, which happens where the Slavic tradition
    splits a Hebrew psalm and no single reference can name the span. The
    caller treats that the way it treats any other absence — keep the
    author's own quotation, or move to the next candidate.

    Everything that is not a psalm, and every locale that numbers them
    the way the reference is written, passes through untouched.
    """
    if ref.book != "psalms":
        return ref

    if locale in SUPERSCRIPTION_NUMBERING_LOCALES:
        # Same psalm, same order, one heading in front of it. A range
        # moves as a whole: both ends shift by the same amount, so a
        # range cannot be split by this and never returns ``None``.
        offset = superscription_verses(ref.chapter)
        if not offset:
            return ref
        return BibleRef(
            book=ref.book,
            chapter=ref.chapter,
            verse_start=ref.verse_start + offset,
            verse_end=None if ref.verse_end is None else ref.verse_end + offset,
        )

    if locale not in SEPTUAGINT_LOCALES:
        return ref

    chapter, verse_start = _lookup(ref.chapter, ref.verse_start)

    verse_end: int | None = None
    if ref.verse_end is not None:
        end_chapter, verse_end = _lookup(ref.chapter, ref.verse_end)
        if end_chapter != chapter:
            return None

    return BibleRef(book=ref.book, chapter=chapter, verse_start=verse_start, verse_end=verse_end)


def renumber_between(
    ref: BibleRef,
    *,
    source_locale: LocaleCode | str,
    target_locale: LocaleCode | str,
) -> tuple[BibleRef, ...]:
    """``ref`` as printed by ``source_locale``, in ``target_locale``'s numbers.

    ``remap_psalm`` answers one direction only — Hebrew numbers into the
    edition the reader holds — because every caller it was written for
    starts from the platform's own Hebrew-numbered references. Comparing
    two *translations* of the same lesson does not: the source there is
    whatever the author was reading, and a Russian author was reading
    Synodal.

    Found on 2026-08-19 in ``chapter_block/content`` of entity
    ``c18954e1-6652-4fa8-8062-538483ce789b``: a Russian source cites
    Пс. 109:1, the German translation correctly prints Ps. 110,1 as
    rule 2a of the system prompt asks, and a check comparing bare
    numbers called the reference lost. The German row sat at
    ``needs_review`` — and because ``executor`` skips a parked row whose
    source has not changed, it would have sat there for good — while the
    English and Ukrainian rows, which kept 109:1 and are therefore
    pointing at the wrong psalm, were marked ``ok``.

    Returns every number pair the target edition may legitimately print.
    That is normally one; it is two where the Septuagint verse answers
    to two Hebrew ones (see ``_inverse_table``), and none where the
    range straddles a split psalm and no single reference names the span
    — the same "this edition cannot be asked for this reference" that
    ``remap_psalm`` signals with ``None``.
    """
    if ref.book != "psalms":
        return (ref,)

    if _numbering_system(source_locale) == _numbering_system(target_locale):
        # Two editions in the same system print the same numbers,
        # whatever else differs between them.
        return (ref,)

    out: list[BibleRef] = []
    for as_written in _as_reference_numbering(ref, source_locale):
        mapped = remap_psalm(as_written, target_locale)
        if mapped is not None and mapped not in out:
            out.append(mapped)
    return tuple(out)


def _numbering_system(locale: LocaleCode | str) -> str:
    """Which of the three ways this edition numbers the Psalms.

    ``reference`` is the platform's own — the English editions', which
    number neither the Septuagint's chapters nor the heading's verses.
    """
    if locale in SEPTUAGINT_LOCALES:
        return "septuagint"
    if locale in SUPERSCRIPTION_NUMBERING_LOCALES:
        return "masoretic"
    return "reference"


def _as_reference_numbering(ref: BibleRef, locale: LocaleCode | str) -> tuple[BibleRef, ...]:
    """``ref``, as printed by ``locale``, read back into the platform's
    own reference numbering. The inverse of ``remap_psalm``.

    Empty where the edition's number names something the reference
    system does not number at all — a psalm's heading, which is verse 1
    in a Masoretic edition and no verse anywhere in an English one.
    """
    system = _numbering_system(locale)
    if system == "reference":
        return (ref,)

    if system == "masoretic":
        offset = superscription_verses(ref.chapter)
        if not offset:
            return (ref,)
        if ref.verse_start - offset < 1:
            return ()
        return (
            BibleRef(
                book=ref.book,
                chapter=ref.chapter,
                verse_start=ref.verse_start - offset,
                verse_end=None if ref.verse_end is None else ref.verse_end - offset,
            ),
        )

    starts = _hebrew_candidates(ref.chapter, ref.verse_start)
    if ref.verse_end is None:
        return tuple(BibleRef(book=ref.book, chapter=chapter, verse_start=verse) for chapter, verse in starts)

    ends = _hebrew_candidates(ref.chapter, ref.verse_end)
    return tuple(
        BibleRef(book=ref.book, chapter=start_chapter, verse_start=start_verse, verse_end=end_verse)
        for start_chapter, start_verse in starts
        for end_chapter, end_verse in ends
        if start_chapter == end_chapter and end_verse >= start_verse
    )


def remap_usfm(ref: str, locale: LocaleCode | str) -> str | None:
    """The same rule, for callers holding a USFM string (``PSA.23.1``).

    The verse-of-the-day walk speaks USFM end to end and never builds a
    ``BibleRef``. It had its own copy of this logic — correct, and one
    edit away from disagreeing with the copy that serves everything
    else about which psalms are which.
    """
    if locale not in SEPTUAGINT_LOCALES or not ref.startswith("PSA."):
        return ref
    parts = ref.split(".")
    if len(parts) < 3:
        return ref
    try:
        chapter = int(parts[1])
        verses = [int(piece) for piece in parts[2].split("-")]
    except ValueError:
        return ref
    if not verses:
        return ref

    mapped = [_lookup(chapter, verse) for verse in verses]
    if len({chapter for chapter, _ in mapped}) > 1:
        return None
    return f"PSA.{mapped[0][0]}." + "-".join(str(verse) for _, verse in mapped)


__all__ = [
    "SEPTUAGINT_LOCALES",
    "SUPERSCRIPTION_NUMBERING_LOCALES",
    "remap_psalm",
    "remap_usfm",
    "renumber_between",
    "superscription_verses",
]
