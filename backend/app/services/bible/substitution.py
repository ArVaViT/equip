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
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from app.core.sanitize import html_to_plain_text
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
    ``(Матф. 28:19).`` instead of the source-locale form."""

    marker: str
    ref: BibleRef
    original_inner: str
    ref_tail: str = ""


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
        subs.append(
            Substitution(
                marker=marker,
                ref=ref,
                original_inner=verse_text_inner,
                ref_tail=emitted_tail or stored_ref_tail,
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
    conventional form (``(Матф. 28:19)``). Falls back to the original
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
        replacement = canonical_target if canonical_target is not None else sub.original_inner
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
