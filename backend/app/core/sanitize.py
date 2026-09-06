"""HTML sanitization for user-supplied text/rich content.

The frontend runs DOMPurify on all rich content before it's rendered, but we
sanitize again on the server as defence-in-depth: if a rich-text payload is
somehow persisted without going through the frontend (direct API hits,
imported content, legacy data), we still strip anything that could lead to
stored XSS.

Preference order:
  1. ``bleach`` when available — canonical HTML sanitizer, handles malformed
     input and nested tricks better than regex.
  2. Regex fallback — preserves the previous behaviour for environments where
     bleach is not installed yet (e.g. older deploys, ad-hoc scripts).
"""

from __future__ import annotations

import re
from html import unescape
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

try:
    import bleach

    _HAS_BLEACH = True
except ImportError:  # pragma: no cover - exercised in environments without bleach
    _HAS_BLEACH = False


# Tags that are safe to embed inside user content. Block-level + inline +
# lists + tables + limited media (iframes with scheme-checked src only).
_ALLOWED_TAGS = frozenset(
    {
        "p",
        "br",
        "span",
        "div",
        "strong",
        "b",
        "em",
        "i",
        "u",
        "s",
        "strike",
        "mark",
        "ul",
        "ol",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "blockquote",
        "pre",
        "code",
        "table",
        "thead",
        "tbody",
        "tr",
        "td",
        "th",
        "a",
        "img",
        "hr",
        "sup",
        "sub",
        "iframe",
        # ``details`` + ``summary`` are HTML5 click-to-expand primitives.
        # The TipTap Callout extension's ``toggle`` variant is stored as
        # ``<div data-callout="toggle">`` and rewritten at view time
        # (``frontend/src/lib/callout-toggle.ts``) to the native
        # ``<details>`` / ``<summary>`` shape — but if a teacher pastes
        # the rewritten form directly (e.g. from another doc) or legacy
        # imports include the native shape, the sanitiser keeps it
        # intact instead of stripping it down to raw text.
        "details",
        "summary",
        # A picture with a caption is one thing. Without these two the
        # sanitiser unwraps the pair and the caption survives as a bare
        # sentence under the image, reading as body text — and the
        # translation validator, which compares the tag list of a
        # translation against its source, sees the structure change and
        # parks the row. Neither tag can carry script.
        "figure",
        "figcaption",
        # The editor's "Insert audio" button (``AudioExtension``) stores a
        # sermon recording as ``<audio controls preload="metadata"
        # class="w-full my-4" src="https://…">``. Until 2026-09-05 neither
        # tag was here and bleach dropped the element whole: the player
        # showed in the editor, autosave went green, and the recording
        # was gone on reload — silently, because nothing else on the
        # page changed. ``source`` is the child form the same extension
        # reads (``<audio><source src=…></audio>``). Which schemes a
        # ``src`` may carry is decided below, in ``_strip_dangerous_audio``.
        "audio",
        "source",
    }
)

_ALLOWED_ATTRIBUTES: dict[str, list[str]] = {
    # No ``target``: a stored link must never open a new browsing context,
    # so there is no ``window.opener`` for the opened page to abuse
    # (reverse tabnabbing). The frontend renderer strips ``target`` too;
    # dropping it here keeps both layers consistent. Intentional new-tab
    # links are built in app code with an explicit rel="noopener noreferrer".
    "a": ["href", "title"],
    "img": ["src", "alt", "title", "width", "height", "loading"],
    "iframe": [
        "src",
        "allow",
        "allowfullscreen",
        "frameborder",
        "loading",
        "referrerpolicy",
        "width",
        "height",
    ],
    # Table cells emit ``colspan`` / ``rowspan`` when a teacher merges
    # cells in the TipTap editor. ``th`` also carries ``scope`` for the
    # standard column / row header semantics screen readers rely on.
    # Bleach's per-tag list OVERRIDES the wildcard ``*`` entry, so we
    # repeat ``class`` and ``id`` here to keep the equip-table class
    # round-tripping for the .prose-cascade CSS.
    "td": ["colspan", "rowspan", "class", "id"],
    "th": ["colspan", "rowspan", "scope", "class", "id"],
    # Inline-math markers from ``@aarkue/tiptap-math-extension``. The
    # extension stores math as ``<span data-type="inlineMath"
    # data-latex="..." data-display="...">$x^2$</span>`` and the
    # chapter renderer feeds the LaTeX to KaTeX at view time. The
    # extension is configured with ``evaluation: false`` so the symbolic
    # ``data-evaluate`` attr it would otherwise emit never ships; we
    # don't allowlist it. Same per-tag-overrides-wildcard rule as table
    # cells — ``class`` / ``id`` are repeated so highlight.js token
    # spans (and any other span use) keep their class.
    "span": [
        "class",
        "id",
        "data-type",
        "data-latex",
        "data-display",
    ],
    # ``div`` and ``details`` both carry ``data-callout`` from the
    # TipTap Callout extension (info / verse / takeaway / warning go on
    # the ``div``; the ``toggle`` variant rewrites to native
    # ``<details>``). Per-tag overrides wildcard, so ``class`` / ``id``
    # are repeated.
    "div": ["class", "id", "data-callout"],
    "details": ["class", "id", "data-callout", "open"],
    # Exactly what ``AudioExtension.renderHTML`` emits, plus the wildcard
    # pair (per-tag overrides wildcard). No ``autoplay``: a lesson must
    # not start talking when it opens.
    "audio": ["src", "controls", "preload", "class", "id"],
    "source": ["src", "type"],
    "*": ["class", "id"],
}

_ALLOWED_PROTOCOLS = frozenset({"http", "https", "mailto", "tel"})

# CodeQL flagged the previous pattern ``<\s*/?\s*(...)[^>]*>`` as
# polynomial-redos: the two ``\s*`` flanking ``/?`` can partition any
# leading whitespace run in O(n) ways, triggering quadratic backtracking
# on attacker-shaped input. Drop both — real HTML doesn't allow
# whitespace between ``<`` / ``</`` and the tag name; bleach (the
# primary path) handles the obfuscation cases properly anyway.
_TAG_RE = re.compile(r"</?(?:script|object|embed|form|style|link|meta)\b[^>]*>", re.IGNORECASE)
_EVENT_ATTR_RE = re.compile(r"\bon\w+\s*=", re.IGNORECASE)
_JS_PROTO_RE = re.compile(r"javascript\s*:", re.IGNORECASE)


# Every ``src="…"`` / ``src='…'`` in a piece of markup. Used on the
# post-bleach output, where attribute values are always quoted.
_SRC_ATTR_RE = re.compile(r"""\bsrc\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.IGNORECASE)


def _src_values(markup: str) -> list[str]:
    """The ``src`` values in ``markup``, trimmed and lower-cased, in order."""
    return [(double or single).strip().lower() for double, single in _SRC_ATTR_RE.findall(markup)]


def _keep_only_trusted_elements(html: str, tag: str, trusted: Callable[[str], bool]) -> str:
    """Drop every ``<tag>`` element that ``trusted`` does not vouch for.

    ``bleach`` treats an allowed tag as an allowed tag; it doesn't know
    which ``src`` values are safe to embed. That decision is made here,
    after bleach, by ``trusted`` — handed the element's whole markup,
    opening tag through closing tag.

    The whole element goes, opening tag through closing tag. Dropping the
    opening tag alone — which is what the iframe filter did until
    2026-08-24, the line after the substitution being a replacement of
    ``</iframe>`` by itself — leaves an orphan closing tag in the
    document. It renders as nothing, so it survived review, but the
    translation validator compares the tag list of a translation against
    its source: the model tidies the stray closing tag away, the lists
    differ, and a correct translation is parked as ``markup_mismatch``.
    """
    # NUL cannot appear in a Postgres ``text`` column and has no meaning in
    # HTML, so dropping it costs nothing — and it keeps a caller from
    # writing the placeholder shape below into their own content.
    html = html.replace("\x00", "")
    element = re.compile(rf"<{tag}\b[^>]*>(?:.*?</{tag}\s*>)?", re.IGNORECASE | re.DOTALL)
    kept: list[str] = []

    def _check(match: re.Match[str]) -> str:
        element_html = match.group(0)
        if trusted(element_html):
            kept.append(element_html)
            # Parked behind a placeholder so the orphan sweep below cannot
            # see — and delete — the closing tag of an element we are keeping.
            return f"\x00{tag}{len(kept) - 1}\x00"
        return ""

    html = element.sub(_check, html)
    # Whatever closing tag is left belongs to no opening tag: either the
    # author pasted it, or an earlier version of this filter stripped the
    # opening half and left this behind.
    html = re.sub(rf"</{tag}\s*>", "", html, flags=re.IGNORECASE)
    for index, original in enumerate(kept):
        html = html.replace(f"\x00{tag}{index}\x00", original)
    return html


def _is_youtube_embed(element_html: str) -> bool:
    opening = re.match(r"<iframe\b[^>]*>", element_html, re.IGNORECASE)
    open_tag = opening.group(0) if opening else element_html
    srcs = _src_values(open_tag)
    src = srcs[0] if srcs else ""
    return src.startswith(("https://www.youtube.com/embed/", "https://www.youtube-nocookie.com/embed/"))


def _strip_dangerous_iframes(html: str) -> str:
    """Only allow YouTube embeds through iframes — everything else is stripped."""
    return _keep_only_trusted_elements(html, "iframe", _is_youtube_embed)


def _is_http_audio(element_html: str) -> bool:
    """An ``<audio>`` whose every source — its own ``src`` and each nested
    ``<source src>`` — is fetched over ``http(s)``.

    The same rule ``AudioExtension`` applies on paste, kept in step on
    the server so what the editor accepts is what the store keeps.
    Bleach's protocol allowlist is wider than that (``mailto:``,
    ``tel:``, and every relative path pass it), and a player pointed at
    nothing is worse than no player: it renders as a broken control the
    teacher cannot explain.
    """
    srcs = _src_values(element_html)
    return bool(srcs) and all(src.startswith(("http://", "https://")) for src in srcs)


def _strip_dangerous_audio(html: str) -> str:
    """Only keep ``<audio>`` players with ``http(s)`` sources — the rest go whole."""
    return _keep_only_trusted_elements(html, "audio", _is_http_audio)


def sanitize_string(value: str) -> str:
    """Sanitize user-supplied HTML/text for safe server-side storage.

    For rich content only — a lesson block, an announcement body, an
    event description. Bleach escapes the text between the tags on its
    way through, so a one-line field that carries no markup must go
    through ``sanitize_plain_text`` instead: run through this, a course
    called ``Faith & Works`` is stored as ``Faith &amp; Works``, the
    teacher sees the entity in the title box, and every save escapes it
    once more.
    """
    if not value:
        return value

    if _HAS_BLEACH:
        cleaned = bleach.clean(
            value,
            tags=_ALLOWED_TAGS,
            attributes=_ALLOWED_ATTRIBUTES,
            protocols=_ALLOWED_PROTOCOLS,
            strip=True,
            strip_comments=True,
        )
        cleaned = _strip_dangerous_iframes(cleaned)
        cleaned = _strip_dangerous_audio(cleaned)
        return cleaned.strip()

    # Regex fallback — matches the previous minimal behaviour.
    cleaned = _TAG_RE.sub("", value)
    cleaned = _EVENT_ATTR_RE.sub("", cleaned)
    cleaned = _JS_PROTO_RE.sub("", cleaned)
    return cleaned.strip()


def sanitize_plain_text(value: str) -> str:
    """One line of text with no markup in it — a course, module, chapter,
    event or announcement title.

    Tags are removed, not escaped, and entities are not escaped either:
    the field is rendered as text by React (and by nothing else as
    HTML), so ``&`` and ``<`` are just characters in a name. Whitespace
    folds to single spaces — a title has no line breaks.

    Entities are decoded *before* the tag pass, and nothing re-encodes
    them after it, so a ``&lt;script&gt;`` cannot re-form a tag and a
    title saved as ``Faith &amp; Works`` by the old code heals to
    ``Faith & Works`` the next time the teacher saves it. Plain text
    comes back unchanged however many times it passes through — the
    property the escaping path lacked.

    Not a sanitizer for anything that will be rendered as HTML: what
    comes out may still hold a bare ``<`` (``5 < 10``), and that is
    fine for a text node and wrong for ``innerHTML``.
    """
    if not value:
        return value
    return " ".join(strip_tags(unescape(value)).split())


def strip_tags(html: str) -> str:
    """Return the text content of ``html``, with tags replaced by spaces.

    Not a sanitizer — use ``sanitize_string`` for anything that will be
    rendered. This exists for the places that only want to *read* the
    prose: counting letters to detect a language, measuring similarity
    against a scripture verse, laying out a PDF.

    Written as a single linear pass rather than the obvious
    ``re.sub(r"<[^>]+>", " ", html)`` because that pattern backtracks
    quadratically on input that is mostly ``<`` — a string a teacher
    can paste into a lesson body. CodeQL flags it as a polynomial
    regular expression on uncontrolled data, and it is right to.

    A ``<`` only opens a tag when what follows looks like one (a
    letter, ``/``, or ``!``), so prose like "5 < 10" keeps its text
    instead of losing everything to the end of the paragraph.
    """
    out: list[str] = []
    i = 0
    length = len(html)
    while i < length:
        ch = html[i]
        if ch == "<" and i + 1 < length and (html[i + 1].isalpha() or html[i + 1] in "/!"):
            end = html.find(">", i + 1)
            if end == -1:
                # Unterminated tag: the rest is markup, not prose.
                break
            out.append(" ")
            i = end + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# Space stranded against punctuation when a tag that hugged the word is
# replaced by one: "<b>Бог</b>, сказал" would read "Бог , сказал", and
# "(<i>так</i>)" would read "( так)". Both sides, because an opening
# bracket collects the space after it and a closing one before.
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?)»”\]])")
_SPACE_AFTER_OPENING = re.compile(r"([(«“\[])\s+")


def html_to_plain_text(html: str | None) -> str:
    """Collapse ``html`` to a single line of prose.

    ``strip_tags`` plus whitespace folding — the shape three call sites
    had each written for themselves: the verse-of-the-day card, the
    scripture similarity comparison, and the course PDF. All three used
    the same `<[^>]+>` regex, which is the one CodeQL flagged as
    quadratic on hostile input.
    """
    if not html:
        return ""
    text = " ".join(strip_tags(html).split())
    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    return _SPACE_AFTER_OPENING.sub(r"\1", text)
