"""Source-language detection for course-authored text.

Replaces the ``source_locale = teacher.preferred_locale`` shortcut
that conflated the teacher's UI language with the language they
actually authored content in. The bug it fixes: an English-UI
teacher who authored a Russian course ended up with
``courses.source_locale='en'``, the translation pipeline thought
the course was already in English, and Russian students saw the
Russian text labelled as English (while English students never got
a translation).

The Equip platform currently supports two locales (``ru``, ``en``)
that live in completely disjoint Unicode blocks — Cyrillic
(U+0400..U+04FF) vs Basic Latin — so a character-counting heuristic
is both perfectly accurate AND zero-dependency. If the supported
set ever widens (Spanish, German, Ukrainian — anything that shares
script with English / Russian), swap in a real detector like
``lingua-py`` here without changing the call sites.

Contract
--------

``detect_locale(text)``:
* Returns ``"ru"`` or ``"en"`` when at least ``_MIN_LETTER_COUNT``
  alphabetic characters of one script dominate the input.
* Returns ``None`` when there's no usable signal (empty, whitespace,
  digits / punctuation only, below the threshold). The caller is
  expected to fall back to the teacher's UI locale in that case.
* Is forgiving of HTML tags, emojis, numbers, and punctuation —
  they're ignored, only letters in the two supported scripts
  contribute to the decision.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode

# Minimum number of script-tagged letters before the detector is
# willing to commit to a locale. Below this we return ``None`` so
# the caller falls back to a deterministic default (teacher UI).
#
# 3 is empirically the right number for our content: it catches
# single-word titles like "Тайтл" (5 Cyrillic letters), "Genesis"
# (7 Latin letters), and "Yes" / "Хай" while rejecting "Hi" / "Да"
# which are too short to disambiguate from acronyms or interjections.
_MIN_LETTER_COUNT: Final[int] = 3

# Cyrillic block — covers Russian (and Ukrainian / Bulgarian /
# Serbian Cyrillic, all of which would normalise to ``ru`` if we
# ever needed them; that decision lives outside this module).
_CYRILLIC_START: Final[int] = 0x0400
_CYRILLIC_END: Final[int] = 0x04FF


def detect_locale(text: str | None) -> LocaleCode | None:
    """Return the detected locale, or ``None`` if the input is too short
    or has no script signal.

    The decision rule is character-count majority among letters in
    the two supported scripts. Non-letter characters (digits,
    punctuation, whitespace, emojis, HTML tag chars except their
    inner names) are ignored.
    """
    if not text:
        return None

    cyrillic = 0
    latin = 0
    for ch in text:
        codepoint = ord(ch)
        if _CYRILLIC_START <= codepoint <= _CYRILLIC_END and ch.isalpha():
            cyrillic += 1
        elif ch.isascii() and ch.isalpha():
            latin += 1

    total = cyrillic + latin
    if total < _MIN_LETTER_COUNT:
        return None
    return "ru" if cyrillic > latin else "en"
