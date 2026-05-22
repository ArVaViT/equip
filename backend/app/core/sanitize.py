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
    }
)

_ALLOWED_ATTRIBUTES: dict[str, list[str]] = {
    "a": ["href", "title", "target", "rel"],
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


def _strip_dangerous_iframes(html: str) -> str:
    """Only allow YouTube embeds through iframes — everything else is stripped.

    ``bleach`` treats iframes as a regular allowed tag; it doesn't know which
    ``src`` values are safe. We do that post-filter here.
    """
    pattern = re.compile(r"<iframe\b[^>]*>", re.IGNORECASE)

    def _check(match: re.Match[str]) -> str:
        tag = match.group(0)
        src_match = re.search(r'\bsrc\s*=\s*"([^"]*)"', tag, re.IGNORECASE) or re.search(
            r"\bsrc\s*=\s*'([^']*)'", tag, re.IGNORECASE
        )
        src = (src_match.group(1) if src_match else "").strip().lower()
        if src.startswith(("https://www.youtube.com/embed/", "https://www.youtube-nocookie.com/embed/")):
            return tag
        return ""

    html = pattern.sub(_check, html)
    html = re.sub(r"</iframe>", "</iframe>", html, flags=re.IGNORECASE)
    return html


def sanitize_string(value: str) -> str:
    """Sanitize user-supplied HTML/text for safe server-side storage.

    Short strings (titles, names, etc.) still go through this. Because they
    shouldn't contain HTML at all, any residue the sanitizer leaves is
    already safe for rendering.
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
        return cleaned.strip()

    # Regex fallback — matches the previous minimal behaviour.
    cleaned = _TAG_RE.sub("", value)
    cleaned = _EVENT_ATTR_RE.sub("", cleaned)
    cleaned = _JS_PROTO_RE.sub("", cleaned)
    return cleaned.strip()
