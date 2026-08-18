# ruff: noqa: RUF001
# The tables below are Cyrillic and Latin side by side by definition.
"""The words this school always renders the same way.

What separates a professional translation from a competent one is
rarely a mistake. It is consistency: the same term, in the same place,
every time. A machine translating field by field has no memory between
calls, so `завет` becomes *Bund* in one lesson and *Testament* in the
next, `преподаватель` becomes *Dozent* in the course description and
*Lehrer* in the quiz — and a reader who studies here for a term feels
the seam without being able to name it.

Two decisions worth stating, because both could reasonably go the
other way:

**Register.** This is a Bible school in a Slavic Pentecostal
community, not a university and not a corporation. So `преподаватель`
is *Kursleiter*, not *Dozent* — production had *Dozent*, which is a
university lecturer and reads as borrowed clothing. `Церковь` as the
gathered people is *Gemeinde*; *Kirche* is the institution or the
building, and using it for a congregation quietly changes what the
sentence says.

**Only the terms actually present are sent.** Pasting thirty pairs
into every call would cost tokens on every string and bury the rules
that matter under a wall of vocabulary. `terms_in` scans the source
first, so a two-word answer option carries no glossary at all and a
lesson on the covenant carries exactly the lines about covenants.

Terms are keyed by their Russian form because that is the language
most course material is authored in, but each row carries all four, so
the table works for any direction — a German teacher writing in German
gets the same Ukrainian rendering a Russian one would.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode

# Each row: the concept in every language we serve. Order is ru, en, de, uk.
#
# Kept to terms where a translator could reasonably choose differently
# and where the choice matters to a reader: doctrine, the shape of the
# school, and the handful of words whose everyday meaning differs from
# their meaning here.
_TERMS: Final[tuple[tuple[str, str, str, str], ...]] = (
    # The church and its people
    ("церковь", "church", "Gemeinde", "церква"),
    ("община", "congregation", "Gemeinde", "громада"),
    ("собрание", "assembly", "Versammlung", "зібрання"),
    ("служение", "ministry", "Dienst", "служіння"),
    ("служитель", "minister", "Diener", "служитель"),
    ("пастор", "pastor", "Pastor", "пастор"),
    ("ученик", "disciple", "Jünger", "учень"),
    ("апостол", "apostle", "Apostel", "апостол"),
    ("пророк", "prophet", "Prophet", "пророк"),
    # Doctrine
    ("завет", "covenant", "Bund", "завіт"),
    # A covenant word, and the one the model would not stop calquing:
    # asked for "binding", flash-lite returns "зобов'язуюча" however
    # firmly the prompt forbids it — a participle Ukrainian does not
    # form. Naming the rendering here settles it, which is what a
    # glossary is for: the terms too important to leave to preference.
    ("обязывающий", "binding", "verpflichtend", "що зобов'язує"),
    ("благодать", "grace", "Gnade", "благодать"),
    ("покаяние", "repentance", "Buße", "покаяння"),
    ("спасение", "salvation", "Errettung", "спасіння"),
    ("оправдание", "justification", "Rechtfertigung", "виправдання"),
    ("благовестие", "the gospel", "die Verkündigung des Evangeliums", "благовістя"),
    ("проповедь", "sermon", "Predigt", "проповідь"),
    ("заповедь", "commandment", "Gebot", "заповідь"),
    ("Писание", "Scripture", "die Schrift", "Писання"),
    ("Пятидесятница", "Pentecost", "Pfingsten", "П'ятидесятниця"),
    ("Дух Святой", "the Holy Spirit", "der Heilige Geist", "Дух Святий"),
    # The school itself
    ("преподаватель", "teacher", "Kursleiter", "викладач"),
    ("студент", "student", "Teilnehmer", "студент"),
    ("урок", "lesson", "Lektion", "урок"),
    ("модуль", "module", "Modul", "модуль"),
    ("курс", "course", "Kurs", "курс"),
    ("аттестация", "assessment", "Prüfung", "атестація"),
    ("экзамен", "exam", "Abschlussprüfung", "іспит"),
    ("эссе", "essay", "Essay", "есе"),
    ("оценка", "grade", "Note", "оцінка"),
)

_INDEX: Final[dict[str, tuple[str, str, str, str]]] = {}
for _row in _TERMS:
    for _form in _row:
        _INDEX.setdefault(_form.lower(), _row)

_COLUMN: Final[dict[str, int]] = {"ru": 0, "en": 1, "de": 2, "uk": 3}


# Matches a term as a whole word, allowing the inflections these
# languages actually produce: "завета", "заветом", "Gemeinden",
# "громади". Deliberately loose at the end and strict at the start —
# a suffix is a form of the word, a prefix usually is not.
def _pattern(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(term)}\w{{0,4}}", re.IGNORECASE)


_PATTERNS: Final[dict[str, re.Pattern[str]]] = {form: _pattern(form) for form in _INDEX}


def terms_in(text: str, *, source_locale: LocaleCode, target_locale: LocaleCode) -> list[tuple[str, str]]:
    """The glossary pairs this particular text needs, and no others.

    Returns ``(source form, target form)`` for every term found in the
    text, deduplicated and in a stable order so two identical strings
    build an identical prompt — which keeps the ``source_hash``
    short-circuit and the duplicate-text dedupe honest.
    """
    if not text:
        return []
    src_col = _COLUMN.get(source_locale)
    tgt_col = _COLUMN.get(target_locale)
    if src_col is None or tgt_col is None or src_col == tgt_col:
        return []

    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row in _TERMS:
        source_form = row[src_col]
        target_form = row[tgt_col]
        if source_form.lower() in seen:
            continue
        if _PATTERNS[source_form.lower()].search(text):
            found.append((source_form, target_form))
            seen.add(source_form.lower())
    return found


def glossary_block(pairs: list[tuple[str, str]]) -> str:
    """Render the pairs as prompt lines, or an empty string for none."""
    if not pairs:
        return ""
    lines = "\n".join(f"  {source} → {target}" for source, target in pairs)
    return (
        "Terminology used by this school. Where the text uses one of these, "
        "render it exactly this way — the same word every time, across every "
        "lesson:\n" + lines + "\n\n"
    )


__all__ = ["glossary_block", "terms_in"]
