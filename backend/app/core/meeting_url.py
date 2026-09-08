"""The one address a student clicks to get into a live session.

Why this is its own module
--------------------------
A meeting link is the only field in the product where a teacher hands us
a URL and we hand it, unchanged, to every student as something clickable.
That is the exact shape of a stored-XSS hole: ``javascript:fetch(…)`` in
an ``href`` runs in the reader's session, with the reader's cookies, on
click. React does not block dangerous schemes in ``href`` — it renders
what it is given — so the block has to be here, before the value is ever
stored.

So the rule is an allowlist, not a blocklist: a value is a meeting link
only if it parses as an absolute ``http`` or ``https`` URL with a host.
Everything else is refused, and the caller never has to enumerate the
things it is refusing. ``javascript:``, ``data:``, ``vbscript:``,
``file:``, a bare ``zoom.us/j/1``, ``//evil.com`` and an empty string all
fail the same single test, because none of them are that.

Two refusals, not one
---------------------
``https://zoom.us@evil.com`` passes every scheme check ever written: the
scheme really is ``https``. It is also a link to ``evil.com`` — the part
before the ``@`` is a username, and a reader skimming the address sees
the half that is decoration. It gets its own rejection reason because it
needs its own explanation; told merely that the link "must start with
https://", the teacher looks at a link starting with https:// and
concludes the product is broken.

What comes back
---------------
The value is returned stripped but otherwise byte-for-byte as it was
typed. Re-serializing through ``urlunsplit`` would be the tidy thing to
do and is wrong here: a Zoom link carries its password in the query
(``?pwd=aB3.dEf``) and a Google Meet link carries meaning in its path
case, and any normalization that re-encodes either produces a link that
looks right and joins nothing.
"""

from __future__ import annotations

import enum
from urllib.parse import urlsplit

#: Longer than any real meeting link. Zoom's are ~90 characters, Google
#: Meet's ~35; the cap is here so a paste of a whole email thread is
#: refused as a length before it is parsed as a URL.
MEETING_URL_MAX_LENGTH = 2048

_ALLOWED_SCHEMES = frozenset({"http", "https"})

#: A URL has no whitespace in it. Anything here that survived the outer
#: ``strip()`` is *inside* the value, and every one of these is a way to
#: smuggle something past a parser: a newline ends an iCalendar property
#: line and would let a link write feed properties of its own, a NUL
#: truncates a C string, and U+2028 / U+2029 are line terminators to a
#: JavaScript parser though not to ``str.strip()``. Spelled as code
#: points because most of them are invisible, and a set of characters
#: nobody can see in the source is a set nobody can review.
_FORBIDDEN_CHARS = frozenset(
    {
        *(chr(code) for code in range(0x00, 0x20)),  # C0 controls, incl. tab / CR / LF
        "\x7f",  # DELETE
        "\u00a0",  # NO-BREAK SPACE — what a word processor pastes
        "\u2028",  # LINE SEPARATOR
        "\u2029",  # PARAGRAPH SEPARATOR
        "\ufeff",  # ZERO WIDTH NO-BREAK SPACE (BOM)
    }
)


class MeetingUrlRejection(enum.StrEnum):
    """Why a value is not a meeting link. One member per explanation the
    teacher gets — the route maps these to sentences in their language."""

    NOT_A_WEB_ADDRESS = "not_a_web_address"
    """Not an absolute ``http(s)`` URL with a host: a different scheme
    (``javascript:``, ``data:``, ``mailto:``), a relative path, a
    protocol-relative ``//host``, whitespace in the middle, or noise."""

    CREDENTIALS_IN_URL = "credentials_in_url"
    """Carries a ``user@`` (or ``user:pass@``) before the host, which
    hides the site the link actually opens."""

    TOO_LONG = "too_long"
    """Over ``MEETING_URL_MAX_LENGTH``."""


class MeetingUrlRejected(ValueError):
    """Raised by :func:`normalize_meeting_url`. ``reason`` is the
    machine-readable half; the human half belongs to the caller, which
    knows what language the reader speaks."""

    def __init__(self, reason: MeetingUrlRejection) -> None:
        self.reason = reason
        super().__init__(reason.value)


def normalize_meeting_url(value: str | None) -> str | None:
    """The meeting link in ``value``, or ``None`` if there is not one.

    An absent link and a blank one are the same thing — most events have
    no meeting to join, and a form that submits ``""`` for an untouched
    field must not be treated as an attempt at a link. Both give
    ``None``.

    Raises :class:`MeetingUrlRejected` when ``value`` holds something
    that is not an ``http(s)`` address.
    """
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if len(candidate) > MEETING_URL_MAX_LENGTH:
        raise MeetingUrlRejected(MeetingUrlRejection.TOO_LONG)
    if any(ch in _FORBIDDEN_CHARS for ch in candidate):
        raise MeetingUrlRejected(MeetingUrlRejection.NOT_A_WEB_ADDRESS)
    try:
        parts = urlsplit(candidate)
    except ValueError as exc:
        # ``urlsplit`` raises on a malformed IPv6 literal ("https://[::1")
        # and on a port that is not a number.
        raise MeetingUrlRejected(MeetingUrlRejection.NOT_A_WEB_ADDRESS) from exc
    if parts.scheme.lower() not in _ALLOWED_SCHEMES:
        raise MeetingUrlRejected(MeetingUrlRejection.NOT_A_WEB_ADDRESS)
    # ``@`` is only ever a userinfo separator in the authority: the host
    # itself cannot contain one, and a ``@`` later in the path or query
    # is ordinary. Checked before the host check so the more specific
    # explanation wins for "https://@evil.com".
    if "@" in parts.netloc:
        raise MeetingUrlRejected(MeetingUrlRejection.CREDENTIALS_IN_URL)
    try:
        host = parts.hostname
    except ValueError as exc:  # pragma: no cover - urlsplit rejects these first
        raise MeetingUrlRejected(MeetingUrlRejection.NOT_A_WEB_ADDRESS) from exc
    if not host:
        # "https:", "https://", "https:///room" — a scheme and no site.
        raise MeetingUrlRejected(MeetingUrlRejection.NOT_A_WEB_ADDRESS)
    return candidate


__all__ = [
    "MEETING_URL_MAX_LENGTH",
    "MeetingUrlRejected",
    "MeetingUrlRejection",
    "normalize_meeting_url",
]
