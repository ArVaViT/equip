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

**A sense, not a spelling.** Every word here also means something else
somewhere else. `grace` is a period a lender allows, `redemption` is
what a bond is worth at maturity, `minister` is in the cabinet,
«оценка» is what a surveyor puts on a building, «курс» is an exchange
rate. The school teaches three biblical courses today and will teach
other subjects, so the register asks for its rendering *where the word
carries its meaning* and says so in the prompt — and the check that
reads the answer back names what it saw without arguing, because it
cannot tell a dropped term from a declined one and the model already
had the table in front of it when it chose.

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

from app.services.bible.references import parse_references

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
    # People and things a reader would notice being renamed. Each of
    # these was got wrong somewhere in production, and none of them is a
    # matter of taste: an editor reading the Ukrainian corpus found the
    # Ethiopian eunuch of Acts 8 turned into a Pentecostal —
    # "п'ятидесятник" — which is what the readers of this school call
    # themselves.
    ("евнух", "eunuch", "Kämmerer", "скопець"),
    ("наставник", "mentor", "Mentor", "наставник"),
    ("притча", "parable", "Gleichnis", "притча"),
    ("праведность", "righteousness", "Gerechtigkeit", "праведність"),
    ("искупление", "redemption", "Erlösung", "викуплення"),
    ("первосвященник", "high priest", "Hohepriester", "первосвященик"),
    ("язычник", "Gentile", "Heide", "язичник"),
    ("родословие", "genealogy", "Geschlechtsregister", "родовід"),
)

_INDEX: Final[dict[str, tuple[str, str, str, str]]] = {}
for _row in _TERMS:
    for _form in _row:
        _INDEX.setdefault(_form.lower(), _row)

_COLUMN: Final[dict[str, int]] = {"ru": 0, "en": 1, "de": 2, "uk": 3}

#: Phrases where a registered word is part of a name and carries none of
#: its register meaning. Removed before the table is consulted, in every
#: language, because the pipeline reads in all directions.
#:
#: Kept to fixed names, and short. It is not the place to record that
#: `grace` is also a period a lender allows — that list has no end,
#: because every subject the school has not taught yet would add to it.
#: The prompt says the conditional thing instead; see ``glossary_block``.
#: The book names, which are the other half of this job, come from
#: ``bible.references`` rather than from here.
_NOT_A_TERM_HERE: Final[tuple[str, ...]] = (
    "новый завет",
    "нового завета",
    "новом завете",
    "новым заветом",
    "ветхий завет",
    "ветхого завета",
    "ветхом завете",
    "ветхим заветом",
    "new testament",
    "old testament",
    "neues testament",
    "alten testament",
    "altes testament",
    "новий завіт",
    "нового завіту",
    "старий завіт",
    "старого завіту",
)


# Ukrainian words carry an apostrophe, and the corpus now carries two of
# them: the typographic U+2019 that `typography.py` normalises to, and
# the typewriter U+0027 these tables were written with. Comparing the two
# spellings as different words made the register stop recognising
# the Ukrainian word for Pentecost the day typography shipped — a check
# quietly going blind, which is worse than a check that never existed.
_APOSTROPHES = str.maketrans({"\u2019": "'", "\u02bc": "'", "\u2018": "'"})


def _fold_apostrophes(text: str) -> str:
    return text.translate(_APOSTROPHES)


_VOWELS: Final[str] = "аеёиоуыэюяіїєaeiouäöü"

#: Case and number endings, and nothing else.
#:
#: The matcher used to accept any four letters after a term, which was
#: never a rule about language — it was a guess at how long an ending
#: is. It cost the school «курсив» and «курсор» read as «курс»,
#: "example" read as "exam", "Notebook" read as "Note": a word that
#: merely *starts* like a term is not that term, and the register was
#: telling the model to render the cursor as a course.
#:
#: Endings are a closed class. New subject matter brings new vocabulary;
#: it does not bring new declensions, which is why this is the one kind
#: of list that does not have to grow when the school teaches something
#: other than the Bible.
#:
#: Derivations are deliberately absent. «апостольский», "prophetic" and
#: "pastoral" change the part of speech, and the register has no opinion
#: about them — "prophetic" is *prophetisch*, not *Prophet*, so firing
#: the glossary line there was arguing for the wrong word anyway.
_CYRILLIC_ENDINGS: Final[tuple[str, ...]] = (
    "а", "е", "ё", "є", "и", "і", "ї", "й", "м", "о", "у", "х", "ы", "ь", "ю", "я",
    "ам", "ах", "ев", "ей", "ем", "ём", "єм", "им", "их", "ів", "їв", "ми",
    "ов", "ой", "ом", "ою", "ью", "ья", "ье", "ям", "ях",
    "ами", "еві", "ові", "ями",
)  # fmt: skip

_LATIN_ENDINGS: Final[tuple[str, ...]] = ("e", "en", "es", "n", "s", "se", "sen", "ses")


def _is_cyrillic(term: str) -> bool:
    return any("Ѐ" <= char <= "ӿ" for char in term)


def _endings(term: str) -> tuple[str, ...]:
    return _CYRILLIC_ENDINGS if _is_cyrillic(term) else _LATIN_ENDINGS


def _bases(term: str) -> tuple[str, ...]:
    """The dictionary form, and the stem its oblique cases are built on.

    A Slavic noun rarely inflects by *adding* to its dictionary form. It
    replaces an ending the dictionary form already carries: «служение»
    becomes «служения», «церковь» becomes «церкви», «община» becomes
    «общины». A matcher anchored on the whole dictionary form sees none
    of those, and the old one did not — the register went quiet on a
    thousand strings that use its own terms.

    So a Cyrillic term also offers its stem: the form with its final
    vowel removed, after any soft sign. That is the move ``_stems``
    already makes on the other side of the pipeline — it drops the last
    vowel of a truncated head so «учень» is still found in «учня» — and
    it exists for the same reason here.

    A stem is never accepted bare, only with an ending after it.
    «служени» is not a word and must not stand where the term was
    expected.
    """
    folded = _fold_apostrophes(term)
    if not _is_cyrillic(folded):
        return (folded,)
    bases = [folded]
    core = folded.rstrip("ьй")  # «служитель» → «служител» → «служителя»
    if len(core) > 3:
        if core != folded:
            bases.append(core)
        if core[-1].lower() in _VOWELS:
            bases.append(core[:-1])  # «служение» → «служени», «община» → «общин»
        elif core != folded and core[-2].lower() in _VOWELS:
            bases.append(core[:-2] + core[-1])  # «церковь» → «церкв», «учень» → «учн»
    return tuple(dict.fromkeys(bases))


def _pattern(term: str) -> re.Pattern[str]:
    """Match ``term`` as a whole word, in any form its language declines it into.

    Strict at both ends now. It was always strict at the start — a
    prefix is not a form of a word — and it is strict at the end too:
    what follows the term has to be an ending, and the ending has to be
    where the word stops. «Bundeslade» is no longer «Bund», which costs
    the check side nothing: ``missing_terms`` looks for the target word
    *inside* the translation, so a German compound still satisfies the
    term it is built from.
    """
    endings = "|".join(sorted(map(re.escape, _endings(term)), key=len, reverse=True))
    dictionary_form, *stems = (re.escape(base) for base in _bases(term))
    alternatives = [rf"{dictionary_form}(?:{endings})?", *(rf"{stem}(?:{endings})" for stem in stems)]
    return re.compile(rf"(?<!\w)(?:{'|'.join(alternatives)})(?!\w)", re.IGNORECASE)


_PATTERNS: Final[dict[str, re.Pattern[str]]] = {form: _pattern(form) for form in _INDEX}


def _blank_scripture_references(text: str, locale: str) -> str:
    """Erase Bible citations, keeping the string the same length.

    A book name is a name, exactly like «Новый Завет» in
    ``_NOT_A_TERM_HERE`` — and one of them is spelled like a term this
    table decides. «Притчи 3:1» is the book of Proverbs, *Sprüche*,
    «Приповісті»; it is not a parable and must not be told to become
    *Gleichnis*. Measured on the live catalogue, that is 25 of the
    register's complaints, every one of them wrong.

    ``bible/references.py`` already knows every book in every language
    this school serves, so this asks it rather than growing a second
    list of names that would go stale the first time a book was
    renamed. Blanked in place, not deleted, because the caller still
    holds offsets into this string.
    """
    parsed = parse_references(text, locale)
    if not parsed:
        return text
    chars = list(text)
    for reference in parsed:
        start, end = reference.span
        chars[start:end] = " " * (end - start)
    return "".join(chars)


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

    folded = _blank_scripture_references(_fold_apostrophes(text), source_locale)
    # A term inside a fixed name is not that term. «Новый Завет» is the
    # New Testament, not a covenant, and telling the model to render it
    # "Bund" would turn a correct translation into a wrong one — the
    # register was measured doing exactly that on ten of the corpus's
    # rows before this line existed.
    lowered = folded.lower()
    for phrase in _NOT_A_TERM_HERE:
        lowered = lowered.replace(phrase, " ")
    folded = lowered
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row in _TERMS:
        source_form = row[src_col]
        target_form = row[tgt_col]
        if source_form.lower() in seen:
            continue
        if _PATTERNS[source_form.lower()].search(folded):
            found.append((source_form, target_form))
            seen.add(source_form.lower())
    return found


def known_forms(locale: LocaleCode) -> frozenset[str]:
    """Every word this table already decides, in ``locale``.

    Exposed for ``translation/term_memory.py``, which learns the school's
    vocabulary from what a course has already been translated into and
    must not learn any of *these*: the register is authoritative, and two
    answers to the same question in one prompt is how a hint starts
    losing arguments it should win.
    """
    column = _COLUMN.get(locale)
    if column is None:
        return frozenset()
    return frozenset(row[column] for row in _TERMS)


def glossary_block(pairs: list[tuple[str, str]]) -> str:
    """Render the pairs as prompt lines, or an empty string for none.

    The instruction is about a *sense*, not a spelling, and it now says
    so. It used to read "where the text uses one of these, render it
    exactly this way", which is true of the three Bible courses and
    false of the next subject the school teaches: `grace` is a period a
    lender allows, `redemption` is what a bond is worth at maturity,
    `minister` is in the cabinet, `оценка` is what a surveyor puts on a
    building. Told to render those exactly this way, the model does —
    and the register turns a correct translation into a wrong one.

    The condition costs nothing where the word *is* theological, which
    is the whole reason this table exists: the pair is still stated, and
    still stated absolutely. What the sentence gives up is the claim
    that a word has only one sense, which was never the school's to
    make. It is also what ``validation._check_glossary`` already says
    when it reads the answer back — the two halves of the register now
    tell the model the same thing.
    """
    if not pairs:
        return ""
    lines = "\n".join(f"  {source} → {target}" for source, target in pairs)
    return (
        "Terminology used by this school. Where the text uses one of these "
        "words in the sense the school means, render it exactly this way — "
        "the same word every time, across every lesson:\n"
        + lines
        + "\nWhere the same word carries an everyday sense instead — part of "
        "a name, or the meaning it has in another subject — translate that "
        "sense as it needs to be translated.\n\n"
    )


def _stems(term: str) -> tuple[str, ...]:
    """Beginnings of ``term`` that any inflection of it must contain.

    A prefix of the dictionary form is nearly always enough — German and
    Ukrainian decline at the end. Nearly: Ukrainian also drops a vowel in
    the middle, so «учень» becomes «учня» and «учнів», and a check
    looking for «учен» declares a perfectly good translation missing. It
    did, twelve times, on the day this was measured.

    So the second stem is the first with its last vowel removed. Cheap,
    ugly, and it turns twelve false alarms into none without letting a
    replaced word through: «п'ятидесятник» still shares no beginning
    with «скопець».

    A multi-word term is judged by its longest word — the article moves
    with the case («die Schrift» / «der Schrift») and carries no meaning
    worth checking.
    """
    core = max(_fold_apostrophes(term).lower().split(), key=len, default="")
    if not core:
        return ()
    head = core[: max(4, len(core) - 3)]
    stems = {head}
    for index in range(len(head) - 1, 1, -1):
        if head[index] in "аеёиоуыэюяіїєaeiouäöü":
            stems.add(head[:index] + head[index + 1 :])
            break
    return tuple(stems)


def missing_terms(
    source: str,
    translation: str,
    *,
    source_locale: LocaleCode,
    target_locale: LocaleCode,
) -> list[tuple[str, str]]:
    """Register entries the source used and the translation did not.

    The same table, read the other way round. As a prompt it is a
    request; here it is a check, and it catches the one class of defect
    structural validation is blind to by design — a word swapped for
    another word. Nothing is lost, nothing is malformed, the markup
    matches and the length is right; the sentence simply says something
    else. That is how the Ethiopian eunuch became a Pentecostal and
    stayed that way, servable and wrong, until a person read it.

    Deliberately forgiving in one direction: a term is satisfied by any
    inflection of the target form, because German declines and Ukrainian
    declines and demanding the dictionary form would flag correct prose
    all day. It reports what is absent entirely.
    """
    if not source or not translation:
        return []
    absent: list[tuple[str, str]] = []
    folded_translation = _fold_apostrophes(translation).lower()
    for source_form, target_form in terms_in(source, source_locale=source_locale, target_locale=target_locale):
        if not any(stem in folded_translation for stem in _stems(target_form)):
            absent.append((source_form, target_form))
    return absent


__all__ = ["glossary_block", "known_forms", "missing_terms", "terms_in"]
