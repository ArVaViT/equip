# ruff: noqa: RUF001, RUF003
# The rules here are about characters: an en dash inside a verse range
# and a Cyrillic book name in the comment explaining it are the
# subject matter, not typos.
"""Structural validation of a translation against its source.

Why this exists
---------------

Before this module, ``status='ok'`` on a ``content_versions`` row meant
"the HTTP call did not raise". ``gemini._parse_response`` checks the
*envelope* — are there candidates, are there parts, did ``finishReason``
say STOP, is the text non-empty — and nothing at all checks what came
back. A response that dropped a scripture marker, lost half the HTML,
answered in the wrong language, or politely explained that it could not
translate the passage is a perfectly well-formed envelope, and the whole
platform reads its ``ok`` as "this translation is good".

That gap is what makes the publishing rule unenforceable. "Do not
publish until every language is translated **and checked**" needs
something that can say *checked*, and a status that means "no exception
was raised" cannot.

What this can and cannot do
---------------------------

It checks the promises the system prompt makes, and only those:
markers, markup, placeholders, numbers, language, length, and the
model talking to us instead of translating. Every one of them is a
property of the *pair* (source, translation) that can be decided
mechanically.

It does not judge whether the translation is *good*. Nothing local can:
research on this is consistent that quality in the general case is not
measurable without a reader of the language. What it does is catch the
failures that are structural, and those are the ones that silently
corrupt a lesson — a lost verse marker leaves a student reading
``VERSE_a3f9c2`` where scripture should be.

The output is advisory to the caller: a list of issues, each with a
code and a sentence. The orchestrator decides what to do with them —
today, park the row as ``needs_review`` instead of ``ok``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from app.core.sanitize import strip_tags
from app.services.language_detection import detect_locale

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode
    from app.services.translation.protocol import ContentKind

# ``VERSE_<hex>`` sentinels from ``app.services.bible.substitution``.
# These stand in for canonical scripture during the model call and are
# restored afterwards; one that does not come back means a student
# reads the raw token where the verse belongs.
_MARKER_RE: Final[re.Pattern[str]] = re.compile(r"VERSE_[0-9a-f]+")

# Tag names only — attributes get rewritten by translation (an
# ``alt=""`` legitimately changes language), the structure must not.
_TAG_NAME_RE: Final[re.Pattern[str]] = re.compile(r"<\s*/?\s*([a-zA-Z][a-zA-Z0-9]*)")

# The placeholder shapes rule 4 of the system prompt promises to keep.
_PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(
    r"\{[a-zA-Z_][a-zA-Z0-9_]*\}"  # {variable}
    r"|%\([a-zA-Z_][a-zA-Z0-9_]*\)[sdifr]"  # %(name)s
    r"|%[sdifr]"  # %s
    r"|\[\d+\]"  # [1]
)

# Chapter-and-verse references ("1:26", "3.16"), and only those.
#
# Bare integers were checked here first, and a run over the production
# corpus showed why they cannot be: the source table lists "3–4 Царств"
# and the correct English is "1–2 Kings" — the Slavic and English
# traditions number the books of Kings differently, so a faithful
# translation legitimately changes the digits. Years and counts move
# for related reasons. A verse reference does not: Genesis 1:26 is
# 1:26 in every language we serve, and losing one is what leaves a
# student unable to find the passage.
_VERSE_REF_RE: Final[re.Pattern[str]] = re.compile(r"\d+\s*[:.]\s*\d+(?:\s*[-–]\s*\d+)?")

# The fence the user prompt wraps content in. If either shape comes
# back, the model echoed the scaffolding instead of translating inside
# it — including the defanged form the prompt builder writes.
_FENCE_MARKERS: Final[tuple[str, ...]] = ("===BEGIN", "===END", "===_BEGIN", "===_END")

# Below this many characters, a length ratio says nothing: "Ja" against
# "Yes" is a 1.5x expansion and perfectly correct.
_MIN_CHARS_FOR_RATIO: Final[int] = 40

# German runs long against English, English runs short against Russian.
# These bounds are deliberately loose — they are here to catch a
# truncated paragraph or an appended explanation, not to police style.
_MIN_LENGTH_RATIO: Final[float] = 0.4
_MAX_LENGTH_RATIO: Final[float] = 2.5

# Below this, an unchanged string is ordinary: proper nouns, "Amen",
# numerals, a title that is a name. Above it, identical output means
# the model returned its input.
_MIN_CHARS_FOR_IDENTITY: Final[int] = 25

# Content kinds whose text is a single short answer or heading, where
# an expansion is itself the failure the prompt warns about.
_SHORT_KINDS: Final[frozenset[str]] = frozenset({"title", "quiz_option"})
_SHORT_KIND_MAX_RATIO: Final[float] = 3.0

# …and only when the growth is also large in absolute terms. A quiz
# titled "Q" renders as "Вопрос" in Russian: six times the length, and
# obviously fine. Production had exactly that row.
_SHORT_KIND_MIN_GROWTH_CHARS: Final[int] = 40


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One structural defect found in a translation.

    ``code`` is stable and greppable — it goes into logs and, once the
    review queue exists, into a filter. ``detail`` is the sentence a
    human reads when deciding what to do with the row.
    """

    code: str
    detail: str


def _markers(text: str) -> list[str]:
    return sorted(_MARKER_RE.findall(text))


def _tag_names(text: str) -> list[str]:
    return sorted(name.lower() for name in _TAG_NAME_RE.findall(text))


def _placeholders(text: str) -> list[str]:
    return sorted(_PLACEHOLDER_RE.findall(text))


def _verse_refs(text: str) -> list[str]:
    return sorted(re.sub(r"\s+", "", ref) for ref in _VERSE_REF_RE.findall(text))


def _normalised_for_identity(text: str) -> str:
    return " ".join(strip_tags(text).lower().split())


def _check_markers(source: str, translated: str) -> ValidationIssue | None:
    expected = _markers(source)
    if not expected:
        return None
    got = _markers(translated)
    if expected == got:
        return None
    missing = sorted(set(expected) - set(got))
    added = sorted(set(got) - set(expected))
    parts = []
    if missing:
        parts.append(f"lost {len(missing)} ({', '.join(missing[:3])})")
    if added:
        parts.append(f"invented {len(added)}")
    if not parts:
        parts.append("returned a different number of them")
    return ValidationIssue(
        code="scripture_marker_mismatch",
        detail=(
            f"Scripture markers do not match the source: {'; '.join(parts)}. "
            "A marker that does not come back leaves the raw token where the verse belongs."
        ),
    )


def _check_tags(source: str, translated: str) -> ValidationIssue | None:
    expected = _tag_names(source)
    if not expected:
        return None
    got = _tag_names(translated)
    if expected == got:
        return None
    return ValidationIssue(
        code="markup_mismatch",
        detail=(
            f"Markup changed: source has {len(expected)} tags "
            f"({', '.join(sorted(set(expected)))}), translation has {len(got)} "
            f"({', '.join(sorted(set(got))) or 'none'})."
        ),
    )


def _check_placeholders(source: str, translated: str) -> ValidationIssue | None:
    expected = _placeholders(source)
    if not expected:
        return None
    got = _placeholders(translated)
    if expected == got:
        return None
    return ValidationIssue(
        code="placeholder_mismatch",
        detail=f"Placeholders changed: source has {expected}, translation has {got}.",
    )


def _check_verse_refs(source: str, translated: str) -> ValidationIssue | None:
    expected = _verse_refs(source)
    if not expected:
        return None
    missing = sorted(set(expected) - set(_verse_refs(translated)))
    if not missing:
        # Extra references where none were lost is usually a reference
        # the model spelled out; not worth stopping a course over.
        return None
    return ValidationIssue(
        code="verse_reference_lost",
        detail=(
            f"Chapter-and-verse references present in the source are missing from the "
            f"translation: {', '.join(missing[:5])}. A student cannot look up a passage "
            "whose reference did not survive."
        ),
    )


def _check_fence(translated: str) -> ValidationIssue | None:
    if not any(marker in translated for marker in _FENCE_MARKERS):
        return None
    return ValidationIssue(
        code="fence_leaked",
        detail=(
            "The translation contains the prompt's fence markers, so the model echoed "
            "the scaffolding instead of translating the text inside it."
        ),
    )


def _check_identity(
    source: str,
    translated: str,
    *,
    source_locale: LocaleCode,
    target_locale: LocaleCode,
) -> ValidationIssue | None:
    if source_locale == target_locale:
        return None
    normalised = _normalised_for_identity(source)
    if len(normalised) < _MIN_CHARS_FOR_IDENTITY:
        return None
    if normalised != _normalised_for_identity(translated):
        return None
    return ValidationIssue(
        code="not_translated",
        detail=(
            f"The {target_locale} text is identical to the {source_locale} source. "
            "Either the model returned its input, or the source was not in the language we think it is."
        ),
    )


def _check_language(translated: str, *, target_locale: LocaleCode) -> ValidationIssue | None:
    detected = detect_locale(translated)
    if detected is None or detected == target_locale:
        # ``None`` means the detector had no signal — short strings,
        # proper nouns, two languages of one script it cannot separate.
        # It refuses to guess, and so do we.
        return None
    return ValidationIssue(
        code="wrong_language",
        detail=(
            f"The translation reads as {detected}, not {target_locale}. "
            "A student who chose that language would be served text they did not ask for."
        ),
    )


def _check_length(
    source: str,
    translated: str,
    *,
    content_kind: ContentKind,
) -> ValidationIssue | None:
    source_text = _normalised_for_identity(source)
    if len(source_text) < _MIN_CHARS_FOR_RATIO:
        if content_kind in _SHORT_KINDS and source_text:
            translated_length = len(_normalised_for_identity(translated))
            ratio = translated_length / len(source_text)
            grew_by = translated_length - len(source_text)
            if ratio > _SHORT_KIND_MAX_RATIO and grew_by >= _SHORT_KIND_MIN_GROWTH_CHARS:
                return ValidationIssue(
                    code="length_suspicious",
                    detail=(
                        f"A {content_kind} grew {ratio:.1f}x. The prompt asks the model not to "
                        "expand a heading or a one-line answer into a paragraph."
                    ),
                )
        return None

    translated_text = _normalised_for_identity(translated)
    ratio = len(translated_text) / len(source_text)
    if _MIN_LENGTH_RATIO <= ratio <= _MAX_LENGTH_RATIO:
        return None
    shape = "shorter" if ratio < _MIN_LENGTH_RATIO else "longer"
    return ValidationIssue(
        code="length_suspicious",
        detail=(
            f"The translation is {ratio:.2f}x the length of the source — much {shape} than "
            "any language pair we serve explains. Usually a truncated response or an "
            "explanation the model appended."
        ),
    )


# A run of source words long enough that finding it verbatim in the
# translation means it was not translated. Ten words is roughly a
# clause; below that, legitimate coincidence is common — proper names,
# a list of book titles, a formula.
_UNTRANSLATED_RUN_WORDS: Final[int] = 10

# ...and long enough in characters that ten short tokens (numbers, a
# reference list, initials) cannot reach the bar on their own.
#
# 45 rather than 60: ten English words are shorter than ten Russian
# ones, and at 60 the rule caught the Russian verse left inside English
# prose but not the English verse left inside German. Measured over
# every machine translation in production (2164 pairs) — six flagged,
# all six genuine, none false.
_UNTRANSLATED_RUN_CHARS: Final[int] = 45


def _words_for_runs(text: str) -> list[str]:
    """Words of prose, with markup and sentinels removed.

    Markers stand in for canonical scripture and are identical on both
    sides by design; a placeholder is meant to survive verbatim. Neither
    is evidence of anything.
    """
    plain = _PLACEHOLDER_RE.sub(" ", _MARKER_RE.sub(" ", strip_tags(text)))
    return plain.lower().split()


def _check_untranslated_run(
    source: str,
    translated: str,
    *,
    source_locale: LocaleCode,
    target_locale: LocaleCode,
) -> ValidationIssue | None:
    """Catch a clause of the source surviving verbatim in the translation.

    The whole-string version of this (``not_translated``) only fires
    when nothing was translated at all. What production actually
    produced was subtler and worse: a German sentence wrapping an
    English verse, because the prompt tells the model to leave quoted
    Scripture untouched and the substitution layer had not yet learned
    to recognise a quotation outside a blockquote. To a German reader
    that is not a citation — it is a sentence they cannot read, in the
    middle of one they can.

    Ten consecutive words is the bar, and the pair of languages has to
    actually differ; ``en``→``en`` is not a translation.
    """
    if source_locale == target_locale:
        return None

    source_words = _words_for_runs(source)
    if len(source_words) < _UNTRANSLATED_RUN_WORDS:
        return None
    haystack = " ".join(_words_for_runs(translated))

    for start in range(len(source_words) - _UNTRANSLATED_RUN_WORDS + 1):
        run = " ".join(source_words[start : start + _UNTRANSLATED_RUN_WORDS])
        if len(run) < _UNTRANSLATED_RUN_CHARS:
            continue
        if run in haystack:
            return ValidationIssue(
                code="untranslated_run",
                detail=(
                    f"A run of {_UNTRANSLATED_RUN_WORDS} words survives verbatim from the "
                    f"{source_locale} source: {run[:80]!r}. Usually a quotation the model "
                    "was told to leave alone and nothing restored in the target language."
                ),
            )
    return None


def validate_translation(
    *,
    source: str,
    translated: str,
    source_locale: LocaleCode,
    target_locale: LocaleCode,
    content_kind: ContentKind = "plain",
) -> list[ValidationIssue]:
    """Return every structural defect in ``translated`` against ``source``.

    An empty list means the translation kept every promise this module
    knows how to check. It does not mean the translation is good — see
    the module docstring.
    """
    if not translated.strip():
        return [
            ValidationIssue(
                code="empty",
                detail="The translation is empty.",
            )
        ]

    issues = [
        _check_fence(translated),
        _check_markers(source, translated),
        _check_tags(source, translated),
        _check_placeholders(source, translated),
        _check_verse_refs(source, translated),
        _check_identity(
            source,
            translated,
            source_locale=source_locale,
            target_locale=target_locale,
        ),
        _check_language(translated, target_locale=target_locale),
        _check_untranslated_run(
            source,
            translated,
            source_locale=source_locale,
            target_locale=target_locale,
        ),
        _check_length(source, translated, content_kind=content_kind),
    ]
    return [issue for issue in issues if issue is not None]


def summarise(issues: list[ValidationIssue]) -> str:
    """One-line summary for the row's ``review_reason`` column."""
    return " ".join(f"[{issue.code}] {issue.detail}" for issue in issues)


__all__ = ["ValidationIssue", "summarise", "validate_translation"]
