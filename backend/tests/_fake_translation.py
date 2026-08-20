# ruff: noqa: RUF001
# Transliteration tables are Cyrillic-next-to-Latin by definition.
"""A fake translation that survives the structural check.

The recording providers used across the translation tests used to echo
their input with a locale prefix: ``"Hello"`` came back as
``"[ru]Hello"``. That was fine while the pipeline only routed strings.
It stopped being fine when the orchestrator started validating what
came back (``services/translation/validation.py``) — English text
stored as a Russian translation is exactly the defect the check exists
to catch, and the fake was producing it on every call.

So the fake now transliterates: ``"Hello"`` → ``"[ru]Хелло"``. Not a
translation, but it has the property that matters here — it reads as
the language it claims to be — while staying deterministic and
readable in an assertion. The ``[locale]`` prefix is kept so existing
tests can still tell which row came from which target.

Markup, scripture markers, and placeholders are passed through
untouched, because the validator compares those between source and
translation and a fake that mangled them would fail for the wrong
reason.
"""

from __future__ import annotations

import re
from typing import Final

# Anything inside one of these must reach the output unchanged: HTML
# tags, scripture sentinels, and the placeholder shapes the system
# prompt promises to preserve.
#
# Both sentinel spellings, and ``EQV`` first because that is the one
# production writes. A fake that transliterated ``EQV0c02…`` into
# Cyrillic would be reproducing the exact defect the prefix was changed
# to prevent — see ``bible/substitution._marker_token``.
_PROTECTED: Final[re.Pattern[str]] = re.compile(
    r"(<[^>]*>"
    r"|EQV[0-9a-f]+"
    r"|VERSE_[0-9a-f]+"
    r"|\{[a-zA-Z_][a-zA-Z0-9_]*\}"
    r"|%\([a-zA-Z_][a-zA-Z0-9_]*\)[sdifr]"
    r"|%[sdifr]"
    r"|\[\d+\])"
)

_LATIN_TO_CYRILLIC: Final[dict[str, str]] = {
    "a": "а",
    "b": "б",
    "c": "ц",
    "d": "д",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "х",
    "i": "и",
    "j": "й",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "q": "к",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "v": "в",
    "w": "в",
    "x": "кс",
    "y": "ы",
    "z": "з",
}

_CYRILLIC_TO_LATIN: Final[dict[str, str]] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def _transliterate_char(ch: str, table: dict[str, str]) -> str:
    replacement = table.get(ch.lower())
    if replacement is None:
        return ch
    return replacement.capitalize() if ch.isupper() else replacement


def _transliterate(text: str, *, target_locale: str) -> str:
    table = _LATIN_TO_CYRILLIC if target_locale == "ru" else _CYRILLIC_TO_LATIN
    return "".join(_transliterate_char(ch, table) for ch in text)


def fake_translate(text: str, *, target_locale: str) -> str:
    """Return ``text`` rendered in ``target_locale``'s script, prefixed.

    Deterministic, reversible enough to read in a failure message, and
    — unlike the echo it replaces — it passes the structural check.
    """
    parts = _PROTECTED.split(text)
    # ``re.split`` with one capturing group alternates
    # unprotected / protected / unprotected / …
    rendered = "".join(
        part if index % 2 else _transliterate(part, target_locale=target_locale) for index, part in enumerate(parts)
    )
    return f"[{target_locale}]{rendered}"


__all__ = ["fake_translate"]
