"""Find copyright-management information, hide it from the translator, put it back.

Shape borrowed wholesale from ``app.services.bible.substitution``, including
the constraints its history paid for:

* The marker prefix is **not a word in any language the platform serves.**
  ``VERSE_`` was, and a model asked for Ukrainian obligingly translated it;
  production still holds a row reading ``ВЕРС_0c0214d57ac3a0bb`` where
  Scripture belongs. ``EQA`` is a word in none of ru / en / de / uk.
* ASCII, identifier-shaped, no NUL byte and no Unicode private-use
  character. Postgres ``TEXT`` rejects the first and editors mangle the
  second.
* A random hex suffix per occurrence, so several spans round-trip
  independently and a marker cannot be forged from user content.
* **Never swallow a tag.** Matching happens only on the text between tags,
  so a span can never contain ``<`` and the tag census in
  ``translation.validation`` sees exactly what it saw before.

What counts as copyright-management information
-----------------------------------------------

§ 1202(c) lists it: the title, the author, the copyright owner, terms and
conditions of use, identifying numbers, and the information conveyed in a
notice. In the kind of text a Bible-school teacher actually writes, that is
five shapes, and each pattern below is one of them.

Every pattern is anchored. The unanchored version of the fourth matched 39
rows of the production corpus and was wrong about all 39 — see the package
docstring for the counts. A rule that freezes ordinary prose in the source
language across four languages is not a cautious rule; it is a different bug.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Final

#: Not a word in ru, en, de or uk — the one property the marker must have.
ATTRIBUTION_MARKER_PREFIX: Final[str] = "EQA"

#: What a marker looks like once minted, for anyone matching them elsewhere.
ATTRIBUTION_MARKER_RE: Final[re.Pattern[str]] = re.compile(r"EQA[0-9a-f]+")

#: The Scripture marker. A fragment holding one is left alone: the two
#: families must stay disjoint, because each is restored by looking for its
#: own marker in the text, and a marker nested inside another span is not in
#: the text when its turn comes.
_SCRIPTURE_MARKER_RE: Final[re.Pattern[str]] = re.compile(r"(?:EQV|VERSE_)[0-9a-f]+")

#: Everything from one ``<`` to the matching ``>``. Splitting on it and
#: scanning only what falls between the matches is what guarantees a span
#: never contains markup.
_TAG_RE: Final[re.Pattern[str]] = re.compile(r"<[^>]*>")

#: Opens a line. Inside a text run the line may also be the whole run.
_BOL: Final[str] = r"(?:\A|(?<=\n))[ \t]*"

#: Runs to the end of the line, or to the end of the run.
_EOL: Final[str] = r"[^\n]*"

#: A title in quotes, in any of the four languages' marks.
_QUOTED_TITLE: Final[str] = r"(?:«[^»\n]{1,200}»|“[^”\n]{1,200}”|„[^“”\n]{1,200}[“”]|\"[^\"\n]{1,200}\")"

#: A year, which is what turns "from the book" into a citation.
_YEAR: Final[str] = r"\b(?:1[5-9]\d\d|20\d\d)\b"

#: 1. A notice, wherever it sits. ``©`` and ``Copyright`` are unambiguous
#:    enough that they need no anchor — nothing else in a lesson says them.
_NOTICE: Final[str] = (
    r"(?:©|\((?:c|C)\)\s*\d{4}|\bCopyright\b|\bAll [Rr]ights [Rr]eserved\b"
    r"|\bAlle Rechte vorbehalten\b|\bUrheberrecht\b"
    r"|Все права защищ\w*|Усі права застережен\w*|Усі права захищен\w*)"
)

#: 2. An identifying number, in § 1202(c)(3)'s sense.
_ISBN: Final[str] = r"\bISB[NM]?\b[\s:-]*(?:97[89][\s-]?)?[\dXx][\dXx\s-]{7,20}"

#: 3. A source label opening a line: "Источник: …", "Quelle: …".
_SOURCE_LABEL: Final[str] = (
    r"(?:Источник|Источники|Source|Sources|Quelle|Quellen|Джерело|Джерела"
    r"|Взято из|Взято з|Печатается по|Друкується за|Перепечатано|Reprinted from"
    r"|Abdruck aus|Отрывок из|Уривок з|Excerpt from|Auszug aus)"
)

#: 4. A citation opening a line — and carrying a title or a year, which is
#:    the whole difference between a citation and the words "from the book".
_FROM_THE_BOOK: Final[str] = r"(?:Из книги|Из кн\.|З книги|З кн\.|From the book|Aus dem Buch)"

#: 5. A credit after a dash at the end of a run: "— John Stott, «The Cross
#:    of Christ», 1986." The quoted title is what makes it a credit rather
#:    than a sentence that happens to start with a dash.
_DASH_CREDIT: Final[str] = rf"[—–]\s*[^\n]{{0,160}}{_QUOTED_TITLE}[^\n]{{0,80}}"

#: Ordered widest-first so an overlapping notice wins over a bare ISBN.
_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    # A whole line carrying a notice, so "© 2019 Тимоти Келлер. Перевод …"
    # travels as one piece rather than as a symbol with translated prose
    # around it.
    re.compile(rf"{_BOL}{_EOL}?{_NOTICE}{_EOL}"),
    re.compile(rf"{_BOL}{_SOURCE_LABEL}\s*[:—–-]{_EOL}"),
    re.compile(rf"{_BOL}{_FROM_THE_BOOK}\b(?=[^\n]*(?:{_QUOTED_TITLE}|{_YEAR})){_EOL}"),
    re.compile(_ISBN),
    re.compile(rf"{_DASH_CREDIT}(?=\s*\Z)"),
)


@dataclass(frozen=True, slots=True)
class AttributionSpan:
    """One fragment of copyright-management information, and its stand-in."""

    marker: str
    #: The source text, byte for byte. Restored unchanged — that is the point.
    text: str


def _marker_token() -> str:
    """Mint a sentinel the model will copy through rather than translate.

    ``EQA`` plus 16 hex characters. See the module docstring for why each of
    those three properties is there; every one of them is a bug that has
    already happened to the Scripture markers.
    """
    return f"{ATTRIBUTION_MARKER_PREFIX}{secrets.token_hex(8)}"


def _spans_in(run: str) -> list[tuple[int, int]]:
    """Non-overlapping ``(start, end)`` of every attribution in one text run."""
    found: list[tuple[int, int]] = []
    for pattern in _PATTERNS:
        for match in pattern.finditer(run):
            start, end = match.start(), match.end()
            fragment = run[start:end]
            if not fragment.strip():
                continue
            # A fragment holding a verse marker is left alone: see the note
            # on ``_SCRIPTURE_MARKER_RE``. Rare, and the conservative
            # outcome is the behaviour that was there before this module.
            if _SCRIPTURE_MARKER_RE.search(fragment):
                continue
            if any(start < prior_end and prior_start < end for prior_start, prior_end in found):
                continue
            found.append((start, end))
    return sorted(found)


def find_attributions(text: str) -> list[str]:
    """Every fragment this module would protect, in order. Reading only.

    Used by the tests and by anything that wants to ask "is there anything
    here to protect" without rewriting the text.
    """
    fragments: list[str] = []
    # ``re.split`` on a pattern with no capturing group yields only the text
    # between the matches, which is precisely the text this may look at.
    for run in _TAG_RE.split(text):
        fragments.extend(run[start:end] for start, end in _spans_in(run))
    return fragments


def pre_substitute(text: str) -> tuple[str, list[AttributionSpan]]:
    """Replace every attribution with a marker. Returns the new text and the spans.

    Only the text between tags is scanned, so a tag, an attribute and a URL
    inside an ``href`` are all untouchable by construction rather than by a
    rule somebody has to keep — and the tag census that parks a mangled row
    sees the same tags it saw before.
    """
    spans: list[AttributionSpan] = []
    pieces = _TAG_RE.split(text)
    tags = _TAG_RE.findall(text)
    out: list[str] = []
    for index, run in enumerate(pieces):
        rewritten: list[str] = []
        cursor = 0
        for start, end in _spans_in(run):
            span = AttributionSpan(marker=_marker_token(), text=run[start:end])
            spans.append(span)
            rewritten.append(run[cursor:start])
            rewritten.append(span.marker)
            cursor = end
        rewritten.append(run[cursor:])
        out.append("".join(rewritten))
        if index < len(tags):
            out.append(tags[index])
    return "".join(out), spans


def post_substitute(text: str, spans: list[AttributionSpan]) -> str:
    """Put every attribution back, character for character.

    No localization, no re-pointing, no normalization. A copyright notice is
    the one string in this pipeline that must come out of it identical to the
    way it went in — which is the whole of § 1202(b) in one sentence.

    A marker the model dropped cannot be restored: there is nowhere to put
    it. The provider counts those and says so out of band
    (``TranslationResult.lost_attribution``), and the executor parks the row
    rather than storing a translation with the notice missing.
    """
    for span in spans:
        text = text.replace(span.marker, span.text)
    return text
