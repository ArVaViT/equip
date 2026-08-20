"""Pre/post-translation Bible verse substitution.

The translation pipeline calls these around each Gemini request that
carries HTML content. The point: the teacher writes a Russian Synodal
quote, but an English-locale student should see the canonical KJV text
— not Gemini's paraphrase, not the source-locale verse.

Algorithm (``pre_substitute``):

1. Walk every ``<blockquote>...</blockquote>`` in the source HTML.
2. Look at the ~80 chars immediately following the closing ``</blockquote>``
   for a parenthesized reference (``(Деян. 20:28)`` / ``(Acts 1:8)``).
3. Parse the reference. If it doesn't resolve to a known book, leave alone.
4. Look up the canonical text in the ``source_locale``. If we don't have
   it bundled, leave alone.
5. Compare the author's blockquote text (HTML-stripped, whitespace-folded)
   to the canonical text using ``difflib.SequenceMatcher``. If
   similarity ≥ 0.80, this is a canonical quote — replace the
   blockquote's inner text with a marker token. Track the substitution.
6. Markers are plain-ASCII ``VERSE_<random hex>`` strings. They survive
   JSON encoding to Gemini, the Postgres ``TEXT`` column they end up
   stored in (NUL bytes are forbidden there — that was the v1 bug
   that left raw markers visible in students' EN view), and the
   prompt's "preserve placeholders verbatim" rule which the model
   honours for identifier-shaped tokens.

``post_substitute`` is the inverse: replace each marker in the
translated HTML with the canonical ``target_locale`` text. If the
target-locale lookup fails (e.g. an exotic verse missing from the
bundled file), restore the original blockquote text instead — better
than leaving a marker visible in the rendered output.

The canonical text arrives **bare**: an edition prints Scripture, not
somebody's quotation of it, so there are no quotation marks around it.
The author's marks, meanwhile, were part of the span the marker ate. Put
back naively, that is a verse presented two ways in one lesson — the
recognised quotation restored without marks, the unrecognised one a few
lines down still carrying the author's — which is what a bilingual
editor found across the whole of generation 8: Russian source 18 of 18
featured verses quoted, German 5, Ukrainian 5, English 6. So
``pre_substitute`` also records *whether the author quoted*, and
``post_substitute`` re-wraps the canonical text in the marks the target
language sets a quotation in. See ``_swallowed_quotes`` for what counts
as quoted and why one mark is not enough.

"Bare" needs one qualification, and it is the second half of what the
editor found. An edition that sets direct speech in quotation marks
prints a *fragment* of one when the speech runs across a verse boundary:
the Berean Standard Bible answers a request for Acts 1:8 with
``But you will receive power … to the ends of the earth.”`` — a closing
mark whose opening is in verse 7. Of the four editions quoted here, only
the English one does this (verified against the live API on 2026-08-20),
which is precisely why the English column was the one with blockquotes
that open without a mark and close with one. ``_drop_unpaired_edge_mark``
removes it, and only where "unpaired" is provable rather than guessed.

Why ≥ 0.80: SequenceMatcher tolerates minor punctuation/hyphenation
differences (em-dash variants, ё vs е, smart quotes, "the" / "ye")
without false-matching paraphrases. We tested empirically on the Acts
course's blockquotes — author copy-pasted Synodal hits ≥ 0.95;
paraphrases land below 0.6.
"""

from __future__ import annotations

import logging
import re
import secrets
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Final

from app.core.sanitize import html_to_plain_text
from app.schemas.locale import QUOTATION_MARKS
from app.services.bible.api_source import API_BIBLE_IDS, TRUSTED_BUNDLE_LOCALES, fetch_verse
from app.services.bible.books import display_book_name
from app.services.bible.psalm_numbering import remap_psalm
from app.services.bible.references import BibleRef, ParsedReference, parse_references
from app.services.bible.store import lookup

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode

logger = logging.getLogger(__name__)


# Match a blockquote and capture its inner text + the position of the
# closing tag so we can scan for an adjacent reference.
_BLOCKQUOTE_PATTERN = re.compile(
    r"<blockquote\b[^>]*>(?P<inner>.*?)</blockquote>",
    re.IGNORECASE | re.DOTALL,
)

# How far past the closing </blockquote> to look for "(Acts 1:8)".
# Most academic prose puts the reference immediately after; 120 chars
# leaves room for a small leading phrase like " — see also " before
# the parens. Going much wider invites false matches.
_REFERENCE_LOOKAHEAD = 120

# Similarity threshold between the author's blockquote text and the
# canonical source-locale verse. Below this we assume the author
# paraphrased and leave the quote alone.
_SIMILARITY_THRESHOLD = 0.80


@dataclass(frozen=True, slots=True)
class Substitution:
    """One verse substitution recorded by ``pre_substitute`` and consumed
    by ``post_substitute``. ``marker`` is the ASCII ``VERSE_<hex>``
    sentinel that replaces the blockquote's inner text in the markered
    HTML; ``ref`` points at the canonical Bible passage;
    ``original_inner`` is the author's text (stripped of HTML), kept
    for safe fallback when the target locale's lookup misses;
    ``ref_tail`` is the parenthesized reference text that lived
    immediately after the verse (e.g. ``(Matt. 28:19).``) and is
    re-localized by ``post_substitute`` so a Russian reader sees
    ``(Матф. 28:19).`` instead of the source-locale form.

    ``opening_quote_lost`` / ``closing_quote_lost`` say that the author
    presented this verse as a quotation and that the mark on that side
    went into the marker with the verse. They are the two halves of one
    answer, and they are answered separately because the marks do not
    always fall on the same side of the span: an author who wrote
    ``«…до края земли (Деян. 1:8)»`` put the opening mark inside the
    replaced text and the closing mark after the citation, where it
    survives the round trip untouched. Restoring both would give that
    verse two closing marks. Both default to ``False``, so a
    ``Substitution`` built by hand — or unpickled from a queue written by
    the previous version — adds nothing, which is exactly the old
    behaviour."""

    marker: str
    ref: BibleRef
    original_inner: str
    ref_tail: str = ""
    opening_quote_lost: bool = False
    closing_quote_lost: bool = False


def _strip_html(html: str) -> str:
    """Crude HTML → plain text. Sufficient for similarity comparison.

    The tag pass lives in ``core.sanitize`` now — one implementation
    for the three places that read prose out of markup.
    """
    return html_to_plain_text(html)


def _normalize_for_compare(s: str) -> str:
    """Fold case and replace known-confusable punctuation so that
    SequenceMatcher's edit-distance is dominated by real word changes,
    not stylistic variants."""
    s = s.lower()
    # Smart quotes / em-dashes / non-breaking spaces → plain.
    table = str.maketrans(
        {
            "«": '"',
            "»": '"',
            "“": '"',
            "”": '"',
            "‘": "'",
            "’": "'",
            "—": "-",
            "–": "-",
            "−": "-",
            "\xa0": " ",
            "ё": "е",
            "Ё": "е",
        }
    )
    s = s.translate(table)
    return " ".join(s.split())


# ---------------------------------------------------------------------------
# Did the author quote this?
# ---------------------------------------------------------------------------

# Marks that can open a quotation, and marks that can close one. ``“``
# and ``‘`` are in both sets deliberately: English opens with them and
# German closes with them, and this layer reads text written in four
# languages by authors who mix the conventions freely.
_OPENING_MARKS: Final[frozenset[str]] = frozenset("\"'«„“‘‚")
_CLOSING_MARKS: Final[frozenset[str]] = frozenset("\"'»“”’‘")

# The same, minus the single marks. An apostrophe is a single mark and a
# genitive both, and no rule that *deletes* a character may be allowed to
# read ``the disciples'`` as half a quotation.
_DOUBLE_OPENING: Final[frozenset[str]] = frozenset('"«„“')
_DOUBLE_CLOSING: Final[frozenset[str]] = frozenset('"»“”')
_DOUBLE_MARKS: Final[frozenset[str]] = _DOUBLE_OPENING | _DOUBLE_CLOSING

# Punctuation that may stand between a quotation mark and the words it
# encloses. Russian sets the full stop outside the closing mark
# (``«…земли».``), English inside it (``"…earth."``), and a citation
# brings its own comma; stepping over these is what lets one rule read
# both conventions.
_EDGE_PUNCTUATION: Final[str] = ".,;:!?…"

# Elements that end a line of reading. A quotation mark on the far side
# of ``</p>`` belongs to the previous paragraph, not to this verse — and
# treating it as this verse's mark is how a restored quotation would
# quietly lose its opening or gain a third. Inline elements (``<em>``,
# ``<strong>``, ``<a>``) stay transparent: ``«<em>`` still reads as ``«``.
_BLOCK_ELEMENTS: Final[frozenset[str]] = frozenset(
    {
        "address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt",
        "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6",
        "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section", "table",
        "tbody", "td", "tfoot", "th", "thead", "tr", "ul",
    }
)  # fmt: skip

_TAG_NAME = re.compile(r"</?([A-Za-z][A-Za-z0-9]*)")

# How far outside the replaced span to look for a mark that survived it.
# The only thing that legitimately sits between a verse and its closing
# quote is the citation, and the longest of those is some forty
# characters; this leaves room for the markup around it and still stops
# well short of the next sentence.
_QUOTE_EDGE_WINDOW: Final[int] = 240


def _is_block_tag(tag: str) -> bool:
    name = _TAG_NAME.match(tag)
    return name is not None and name.group(1).lower() in _BLOCK_ELEMENTS


def _visible_before(text: str, *, skip_punctuation: bool) -> str:
    """The last character of ``text`` a reader actually sees, or ``""``.

    Whitespace and inline markup are transparent — ``«</em> `` ends, to a
    reader, in ``«``. A block element, an unterminated tag, or running
    out of text all answer ``""``: we are no longer reading the same line
    of prose, and "no mark here" is the answer that changes nothing.
    """
    index = len(text) - 1
    while index >= 0:
        char = text[index]
        if char.isspace():
            index -= 1
        elif char == ">":
            opened = text.rfind("<", 0, index)
            if opened == -1 or _is_block_tag(text[opened : index + 1]):
                return ""
            index = opened - 1
        elif skip_punctuation and char in _EDGE_PUNCTUATION:
            index -= 1
        else:
            return char
    return ""


def _visible_after(text: str, *, skip_citation: bool) -> str:
    """The first character of ``text`` a reader actually sees, or ``""``.

    ``skip_citation`` steps over the reference that follows a verse —
    sentence punctuation and one parenthesized group — because an
    author's closing mark falls after ``(Деян. 1:8)`` about as often as
    before it, and both spellings mean the same thing to a reader.
    """
    index = 0
    parenthesis_skipped = False
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
        elif char == "<":
            closed = text.find(">", index)
            if closed == -1 or _is_block_tag(text[index : closed + 1]):
                return ""
            index = closed + 1
        elif skip_citation and char in _EDGE_PUNCTUATION:
            index += 1
        elif skip_citation and char == "(" and not parenthesis_skipped:
            closed = text.find(")", index)
            if closed == -1:
                return ""
            index = closed + 1
            parenthesis_skipped = True
        else:
            return char
    return ""


def _swallowed_quotes(replaced: str, before: str, after: str) -> tuple[bool, bool]:
    """Which of the author's quotation marks the marker is about to eat.

    Returns ``(opening, closing)`` — whether ``post_substitute`` has to
    set an opening and a closing mark around the canonical text it pastes
    in. The canonical text itself is always bare, so this is the whole of
    what decides how a quoted verse reaches the reader.

    The question underneath is "did the author present this as a
    quotation", and the replaced span alone cannot answer it. Where the
    marks fall relative to the span depends on where the author put the
    citation, and the two placements are not the same case:

    * A mark **inside** the span is destroyed with the verse and has to
      be put back.
    * A mark **outside** it survives the round trip untouched, and
      putting it back too is how a verse ends up in doubled marks. This
      is the ordinary case for an inline quotation, where the marks are
      deliberately left standing in the prose.

    So the sides are read independently, and the asymmetric layout —
    ``«…до края земли (Деян. 1:8)»``, opening mark eaten, closing mark
    surviving after the citation — restores one mark rather than two.

    A quotation needs both ends before anything is restored. A single
    mark is as likely to be a stray apostrophe, a plural possessive, or
    half a pair the author never closed, and we cannot tell which. Bare
    is also the right answer for the common ``<blockquote>`` an author
    set with no marks at all: it is already a quotation to the eye, and
    this must not give it any.
    """
    opening_inside = _visible_after(replaced, skip_citation=False) in _OPENING_MARKS
    closing_inside = _visible_before(replaced, skip_punctuation=True) in _CLOSING_MARKS
    opens = opening_inside or _visible_before(before[-_QUOTE_EDGE_WINDOW:], skip_punctuation=False) in _OPENING_MARKS
    closes = closing_inside or _visible_after(after[:_QUOTE_EDGE_WINDOW], skip_citation=True) in _CLOSING_MARKS
    if not (opens and closes):
        return False, False
    return opening_inside, closing_inside


def _drop_unpaired_edge_mark(canonical: str) -> str:
    """Canonical text without an edge mark that has nothing to pair with.

    Some editions set direct speech in quotation marks, and speech runs
    across verse boundaries. Ask the API for Acts 1:8 in English and the
    Berean Standard Bible answers

        But you will receive power … to the ends of the earth.”

    — a closing mark whose opening lives in verse 7, which nobody
    reading this lesson can see. Verified against the live API on
    2026-08-20: of the four editions this platform quotes, only the
    English one does this, and it is the whole reason the English column
    of the corpus reads ``…ends of the earth." (Acts 1:8)`` — a verse
    that opens with nothing and closes with a mark. That is not the
    author's punctuation surviving; it is the edition's, orphaned by
    being shown one verse at a time.

    So it goes. Narrowly: only when the text holds **exactly one** double
    quotation mark and that mark stands at an edge, which is proof it has
    no partner in the text rather than a guess that it hasn't. A verse
    that quotes something in full (``“Repent and be baptized…”``) has
    two, and keeps both. An unpaired mark in the *middle* of a verse
    (``Jesus answered, “I am the way…``) is left where it is: it is the
    edition's, it is unbalanced, and there is no safe way to tell from
    one verse whether removing it or completing it is the smaller lie.
    """
    text = canonical.strip()
    if len([char for char in text if char in _DOUBLE_MARKS]) != 1:
        return canonical
    if text[0] in _DOUBLE_OPENING:
        return text[1:].lstrip()
    if text[-1] in _DOUBLE_CLOSING:
        return text[:-1].rstrip()
    return canonical


def _requote(canonical: str, sub: Substitution, html: str, target_locale: LocaleCode) -> str:
    """``canonical`` presented the way the author presented it: wrapped
    in quotation marks if they quoted it, bare if they did not, and in
    the marks ``target_locale`` writes rather than the ones they typed.

    Three things can already have supplied a mark, and each is a reason
    not to supply a second:

    * The **edition**, which may print the verse as speech. ``“Repent
      and be baptized…”`` needs no marks around it, it has them.
    * The **surrounding text**, when the author's mark fell outside the
      replaced span and survived the round trip untouched.
    * **This function**, on a previous pass over the same document.

    All three are answered by the same check — look before adding — and
    it is the third that makes the pass idempotent.
    """
    canonical = _drop_unpaired_edge_mark(canonical)
    marks = QUOTATION_MARKS.get(target_locale)
    if marks is None or not (sub.opening_quote_lost or sub.closing_quote_lost):
        return canonical
    opening, closing = marks
    index = html.find(sub.marker)
    if index == -1:
        return canonical
    lead = html[max(0, index - _QUOTE_EDGE_WINDOW) : index]
    trail = html[index + len(sub.marker) : index + len(sub.marker) + _QUOTE_EDGE_WINDOW]
    if (
        sub.opening_quote_lost
        and canonical[:1] not in _OPENING_MARKS
        and _visible_before(lead, skip_punctuation=False) not in _OPENING_MARKS
    ):
        canonical = opening + canonical
    if (
        sub.closing_quote_lost
        and canonical[-1:] not in _CLOSING_MARKS
        and _visible_after(trail, skip_citation=True) not in _CLOSING_MARKS
    ):
        canonical = canonical + closing
    return canonical


def _localize_ref_tail(
    tail: str,
    target_locale: LocaleCode,
    *,
    book: str | None = None,
    renumber: bool = False,
) -> str:
    """Rewrite the book name in a parenthesized reference like
    ``(Matt. 28:19)`` so it reads naturally in ``target_locale``
    (``(Матф. 28:19)``). Uses the locale's conventional short form
    from ``books.display_book_name``. Falls back to the original tail
    when no parsable reference is found or no display name exists for
    the target locale — never raises, so a stray edge case can't break
    the whole post-substitute pass.

    ``renumber`` moves the chapter and verse into the target edition's
    own numbering as well. It belongs on exactly when the quoted text
    beside the label came from that edition: the Russian edition
    answers a request for Psalm 23:1 with its own 22:1, so a label
    reading "(Пс. 23:1)" over that text sends a reader who wants to
    check it to a different psalm. It belongs off on the fallback path,
    where the author's own quotation survived and their own numbers
    still describe it.

    ``book`` is the slug the caller already resolved, in the source
    language, back when it still knew what that language was. The tail
    is re-parsed only to find where in the string the reference sits —
    asking it *which book* again, with no locale, would read a Ukrainian
    author's ``1 Цар.`` as 1 Samuel and re-label their 1 Kings quotation
    with the wrong book.
    """
    parsed = parse_references(tail)
    if not parsed:
        return tail
    p = parsed[0]
    display = display_book_name(book or p.ref.book, target_locale)
    if not display:
        return tail
    ref = p.ref if book is None else replace(p.ref, book=book)
    if renumber:
        renumbered = remap_psalm(ref, target_locale)
        if renumbered is None:
            return tail
        ref = renumbered
    if ref.verse_end is not None:
        formatted = f"{display} {ref.chapter}:{ref.verse_start}-{ref.verse_end}"
    else:
        formatted = f"{display} {ref.chapter}:{ref.verse_start}"
    start, end = p.span
    return tail[:start] + formatted + tail[end:]


def _marker_token() -> str:
    """Produce a sentinel that survives the full round-trip.

    Constraints satisfied:
    * Plain ASCII — no Unicode Private-Use Area characters (the v1.5
      attempt did that, and the invisible ``\\ue000`` / ``\\ue001`` chars
      broke editor round-trips and the test suite's ASCII assertions).
    * Valid UTF-8, so it survives JSON encoding to Gemini and back.
    * Valid in Postgres TEXT (unlike NUL bytes, which the type
      explicitly rejects — that was the v1 bug that left raw markers
      visible in students' EN view of the Acts course).
    * The prefix is ``EQV`` and not ``VERSE_``, which is the whole
      point of this note. ``VERSE`` is an English word, and a
      translator asked for Ukrainian translated it: production has a
      row reading ``"ВЕРС_0c0214d57ac3a0bb"`` where Scripture belongs.
      The marker then matches nothing on the way back, the verse is
      dropped, and the reference is left standing over an empty space.
      ``EQV`` is a word in none of the four languages, so there is
      nothing to translate — and it is still greppable and still
      identifier-shaped, so the prompt's "preserve placeholders
      verbatim" rule applies.
    * The random hex suffix lets multiple substitutions in one
      document round-trip independently and means an attacker can't
      pre-craft a marker to confuse ``post_substitute``.
    """
    return f"EQV{secrets.token_hex(8)}"


def pre_substitute(
    html: str,
    source_locale: LocaleCode,
) -> tuple[str, list[Substitution]]:
    """Detect canonical scripture quotes in ``html``, replace each
    blockquote's inner text with a unique marker, and return the
    transformed HTML plus the list of substitutions performed.

    ``html`` is returned unchanged when:
    * The locale isn't bundled (we can't compare to canonical).
    * No blockquote / reference pair is detected.
    * The author paraphrased (similarity < 0.80).
    """
    if not html:
        return html, []

    subs: list[Substitution] = []
    out_parts: list[str] = []
    cursor = 0

    for bm in _BLOCKQUOTE_PATTERN.finditer(html):
        bq_start, bq_end = bm.span()
        inner = bm.group("inner")

        # Two real-world layouts for the reference:
        #
        #   A) Inside, at the end of the blockquote text:
        #        <blockquote>«…verse…» (Acts 1:8).</blockquote>
        #   B) Outside, immediately after the closing tag:
        #        <blockquote>…verse…</blockquote> (Acts 1:8)
        #
        # Try inside first — that's where Synodal-style citations sit in
        # most academic prose. Fall back to the lookahead window after
        # the closing tag so older content keeps working.
        ref = None
        verse_text_inner: str = inner
        ref_tail_inner: str = ""
        # ``stored_ref_tail`` is the text we hand to ``post_substitute``
        # for target-locale rewriting. Same as ``ref_tail_inner`` in
        # the inner case (the marker re-emits it inside the
        # blockquote), but in the outside case it points at the
        # source-locale ref text that's still sitting in the
        # surrounding HTML — so post can find and localize it without
        # us re-emitting anything here.
        stored_ref_tail: str = ""
        inner_refs = parse_references(inner, source_locale)
        if inner_refs:
            # Take the *last* reference inside (it's almost always the
            # citation appended after the verse, even when the prose
            # happens to mention an earlier verse number conversationally).
            last = inner_refs[-1]
            # Extend the citation tail leftwards to include a leading
            # ``(`` if present, plus a closing ``"`` / ``»`` / ``)`` /
            # punctuation that closes the verse quote. The regex starts
            # at "Acts" / "Деян." so we'd otherwise leave a stray ``(``
            # inside the marker-replaced verse text.
            tail_start = last.span[0]
            stripped_left = inner[:tail_start].rstrip()
            if stripped_left.endswith(("(", " (")):
                # Walk back over the trailing whitespace + ``(``.
                tail_start = inner.rfind("(", 0, tail_start)
            verse_text_inner = inner[:tail_start]
            ref_tail_inner = inner[tail_start:]
            ref = last.ref
        else:
            tail = html[bq_end : bq_end + _REFERENCE_LOOKAHEAD]
            outside_refs = parse_references(tail, source_locale)
            if outside_refs:
                ref = outside_refs[0].ref
                verse_text_inner = inner
                ref_tail_inner = ""
                # The outside ref lives in the original HTML after the
                # closing </blockquote>; we don't re-emit it here.
                # ``post_substitute`` looks for ``stored_ref_tail`` in
                # the translated HTML and rewrites the book name into
                # the target locale (``Acts 1:8`` → ``Деян. 1:8``).
                # Best-effort: if the LLM mutated the substring in
                # transit, the literal replace becomes a no-op and the
                # source-locale ref survives — never breaks rendering.
                stored_ref_tail = outside_refs[0].raw_text

        if ref is None:
            continue

        candidates = canonical_candidates_for_source(ref, source_locale)
        if not candidates:
            continue

        author_text = _strip_html(verse_text_inner)
        if not author_text:
            continue
        # Best of every wording we hold, not the first one that answered:
        # the author quoted *some* edition, and which one is not ours to
        # assume.
        ratio = max(
            SequenceMatcher(
                None,
                _normalize_for_compare(author_text),
                _normalize_for_compare(candidate),
            ).ratio()
            for candidate in candidates
        )
        if ratio < _SIMILARITY_THRESHOLD:
            logger.debug(
                "Bible quote similarity %.2f below threshold for %s — leaving as-is",
                ratio,
                ref,
            )
            continue

        marker = _marker_token()
        # Re-derive the opening/closing tags from the match so we don't
        # lose attributes like ``class="quote"``.
        opening_tag = html[bq_start : bq_start + html[bq_start:bq_end].index(">") + 1]
        closing_tag = "</blockquote>"
        out_parts.append(html[cursor:bq_start])
        out_parts.append(opening_tag)
        out_parts.append(marker)
        # The marker swallowed the verse text including any trailing
        # whitespace/quote chars; re-introduce a single space before
        # ``(Acts 1:8)`` so the post-substituted output reads
        # ``…canonical text. (Acts 1:8).`` and not
        # ``…canonical text.(Acts 1:8).``. Only when the tail starts
        # with ``(`` (the parenthesized-reference form we walked back
        # to include); the no-paren form is rare and uses ref_tail="".
        emitted_tail = ref_tail_inner
        if emitted_tail.startswith("(") and not emitted_tail.startswith(" ("):
            emitted_tail = " " + emitted_tail
        out_parts.append(emitted_tail)
        out_parts.append(closing_tag)
        cursor = bq_end
        # ``ref_tail`` on Substitution is what post_substitute scans for
        # to localize the book name. For inner-ref blockquotes it's the
        # exact tail we just emitted; for outside-ref blockquotes it's
        # the ref text we left untouched in the surrounding HTML so
        # post can find and rewrite it (``stored_ref_tail`` set above).
        #
        # Whether the author quoted is asked of the *source* HTML, where
        # their own marks are still standing, and about the exact span
        # the marker replaces: everything before ``verse_text_inner``,
        # and everything after it including the citation.
        inner_start = bm.start("inner")
        opening_lost, closing_lost = _swallowed_quotes(
            verse_text_inner,
            html[:inner_start],
            html[inner_start + len(verse_text_inner) :],
        )
        subs.append(
            Substitution(
                marker=marker,
                ref=ref,
                original_inner=verse_text_inner,
                ref_tail=emitted_tail or stored_ref_tail,
                opening_quote_lost=opening_lost,
                closing_quote_lost=closing_lost,
            )
        )

    if cursor == 0:
        # No blockquote substitutions — the original string, so the
        # inline pass sees exactly what the author wrote.
        markered = html
    else:
        out_parts.append(html[cursor:])
        markered = "".join(out_parts)

    markered = _substitute_inline_quotes(markered, source_locale, subs)
    if not subs:
        # Nothing matched at all — return the original to avoid any
        # incidental whitespace / encoding fiddling.
        return html, []
    return markered, subs


# A verse quoted inside a sentence rather than set in a blockquote:
#
#     John 3:17 states, "For God did not send his Son…"
#     «Ибо так возлюбил Бог мир…» (Ин. 3:16)
#
# Both orders occur, and both are common in the Daily Challenge
# explanations, where there is no markup at all to hang a blockquote on.
# Until this existed, those verses went to the model as ordinary prose
# and came back as ordinary prose — which for a German reader meant an
# English verse sitting inside a German sentence, because the prompt
# tells the model to leave quoted Scripture untouched. Rightly: the
# alternative is a model reciting Scripture from memory, and that was
# tried and abandoned.
_QUOTED_SPAN = re.compile(
    r"(?P<open>[\"«“‘'])(?P<inner>[^\"«»“”]{16,900}?)(?P<close>[\"»”’'])",
)

# How far a quotation may sit from its reference and still be read as
# that reference's text. Real prose puts a clause between them —
# "John 3:14 links the lifting up of the Son of Man directly to the
# wilderness event: '…'" is 73 characters of lead-in — so this is
# generous. Attaching to the *nearest* reference is what actually
# prevents a mis-pairing; the distance is a backstop for a quotation
# that belongs to no reference at all.
_INLINE_WINDOW = 300

# The inline path is more forgiving than the blockquote path, and
# deliberately.
#
# Quotation marks next to a reference are the author asserting "these
# are the words of this verse". They may be the words of a different
# English edition than the one bundled — the Daily Challenge generator
# quotes ESV-ish wording, which scores 0.79 against KJV for John 3:17
# and would fail the blockquote bar by a hair. Refusing there means the
# German reader gets the English sentence, which is the worse outcome
# by a wide margin: the source is untouched either way, and what
# changes is only whether the *translation* carries Luther or English.
#
# Below this, it is a paraphrase and the author's own words stand.
_INLINE_SIMILARITY_THRESHOLD = 0.65


def _substitute_inline_quotes(
    text: str,
    source_locale: LocaleCode,
    subs: list[Substitution],
) -> str:
    """Marker-replace quoted verses that sit inside ordinary prose.

    Appends to ``subs`` in place and returns the markered text. Walks
    quotations rather than references, and pairs each with the nearest
    reference: a paragraph that cites three verses and quotes two of
    them has to get both pairings right, and "nearest" is the rule a
    reader applies too.
    """
    refs = parse_references(text, source_locale)
    if not refs:
        return text

    replacements: list[tuple[int, int, Substitution]] = []
    claimed: set[int] = set()

    for match in _QUOTED_SPAN.finditer(text):
        span_start, span_end = match.span("inner")
        for index, parsed in _candidate_references(refs, span_start, span_end, claimed):
            candidates = canonical_candidates_for_source(parsed.ref, source_locale)
            if not candidates:
                continue
            ratio = max(
                SequenceMatcher(
                    None,
                    _normalize_for_compare(match.group("inner")),
                    _normalize_for_compare(candidate),
                ).ratio()
                for candidate in candidates
            )
            if ratio < _INLINE_SIMILARITY_THRESHOLD:
                continue

            claimed.add(index)
            # No ``*_quote_lost`` here, and none is needed:
            # ``_QUOTED_SPAN`` captures the marks as ``open`` and
            # ``close`` and replaces only ``inner``, so the author's own
            # marks are still standing in the prose on either side of the
            # marker. This path was never the defect — it is the one that
            # already did the right thing, and the blockquote path has
            # now been taught to match it.
            replacements.append(
                (
                    span_start,
                    span_end,
                    Substitution(
                        marker=_marker_token(),
                        ref=parsed.ref,
                        original_inner=match.group("inner"),
                        ref_tail=parsed.raw_text,
                    ),
                )
            )
            break

    if not replacements:
        return text

    # Right to left, so the earlier offsets stay valid.
    for span_start, span_end, sub in reversed(replacements):
        text = text[:span_start] + sub.marker + text[span_end:]
    subs.extend(sub for _, _, sub in replacements)
    return text


def _candidate_references(
    refs: list[ParsedReference],
    span_start: int,
    span_end: int,
    claimed: set[int],
) -> list[tuple[int, ParsedReference]]:
    """References this quotation could belong to, nearest first.

    Nearest alone is not enough. In "Ин. 3:16 говорит: «…» А в Деян. 1:8
    сказано: «…»" the *second* reference sits two characters after the
    *first* quotation, closer than the reference that introduced it — so
    a greedy nearest-wins pairing hands John's words to Acts, fails the
    similarity check, and drops a verse it could have matched. The
    caller therefore walks these in order and takes the first that the
    text actually resembles. Distance decides the order; the words
    decide the answer.

    A reference already claimed by an earlier quotation is not offered
    again, and one sitting inside the quotation is not a pairing — that
    is the citation being quoted along with the verse.
    """
    scored: list[tuple[int, int, ParsedReference]] = []
    for index, parsed in enumerate(refs):
        if index in claimed:
            continue
        ref_start, ref_end = parsed.span
        if ref_end <= span_start:
            distance = span_start - ref_end
        elif ref_start >= span_end:
            distance = ref_start - span_end
        else:
            continue
        if distance > _INLINE_WINDOW:
            continue
        scored.append((distance, index, parsed))
    scored.sort(key=lambda item: item[0])
    return [(index, parsed) for _distance, index, parsed in scored]


def canonical_for_display(ref: BibleRef, locale: str) -> str | None:
    """Canonical text for a student's page: API where we have one, file
    where the file is sound, and `None` — meaning "keep what the author
    wrote" — whenever neither can answer.

    No bundle fallback for the API locales. The Russian file is
    misaligned (#990: `romans.1.1` returns James), and a wrong verse
    shown to a student is the one outcome worse than the author's own
    quotation surviving in the wrong language.
    """
    if locale in API_BIBLE_IDS:
        from_api = fetch_verse(ref, locale)  # type: ignore[arg-type]
        if from_api is not None or locale not in TRUSTED_BUNDLE_LOCALES:
            return from_api
        # English only, and only when the API could not answer. Its
        # bundle is the King James Version: sound, complete, verified —
        # and four centuries old, which is why the API edition is
        # preferred now. But "the network was down" is not a reason to
        # show a student nothing where a verse belongs, and archaic
        # English is still Scripture. Russian gets no such fallback: its
        # bundle is misaligned (#990) and would print James where the
        # lesson said Romans, which is worse than a gap. German and
        # Ukrainian have no bundle at all.
    return lookup(ref, locale)  # type: ignore[arg-type]


def canonical_candidates_for_source(ref: BibleRef, locale: str) -> list[str]:
    """Every wording of this verse worth comparing an author against.

    Used only to answer "did the author quote this verse?" — never
    rendered, so more candidates can only help.

    Why a list rather than one text. The Russian edition behind the API
    is a modern paraphrase; the authors here quote the Synodal text, and
    the two disagree far more than the 0.80 bar allows. Acts 8:4 as an
    author writes it scores **0.42** against the API wording and
    **0.89** against the bundled Synodal one. Asking the API first and
    stopping there meant no Russian quotation was ever recognised — and
    Russian is the language this catalogue is written in. Every quoted
    verse went to the model to be re-worded, in every course, which is
    exactly the failure this whole layer exists to prevent.

    Returning both and taking the best match costs one dictionary lookup
    and cannot mislead a reader: the text is discarded after the
    comparison. That is also why the bundle is safe here while it stays
    barred from the display direction, where a misaligned file (#990)
    would put the wrong verse in front of a student.
    """
    candidates: list[str] = []
    if locale in API_BIBLE_IDS:
        from_api = fetch_verse(ref, locale)  # type: ignore[arg-type]
        if from_api is not None:
            candidates.append(from_api)
    from_bundle = lookup(ref, locale)  # type: ignore[arg-type]
    if from_bundle is not None and from_bundle not in candidates:
        candidates.append(from_bundle)
    return candidates


def canonical_for_source(ref: BibleRef, locale: str) -> str | None:
    """First candidate, kept for callers that want a single text."""
    candidates = canonical_candidates_for_source(ref, locale)
    return candidates[0] if candidates else None


def post_substitute(
    html: str,
    subs: list[Substitution],
    target_locale: LocaleCode,
) -> str:
    """Replace every marker in ``html`` with the canonical
    ``target_locale`` text for its substitution and rewrite the
    surviving reference tail (``(Matt. 28:19)``) into the same locale's
    conventional form (``(Матф. 28:19)``). A verse the author set in
    quotation marks is re-wrapped in the marks ``target_locale`` uses —
    ``«»`` for Russian and Ukrainian, ``„“`` for German, straight ``"``
    for English — because the canonical editions print Scripture bare
    and the author's own marks went into the marker with the verse. A
    verse the author did not set in marks gets none.

    Falls back to the original
    (source-locale) inner text when the target lookup misses — better
    than leaking a sentinel marker into the rendered page. Tail-rewrite
    is best-effort: if the LLM mutated the tail in transit, the literal
    string-replace becomes a no-op and the (slightly less native) tail
    survives instead of disappearing."""
    if not subs:
        return html
    for sub in subs:
        canonical_target = canonical_for_display(sub.ref, target_locale)
        if canonical_target is None:
            # The fallback below hands the reader the *source* language:
            # a German student sees a Russian verse inside German prose.
            # That is still better than a visible marker, and better than
            # the model's paraphrase — but it is a defect, and until now
            # it happened in silence, on a row stored as ``ok``. Logged
            # with a stable code so the rate is countable rather than
            # anecdotal.
            logger.warning(
                "verse_fallback_to_source ref=%s target=%s",
                sub.ref_tail or "?",
                target_locale,
            )
        # Re-wrapping applies only to the canonical text. The fallback
        # path restores the author's own span, which still carries
        # whatever marks the author put inside it.
        replacement = (
            _requote(canonical_target, sub, html, target_locale) if canonical_target is not None else sub.original_inner
        )
        html = html.replace(sub.marker, replacement)
        if sub.ref_tail:
            # The numbers follow the text: they move only when the text
            # beside them came from an edition that numbers differently.
            localized = _localize_ref_tail(
                sub.ref_tail,
                target_locale,
                book=sub.ref.book,
                renumber=canonical_target is not None and target_locale in API_BIBLE_IDS,
            )
            if localized != sub.ref_tail:
                html = html.replace(sub.ref_tail, localized, 1)
    # The fallback path restores the author's inner text *with* its closing
    # quote, and the tail already carries a leading space — so a refused
    # lookup left «…Духа:”  (Матф. 28:19)» with a double space. One space
    # before an opening paren, always; the test that guards this predates the
    # fallback and was right to keep failing.
    return html.replace("  (", " (")


__all__ = [
    "Substitution",
    "canonical_for_display",
    "post_substitute",
    "pre_substitute",
]
