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
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from app.services.bible.books import display_book_name
from app.services.bible.references import BibleRef, parse_references
from app.services.bible.store import is_locale_bundled, lookup

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
    ``(Матф. 28:19).`` instead of the source-locale form."""

    marker: str
    ref: BibleRef
    original_inner: str
    ref_tail: str = ""


def _strip_html(html: str) -> str:
    """Crude HTML → plain text. Sufficient for similarity comparison —
    we collapse tags into spaces, then fold whitespace runs."""
    no_tags = re.sub(r"<[^>]+>", " ", html)
    return " ".join(no_tags.split())


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


def _localize_ref_tail(tail: str, target_locale: LocaleCode) -> str:
    """Rewrite the book name in a parenthesized reference like
    ``(Matt. 28:19)`` so it reads naturally in ``target_locale``
    (``(Матф. 28:19)``). Uses the locale's conventional short form
    from ``books.display_book_name``. Falls back to the original tail
    when no parsable reference is found or no display name exists for
    the target locale — never raises, so a stray edge case can't break
    the whole post-substitute pass."""
    parsed = parse_references(tail)
    if not parsed:
        return tail
    p = parsed[0]
    display = display_book_name(p.ref.book, target_locale)
    if not display:
        return tail
    if p.ref.verse_end is not None:
        formatted = f"{display} {p.ref.chapter}:{p.ref.verse_start}-{p.ref.verse_end}"
    else:
        formatted = f"{display} {p.ref.chapter}:{p.ref.verse_start}"
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
    * Distinctive prefix ``VERSE_`` keeps it greppable in logs and
      makes the token "identifier-shaped" so the prompt's
      "preserve placeholders verbatim" rule applies.
    * The random hex suffix lets multiple substitutions in one
      document round-trip independently and means an attacker can't
      pre-craft a marker to confuse ``post_substitute``.
    """
    return f"VERSE_{secrets.token_hex(8)}"


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
    if not html or not is_locale_bundled(source_locale):
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
        inner_refs = parse_references(inner)
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
            outside_refs = parse_references(tail)
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

        canonical_source = lookup(ref, source_locale)
        if canonical_source is None:
            continue

        author_text = _strip_html(verse_text_inner)
        if not author_text:
            continue
        ratio = SequenceMatcher(
            None,
            _normalize_for_compare(author_text),
            _normalize_for_compare(canonical_source),
        ).ratio()
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
        subs.append(
            Substitution(
                marker=marker,
                ref=ref,
                original_inner=verse_text_inner,
                ref_tail=emitted_tail or stored_ref_tail,
            )
        )

    if cursor == 0:
        # No substitutions made — return the original to avoid any
        # incidental whitespace / encoding fiddling.
        return html, []
    out_parts.append(html[cursor:])
    return "".join(out_parts), subs


def post_substitute(
    html: str,
    subs: list[Substitution],
    target_locale: LocaleCode,
) -> str:
    """Replace every marker in ``html`` with the canonical
    ``target_locale`` text for its substitution and rewrite the
    surviving reference tail (``(Matt. 28:19)``) into the same locale's
    conventional form (``(Матф. 28:19)``). Falls back to the original
    (source-locale) inner text when the target lookup misses — better
    than leaking a sentinel marker into the rendered page. Tail-rewrite
    is best-effort: if the LLM mutated the tail in transit, the literal
    string-replace becomes a no-op and the (slightly less native) tail
    survives instead of disappearing."""
    if not subs:
        return html
    for sub in subs:
        canonical_target = lookup(sub.ref, target_locale)
        replacement = canonical_target if canonical_target is not None else sub.original_inner
        html = html.replace(sub.marker, replacement)
        if sub.ref_tail:
            localized = _localize_ref_tail(sub.ref_tail, target_locale)
            if localized != sub.ref_tail:
                html = html.replace(sub.ref_tail, localized, 1)
    return html


__all__ = ["Substitution", "post_substitute", "pre_substitute"]
