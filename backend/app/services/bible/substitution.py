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
6. Markers use ``\\x00`` NUL byte sentinels — those cannot appear in HTML
   or TipTap content, so they survive the Gemini round-trip intact.
   System prompt rule "preserve placeholders verbatim" covers them.

``post_substitute`` is the inverse: replace each marker in the
translated HTML with the canonical ``target_locale`` text. If the
target-locale lookup fails (e.g. an exotic verse missing from the
bundled file), restore the original blockquote text instead — better
than leaving a NUL marker in the output.

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
    by ``post_substitute``. ``marker`` is the NUL-fenced sentinel that
    replaces the blockquote's inner text in the markered HTML; ``ref``
    points at the canonical Bible passage; ``original_inner`` is the
    author's text (stripped of HTML), kept for safe fallback when the
    target locale's lookup misses."""

    marker: str
    ref: BibleRef
    original_inner: str


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


def _marker_token() -> str:
    """Produce a sentinel that cannot appear in any HTML payload.
    NUL bytes are forbidden by both HTML5 parsers and TipTap, so the
    marker survives Gemini's round-trip without escaping risk. The
    random hex suffix keeps multiple substitutions in one document
    distinguishable."""
    return f"\x00VERSE_{secrets.token_hex(8)}\x00"


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
        # Lookahead window for the reference: text right after </blockquote>.
        tail = html[bq_end : bq_end + _REFERENCE_LOOKAHEAD]
        refs = parse_references(tail)
        if not refs:
            continue
        ref = refs[0].ref  # take the first reference closest to the blockquote
        canonical_source = lookup(ref, source_locale)
        if canonical_source is None:
            continue

        author_text = _strip_html(inner)
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
        # Append everything up to the blockquote opening tag, the opening
        # tag itself (preserved verbatim), the marker, and the closing tag.
        # Re-derive the opening/closing tags from the match groups so we
        # don't lose attributes like ``class="quote"``.
        opening_tag = html[bq_start : bq_start + html[bq_start:bq_end].index(">") + 1]
        closing_tag = "</blockquote>"
        out_parts.append(html[cursor:bq_start])
        out_parts.append(opening_tag)
        out_parts.append(marker)
        out_parts.append(closing_tag)
        cursor = bq_end
        subs.append(
            Substitution(
                marker=marker,
                ref=ref,
                original_inner=inner,
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
    ``target_locale`` text for its substitution. Falls back to the
    original (source-locale) inner text when the target lookup misses
    — better than leaking a NUL-byte marker into the rendered page."""
    if not subs:
        return html
    for sub in subs:
        canonical_target = lookup(sub.ref, target_locale)
        replacement = canonical_target if canonical_target is not None else sub.original_inner
        html = html.replace(sub.marker, replacement)
    return html


__all__ = ["Substitution", "post_substitute", "pre_substitute"]
