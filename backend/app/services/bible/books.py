"""Canonical 66-book Bible map + alias lookup for every served language.

Each canonical slug (lower-case, no spaces — e.g. ``acts``,
``1corinthians``) maps to a set of aliases used in printed references.
``find_book`` is a fast normalize-and-lookup that returns the canonical
slug for any reasonable spelling, or ``None``.

This file used to *write* a German or Ukrainian reference and be unable
to *read* one back. ``_DISPLAY_NAMES`` already knew to print ``Apg.``,
``1. Mose`` and ``Дії``; the alias table listed Russian and English
only, so ``find_book("Apg.")`` was ``None``. The consequence was not a
crash anywhere: ``pre_substitute`` simply never fired for a German- or
Ukrainian-authored course, so every quoted verse went to the model as
ordinary prose to be re-worded — precisely the failure the whole
substitution layer exists to prevent (#990). It never bit because all
four live courses are ``source_locale='ru'``.

So the abbreviations are no longer written twice: every entry of
``_DISPLAY_NAMES`` is registered as an alias automatically, which makes
"what we print is what we can read" true by construction rather than by
diligence. ``_LOCALE_ALIASES`` adds only what a display table cannot
hold — the full names (``Apostelgeschichte``, ``Дії апостолів``) and the
second spellings a real author uses (``Hoheslied`` / ``Hohelied``).
"""

from __future__ import annotations

import re

# Canonical book ordering follows the Protestant 66-book canon used by
# both KJV and Synodal RU. Slug strings double as the keys in the
# bundled JSON Bible files (``acts.1.8`` → text).

# Exposed for ``references.py`` to build its regex from the same aliases
# we recognize in ``find_book`` — keeping a single source of truth.
_BOOKS: tuple[tuple[str, tuple[str, ...]], ...] = (
    # OT
    ("genesis", ("genesis", "gen", "ge", "gn", "бытие", "быт", "бт")),
    ("exodus", ("exodus", "exod", "exo", "ex", "исход", "исх")),
    ("leviticus", ("leviticus", "lev", "lv", "левит", "лев")),
    ("numbers", ("numbers", "num", "nm", "числа", "чис", "числ")),
    ("deuteronomy", ("deuteronomy", "deut", "dt", "второзаконие", "втор")),
    ("joshua", ("joshua", "josh", "jos", "иисус навин", "иис нав", "нав")),
    ("judges", ("judges", "judg", "jdg", "судьи", "суд")),
    ("ruth", ("ruth", "руфь", "руф")),
    ("1samuel", ("1samuel", "1 samuel", "1sam", "1 sam", "i samuel", "1 царств", "1 цар", "1цар")),
    ("2samuel", ("2samuel", "2 samuel", "2sam", "2 sam", "ii samuel", "2 царств", "2 цар", "2цар")),
    ("1kings", ("1kings", "1 kings", "1kgs", "1 kgs", "i kings", "3 царств", "3 цар", "3цар")),
    ("2kings", ("2kings", "2 kings", "2kgs", "2 kgs", "ii kings", "4 царств", "4 цар", "4цар")),
    ("1chronicles", ("1chronicles", "1 chronicles", "1chr", "1 chr", "1 паралипоменон", "1 пар", "1пар")),
    ("2chronicles", ("2chronicles", "2 chronicles", "2chr", "2 chr", "2 паралипоменон", "2 пар", "2пар")),
    ("ezra", ("ezra", "ezr", "ездра", "езд")),
    ("nehemiah", ("nehemiah", "neh", "неемия", "неем")),
    ("esther", ("esther", "esth", "est", "есфирь", "есф")),
    ("job", ("job", "jb", "иов", "иов")),
    ("psalms", ("psalms", "psalm", "ps", "psa", "псалтирь", "псалом", "пс")),
    ("proverbs", ("proverbs", "prov", "pr", "притчи", "притч", "прит")),
    ("ecclesiastes", ("ecclesiastes", "eccl", "eccles", "екклесиаст", "еккл")),
    ("songofsolomon", ("songofsolomon", "song of solomon", "song", "sos", "песнь песней", "песн")),
    ("isaiah", ("isaiah", "isa", "is", "исаия", "ис")),
    ("jeremiah", ("jeremiah", "jer", "иеремия", "иер")),
    ("lamentations", ("lamentations", "lam", "плач иеремии", "плач")),
    ("ezekiel", ("ezekiel", "ezek", "иезекииль", "иез")),
    ("daniel", ("daniel", "dan", "дан", "даниил")),
    ("hosea", ("hosea", "hos", "осия", "ос")),
    ("joel", ("joel", "иоиль", "иоил")),
    ("amos", ("amos", "ам", "амос")),
    ("obadiah", ("obadiah", "obad", "авд", "авдий")),
    ("jonah", ("jonah", "jon", "иона", "ион")),
    ("micah", ("micah", "mic", "мих", "михей")),
    ("nahum", ("nahum", "nah", "наум")),
    ("habakkuk", ("habakkuk", "hab", "авв", "аввакум")),
    ("zephaniah", ("zephaniah", "zeph", "соф", "софония")),
    ("haggai", ("haggai", "hag", "агг", "аггей")),
    ("zechariah", ("zechariah", "zech", "зах", "захария")),
    ("malachi", ("malachi", "mal", "мал", "малахия")),
    # NT
    ("matthew", ("matthew", "matt", "mt", "матфей", "мф", "матф", "мт", "от матфея")),
    ("mark", ("mark", "mk", "марк", "мк", "мар", "от марка")),
    ("luke", ("luke", "lk", "лука", "лк", "лук", "от луки")),
    ("john", ("john", "jn", "иоанн", "ин", "иоан", "от иоанна")),
    ("acts", ("acts", "ac", "деяния", "деян", "деяния апостолов")),
    ("romans", ("romans", "rom", "рим", "римлянам", "к римлянам")),
    (
        "1corinthians",
        ("1corinthians", "1 corinthians", "1cor", "1 cor", "i corinthians", "1 коринфянам", "1 кор", "1кор"),
    ),
    (
        "2corinthians",
        ("2corinthians", "2 corinthians", "2cor", "2 cor", "ii corinthians", "2 коринфянам", "2 кор", "2кор"),
    ),
    ("galatians", ("galatians", "gal", "гал", "галатам", "к галатам")),
    ("ephesians", ("ephesians", "eph", "еф", "ефесянам", "к ефесянам")),
    ("philippians", ("philippians", "phil", "флп", "фил", "филиппийцам", "к филиппийцам")),
    ("colossians", ("colossians", "col", "кол", "колоссянам", "к колоссянам")),
    (
        "1thessalonians",
        (
            "1thessalonians",
            "1 thessalonians",
            "1thess",
            "1 thess",
            "1 фессалоникийцам",
            "1 фес",
            "1фес",
            "1 фесс",
            "1фесс",
        ),
    ),
    (
        "2thessalonians",
        (
            "2thessalonians",
            "2 thessalonians",
            "2thess",
            "2 thess",
            "2 фессалоникийцам",
            "2 фес",
            "2фес",
            "2 фесс",
            "2фесс",
        ),
    ),
    ("1timothy", ("1timothy", "1 timothy", "1tim", "1 tim", "1 тимофею", "1 тим", "1тим")),
    ("2timothy", ("2timothy", "2 timothy", "2tim", "2 tim", "2 тимофею", "2 тим", "2тим")),
    ("titus", ("titus", "tit", "тит", "к титу")),
    ("philemon", ("philemon", "phlm", "флм", "к филимону")),
    ("hebrews", ("hebrews", "heb", "евр", "евреям", "к евреям")),
    ("james", ("james", "jas", "иак", "иакова")),
    ("1peter", ("1peter", "1 peter", "1pet", "1 pet", "i peter", "1 петра", "1 пет", "1пет")),
    ("2peter", ("2peter", "2 peter", "2pet", "2 pet", "ii peter", "2 петра", "2 пет", "2пет")),
    ("1john", ("1john", "1 john", "1jn", "1 jn", "i john", "1 иоанна", "1 ин", "1ин", "1 иоан", "1иоан")),
    ("2john", ("2john", "2 john", "2jn", "2 jn", "ii john", "2 иоанна", "2 ин", "2ин", "2 иоан", "2иоан")),
    ("3john", ("3john", "3 john", "3jn", "3 jn", "iii john", "3 иоанна", "3 ин", "3ин", "3 иоан", "3иоан")),
    ("jude", ("jude", "иуд", "иуды", "послание иуды")),
    ("revelation", ("revelation", "rev", "откр", "откровение", "откровение иоанна")),
)


# A numbered book is printed four different ways in four languages —
# ``1 Samuel``, ``1. Mose``, ``1Цар``, ``1-е Коринтян`` — and they are
# the same name. Folding the ordinal marker here means the index holds
# one key per book rather than one per typographic habit.
_LEADING_ORDINAL = re.compile(r"^([1-5])\s*[.\-]?\s*(?:ше|ге|тє|е)?\s*")

# Ukrainian writes an apostrophe inside ``Об'явлення`` and ``Филип'ян``,
# and which apostrophe depends on the keyboard the author used.
_APOSTROPHES = str.maketrans({"’": "'", "ʼ": "'", "‘": "'", "`": "'"})


def _normalize(s: str) -> str:
    """Lower-case, strip dots/whitespace, collapse internal runs of
    whitespace to a single space, fold the apostrophe variants, and
    reduce a leading book number to ``"1 "``. Keeps Cyrillic vs Latin
    distinct intentionally — ё/е normalization is handled by the alias
    list when we add the variant explicitly.

    Whatever this does, ``references.py`` has to undo when it builds its
    regex out of the same keys — the two are a pair, and
    ``test_the_platform_reads_the_references_it_writes`` walks every
    alias through both to prove they still agree.
    """
    s = s.strip().lower().rstrip(".")
    s = " ".join(s.split())
    s = s.translate(_APOSTROPHES)
    return _LEADING_ORDINAL.sub(r"\1 ", s)


# Short aliases that are also ordinary words, and what saves them.
#
# The alias table is a list of strings the parser will believe when it
# finds one in front of two numbers, and some of those strings are
# words. Before this file grew German and Ukrainian, "The ratio is 1:2"
# already parsed as Isaiah 1:2 — ``is`` is a declared alias for Isaiah.
# Widening the table to four languages multiplies the hazard: German
# ``am`` (Amos) sits in every second sentence, ``Mi`` (Micha) is also
# Mittwoch, and Ukrainian ``об`` (Об'явлення) is how a Ukrainian says
# "at" before a time — "об 11:30" is half past eleven, not Revelation.
#
# The rule: a printed citation capitalises the book name, always, in all
# four languages, and prose does not capitalise a preposition mid
# sentence. So an alias that is also a word is read as a book only when
# it is written as one. For the ordinary-word cases the capital alone is
# not enough — "Am 10:30" and "Mi 10:30" are both perfectly ordinary
# German — so those additionally have to carry the dot that their
# printed form carries anyway (``Am. 5,24``, ``Mi. 6,8``).
#
# This costs us nothing on a real citation and it is deliberately not
# applied to every alias: ``acts 1:8`` in lower case is somebody's
# sloppy typing, not an ambiguity, and it has always parsed.
_WORDS_NEEDING_A_CAPITAL = frozenset(
    {
        "job",  # English "job"
        "song",  # English "song"
        "дії",  # Ukrainian "дії" — "actions"
    }
)
_WORDS_NEEDING_THE_PRINTED_DOT = frozenset(
    {
        "is",  # English "is" — "The ratio is 1:2" was parsing as Isaiah
        "am",  # German "am" — "am 10:30 Uhr"
        "mi",  # German "Mi" — Mittwoch
        "nah",  # German "nah" — "near"
        "hab",  # German "hab" — "ich hab"
        "об",  # Ukrainian "об" — "об 11:30"
        "як",  # Ukrainian "як" — "how", "as"
    }
)


def written_as_a_book_name(raw: str) -> bool:
    """Whether ``raw`` — exactly as it stood in the running text, dot and
    all — may be read as a book name at all.

    Only the aliases that are also ordinary words can answer ``False``;
    see the note above them. Callers that already know they hold a book
    name (the Daily Challenge stores one in a column) want ``find_book``
    and not this.
    """
    key = _normalize(raw)
    if key not in _WORDS_NEEDING_A_CAPITAL and key not in _WORDS_NEEDING_THE_PRINTED_DOT:
        return True
    stripped = raw.strip()
    first_letter = next((ch for ch in stripped if ch.isalpha()), "")
    if not first_letter.isupper():
        return False
    return key not in _WORDS_NEEDING_THE_PRINTED_DOT or stripped.endswith(".")


def find_book(name: str, locale: str | None = None) -> str | None:
    """Return the canonical book slug for a printed book name / abbreviation,
    or ``None`` if no match. Tolerant of trailing dots, whitespace, and
    case. Returns the project's canonical lowercase slug (``acts``,
    ``1corinthians``).

    ``locale`` settles the one abbreviation the languages genuinely
    disagree about. Synodal Russian numbers Samuel and Kings straight
    through — ``1 Цар.`` is 1 Samuel and Kings begins at ``3 Цар.`` —
    while Ukrainian numbers them the way English does, so ``1 Цар.`` is
    1 Kings. The same eight characters, two different books. Without a
    locale the Russian reading wins, because Russian is what the whole
    live catalogue is written in; a caller that knows the language of
    the text it is reading should say so. ``_LOCALE_OVERRIDES`` holds
    every such disagreement and is asserted whole in the tests, so a
    future alias cannot quietly steal a book from another language.
    """
    if not name:
        return None
    key = _normalize(name)
    if locale is not None:
        override = _LOCALE_OVERRIDES.get(locale)
        if override is not None and key in override:
            return override[key]
    return _ALIAS_INDEX.get(key)


def find_book_written_in(name: str, locale: str) -> str | None:
    """The slug ``name`` names — but only when ``locale`` itself prints
    that spelling.

    The narrow half of ``find_book``. ``find_book("Rev.")`` is Revelation
    because some language calls it that; ``find_book_written_in("Rev.",
    "de")`` is ``None`` because German calls it ``Offb.`` and a German
    reader meets ``Rev.`` as an abbreviation for *Revision*. A caller
    rewriting text in one language wants this one: a name it cannot
    match here is a name the language would not have printed, which is
    the same thing as saying it is probably not a book at all.
    """
    if not name:
        return None
    return _NATIVE_INDEX.get(locale, {}).get(_normalize(name))


def all_canonical_slugs() -> tuple[str, ...]:
    """Test-time helper: every canonical book slug in canon order."""
    return tuple(slug for slug, _ in _BOOKS)


def all_aliases() -> tuple[str, ...]:
    """Every normalized alias the lookup knows, longest first.

    ``references.py`` builds its regex from exactly this, so a name that
    can be looked up is a name that can be found in running text — the
    single source of truth the original module comment promised.
    """
    keys = set(_ALIAS_INDEX)
    for override in _LOCALE_OVERRIDES.values():
        keys.update(override)
    return tuple(sorted(keys, key=lambda a: (-len(a), a)))


# Display abbreviation per locale — what we render in a localized
# reference like ``(Матф. 28:19)`` / ``(Matt. 28:19)``. Pinned to the
# conventional short form of the edition each language reads: Synodal
# for ``ru``, KJV for ``en``, Luther for ``de``, Kulish for ``uk``.
# Not for parsing — that's what the alias list above is for.
#
# Every served locale must appear here with all 66 books. A missing
# entry does not fail loudly: ``display_book_name`` returns ``None`` and
# the caller keeps the English name, so a German reader is quietly shown
# "(Rom. 8:1)" in the middle of German prose. ``test_every_language_
# names_the_books`` is what makes that a failing test instead.
_DISPLAY_NAMES: dict[str, dict[str, str]] = {
    "ru": {
        "genesis": "Быт.",
        "exodus": "Исх.",
        "leviticus": "Лев.",
        "numbers": "Чис.",
        "deuteronomy": "Втор.",
        "joshua": "Нав.",
        "judges": "Суд.",
        "ruth": "Руф.",
        "1samuel": "1 Цар.",
        "2samuel": "2 Цар.",
        "1kings": "3 Цар.",
        "2kings": "4 Цар.",
        "1chronicles": "1 Пар.",
        "2chronicles": "2 Пар.",
        "ezra": "Езд.",
        "nehemiah": "Неем.",
        "esther": "Есф.",
        "job": "Иов",
        "psalms": "Пс.",
        "proverbs": "Притч.",
        "ecclesiastes": "Еккл.",
        "songofsolomon": "Песн.",
        "isaiah": "Ис.",
        "jeremiah": "Иер.",
        "lamentations": "Плач",
        "ezekiel": "Иез.",
        "daniel": "Дан.",
        "hosea": "Ос.",
        "joel": "Иоил.",
        "amos": "Ам.",
        "obadiah": "Авд.",
        "jonah": "Ион.",
        "micah": "Мих.",
        "nahum": "Наум",
        "habakkuk": "Авв.",
        "zephaniah": "Соф.",
        "haggai": "Агг.",
        "zechariah": "Зах.",
        "malachi": "Мал.",
        "matthew": "Матф.",
        "mark": "Мк.",
        "luke": "Лк.",
        "john": "Ин.",
        "acts": "Деян.",
        "romans": "Рим.",
        "1corinthians": "1 Кор.",
        "2corinthians": "2 Кор.",
        "galatians": "Гал.",
        "ephesians": "Еф.",
        "philippians": "Флп.",
        "colossians": "Кол.",
        "1thessalonians": "1 Фес.",
        "2thessalonians": "2 Фес.",
        "1timothy": "1 Тим.",
        "2timothy": "2 Тим.",
        "titus": "Тит.",
        "philemon": "Флм.",
        "hebrews": "Евр.",
        "james": "Иак.",
        "1peter": "1 Пет.",
        "2peter": "2 Пет.",
        "1john": "1 Ин.",
        "2john": "2 Ин.",
        "3john": "3 Ин.",
        "jude": "Иуд.",
        "revelation": "Откр.",
    },
    "de": {
        # Luther naming, which is what the German edition the platform
        # quotes from (Luther 1912) prints on its own pages: the
        # Pentateuch is numbered Moses, not Genesis-Deuteronomy.
        "genesis": "1. Mose",
        "exodus": "2. Mose",
        "leviticus": "3. Mose",
        "numbers": "4. Mose",
        "deuteronomy": "5. Mose",
        "joshua": "Jos.",
        "judges": "Ri.",
        "ruth": "Rut",
        "1samuel": "1. Sam.",
        "2samuel": "2. Sam.",
        "1kings": "1. Kön.",
        "2kings": "2. Kön.",
        "1chronicles": "1. Chr.",
        "2chronicles": "2. Chr.",
        "ezra": "Esra",
        "nehemiah": "Neh.",
        "esther": "Est.",
        "job": "Hiob",
        "psalms": "Ps.",
        "proverbs": "Spr.",
        "ecclesiastes": "Pred.",
        "songofsolomon": "Hld.",
        "isaiah": "Jes.",
        "jeremiah": "Jer.",
        "lamentations": "Klgl.",
        "ezekiel": "Hes.",
        "daniel": "Dan.",
        "hosea": "Hos.",
        "joel": "Joel",
        "amos": "Amos",
        "obadiah": "Obd.",
        "jonah": "Jona",
        "micah": "Mi.",
        "nahum": "Nah.",
        "habakkuk": "Hab.",
        "zephaniah": "Zeph.",
        "haggai": "Hag.",
        "zechariah": "Sach.",
        "malachi": "Mal.",
        "matthew": "Mt.",
        "mark": "Mk.",
        "luke": "Lk.",
        "john": "Joh.",
        "acts": "Apg.",
        "romans": "Röm.",
        "1corinthians": "1. Kor.",
        "2corinthians": "2. Kor.",
        "galatians": "Gal.",
        "ephesians": "Eph.",
        "philippians": "Phil.",
        "colossians": "Kol.",
        "1thessalonians": "1. Thess.",
        "2thessalonians": "2. Thess.",
        "1timothy": "1. Tim.",
        "2timothy": "2. Tim.",
        "titus": "Tit.",
        "philemon": "Phlm.",
        "hebrews": "Hebr.",
        "james": "Jak.",
        "1peter": "1. Petr.",
        "2peter": "2. Petr.",
        "1john": "1. Joh.",
        "2john": "2. Joh.",
        "3john": "3. Joh.",
        "jude": "Jud.",
        "revelation": "Offb.",
    },
    "uk": {
        # Conventional Ukrainian short forms. Note ``Ів.`` for John
        # against Russian ``Ин.`` — the two look close enough to copy
        # by accident and are not the same word.
        "genesis": "Бут.",
        "exodus": "Вих.",
        "leviticus": "Лев.",
        "numbers": "Чис.",
        "deuteronomy": "Повт.",
        "joshua": "Нав.",
        "judges": "Суд.",
        "ruth": "Рут",
        "1samuel": "1 Сам.",
        "2samuel": "2 Сам.",
        "1kings": "1 Цар.",
        "2kings": "2 Цар.",
        "1chronicles": "1 Хр.",
        "2chronicles": "2 Хр.",
        "ezra": "Езд.",
        "nehemiah": "Неєм.",
        "esther": "Ест.",
        "job": "Йов",
        "psalms": "Пс.",
        "proverbs": "Прип.",
        "ecclesiastes": "Екл.",
        "songofsolomon": "Пісн.",
        "isaiah": "Іс.",
        "jeremiah": "Єр.",
        "lamentations": "Плач",
        "ezekiel": "Єз.",
        "daniel": "Дан.",
        "hosea": "Ос.",
        "joel": "Йоіл",
        "amos": "Ам.",
        "obadiah": "Авд.",
        "jonah": "Йона",
        "micah": "Мих.",
        "nahum": "Наум",
        "habakkuk": "Авв.",
        "zephaniah": "Соф.",
        "haggai": "Ог.",
        "zechariah": "Зах.",
        "malachi": "Мал.",
        "matthew": "Мт.",
        "mark": "Мк.",
        "luke": "Лк.",
        "john": "Ів.",
        "acts": "Дії",
        "romans": "Рим.",
        "1corinthians": "1 Кор.",
        "2corinthians": "2 Кор.",
        "galatians": "Гал.",
        "ephesians": "Еф.",
        "philippians": "Флп.",
        "colossians": "Кол.",
        "1thessalonians": "1 Сол.",
        "2thessalonians": "2 Сол.",
        "1timothy": "1 Тим.",
        "2timothy": "2 Тим.",
        "titus": "Тит",
        "philemon": "Флм.",
        "hebrews": "Євр.",
        "james": "Як.",
        "1peter": "1 Пет.",
        "2peter": "2 Пет.",
        "1john": "1 Ів.",
        "2john": "2 Ів.",
        "3john": "3 Ів.",
        "jude": "Юда",
        "revelation": "Об.",
    },
    "en": {
        "genesis": "Gen.",
        "exodus": "Ex.",
        "leviticus": "Lev.",
        "numbers": "Num.",
        "deuteronomy": "Deut.",
        "joshua": "Josh.",
        "judges": "Judg.",
        "ruth": "Ruth",
        "1samuel": "1 Sam.",
        "2samuel": "2 Sam.",
        "1kings": "1 Kgs.",
        "2kings": "2 Kgs.",
        "1chronicles": "1 Chr.",
        "2chronicles": "2 Chr.",
        "ezra": "Ezra",
        "nehemiah": "Neh.",
        "esther": "Esth.",
        "job": "Job",
        "psalms": "Ps.",
        "proverbs": "Prov.",
        "ecclesiastes": "Eccl.",
        "songofsolomon": "Song",
        "isaiah": "Isa.",
        "jeremiah": "Jer.",
        "lamentations": "Lam.",
        "ezekiel": "Ezek.",
        "daniel": "Dan.",
        "hosea": "Hos.",
        "joel": "Joel",
        "amos": "Amos",
        "obadiah": "Obad.",
        "jonah": "Jonah",
        "micah": "Mic.",
        "nahum": "Nah.",
        "habakkuk": "Hab.",
        "zephaniah": "Zeph.",
        "haggai": "Hag.",
        "zechariah": "Zech.",
        "malachi": "Mal.",
        "matthew": "Matt.",
        "mark": "Mark",
        "luke": "Luke",
        "john": "John",
        "acts": "Acts",
        "romans": "Rom.",
        "1corinthians": "1 Cor.",
        "2corinthians": "2 Cor.",
        "galatians": "Gal.",
        "ephesians": "Eph.",
        "philippians": "Phil.",
        "colossians": "Col.",
        "1thessalonians": "1 Thess.",
        "2thessalonians": "2 Thess.",
        "1timothy": "1 Tim.",
        "2timothy": "2 Tim.",
        "titus": "Titus",
        "philemon": "Phlm.",
        "hebrews": "Heb.",
        "james": "Jas.",
        "1peter": "1 Pet.",
        "2peter": "2 Pet.",
        "1john": "1 Jn.",
        "2john": "2 Jn.",
        "3john": "3 Jn.",
        "jude": "Jude",
        "revelation": "Rev.",
    },
}


def display_book_name(slug: str, locale: str) -> str | None:
    """Return the locale's conventional short form for a canonical
    book slug (``Матф.`` for ru, ``Matt.`` for en), or ``None`` if the
    slug is unknown / locale not bundled. Used to localize the reference
    notation that sits next to a canonical-quoted blockquote, so a
    Russian student sees ``(Матф. 28:19)`` instead of the source's
    ``(Matt. 28:19)``."""
    return _DISPLAY_NAMES.get(locale, {}).get(slug)


# What a display table cannot hold: the full name, and the second
# spelling. ``_DISPLAY_NAMES`` carries one abbreviation per book because
# that is what we print, but an author writes "Apostelgeschichte 1,8" as
# readily as "Apg. 1,8", and Ukrainian genitive endings vary by edition
# ("Матвія" in Kulish, "Від Матвія" as a heading). Everything derivable
# from the display table is left out of this one on purpose — the two
# are merged below, and duplicating a row here would only create a place
# for the two to drift apart.
_LOCALE_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "de": {
        "genesis": ("Genesis",),
        "exodus": ("Exodus",),
        "leviticus": ("Levitikus",),
        "numbers": ("Numeri",),
        "deuteronomy": ("Deuteronomium",),
        "joshua": ("Josua",),
        "judges": ("Richter",),
        "ruth": ("Ruth",),
        "1samuel": ("1. Samuel",),
        "2samuel": ("2. Samuel",),
        "1kings": ("1. Könige",),
        "2kings": ("2. Könige",),
        "1chronicles": ("1. Chronik",),
        "2chronicles": ("2. Chronik",),
        "ezra": ("Esr.",),
        "nehemiah": ("Nehemia",),
        "esther": ("Ester",),
        "job": ("Ijob",),
        "psalms": ("Psalm", "Psalmen"),
        "proverbs": ("Sprüche", "Sprichwörter"),
        "ecclesiastes": ("Prediger", "Kohelet"),
        "songofsolomon": ("Hoheslied", "Hohelied", "Hohes Lied"),
        "isaiah": ("Jesaja",),
        "jeremiah": ("Jeremia",),
        "lamentations": ("Klagelieder",),
        "ezekiel": ("Hesekiel", "Ezechiel"),
        "hosea": ("Hos.",),
        "amos": ("Am.",),
        "obadiah": ("Obadja",),
        "micah": ("Micha",),
        "habakkuk": ("Habakuk",),
        "zephaniah": ("Zefanja", "Zephanja"),
        "zechariah": ("Sacharja",),
        "malachi": ("Maleachi",),
        "matthew": ("Matthäus",),
        "mark": ("Markus",),
        "luke": ("Lukas",),
        "john": ("Johannes",),
        "acts": ("Apostelgeschichte",),
        "romans": ("Römer",),
        "1corinthians": ("1. Korinther",),
        "2corinthians": ("2. Korinther",),
        "galatians": ("Galater",),
        "ephesians": ("Epheser",),
        "philippians": ("Philipper",),
        "colossians": ("Kolosser",),
        "1thessalonians": ("1. Thessalonicher",),
        "2thessalonians": ("2. Thessalonicher",),
        "1timothy": ("1. Timotheus",),
        "2timothy": ("2. Timotheus",),
        "philemon": ("Phlm.",),
        "hebrews": ("Hebräer",),
        "james": ("Jakobus",),
        "1peter": ("1. Petrus",),
        "2peter": ("2. Petrus",),
        "1john": ("1. Johannes",),
        "2john": ("2. Johannes",),
        "3john": ("3. Johannes",),
        "jude": ("Judas",),
        "revelation": ("Offenbarung",),
    },
    "uk": {
        "genesis": ("Буття",),
        "exodus": ("Вихід",),
        "leviticus": ("Левит",),
        "numbers": ("Числа",),
        "deuteronomy": ("Повторення Закону",),
        "joshua": ("Ісус Навин", "Навин"),
        "judges": ("Судді",),
        "1samuel": ("1 Самуїлова", "1 Самуїла"),
        "2samuel": ("2 Самуїлова", "2 Самуїла"),
        "1kings": ("1 Царів",),
        "2kings": ("2 Царів",),
        "1chronicles": ("1 Хроніки", "1 Хронік"),
        "2chronicles": ("2 Хроніки", "2 Хронік"),
        "ezra": ("Ездра",),
        "nehemiah": ("Неемія",),
        "esther": ("Естер",),
        "job": ("Йова",),
        "psalms": ("Псалми", "Псалом"),
        "proverbs": ("Приповісті", "Приповідки"),
        "ecclesiastes": ("Екклезіяст", "Еклезіаст"),
        "songofsolomon": ("Пісня над піснями",),
        "isaiah": ("Ісая", "Ісаї"),
        "jeremiah": ("Єремія", "Єремії"),
        "lamentations": ("Плач Єремії",),
        "ezekiel": ("Єзекіїль", "Єзекіїля"),
        "daniel": ("Даниїл", "Даниїла"),
        "hosea": ("Осія", "Осії"),
        "joel": ("Йоіла", "Йоїл"),
        "amos": ("Амос", "Амоса"),
        "obadiah": ("Авдій",),
        "jonah": ("Йони",),
        "micah": ("Михей", "Михея"),
        "habakkuk": ("Авакум",),
        "zephaniah": ("Софонія",),
        "haggai": ("Огій",),
        "zechariah": ("Захарія",),
        "malachi": ("Малахія",),
        "matthew": ("Матвія", "Від Матвія"),
        "mark": ("Марка", "Від Марка"),
        "luke": ("Луки", "Від Луки"),
        "john": ("Івана", "Від Івана"),
        "acts": ("Дії апостолів", "Діяння"),
        "romans": ("Римлян", "До римлян"),
        "1corinthians": ("1 Коринтян",),
        "2corinthians": ("2 Коринтян",),
        "galatians": ("Галатів",),
        "ephesians": ("Ефесян",),
        "philippians": ("Филип'ян",),
        "colossians": ("Колосян",),
        "1thessalonians": ("1 Солунян",),
        "2thessalonians": ("2 Солунян",),
        "1timothy": ("1 Тимофія",),
        "2timothy": ("2 Тимофія",),
        "titus": ("Тита",),
        "philemon": ("Филимона",),
        "hebrews": ("Євреїв",),
        "james": ("Якова",),
        "1peter": ("1 Петра",),
        "2peter": ("2 Петра",),
        "1john": ("1 Івана",),
        "2john": ("2 Івана",),
        "3john": ("3 Івана",),
        "jude": ("Юди",),
        "revelation": ("Об'явлення", "Одкровення"),
    },
}

# Registration order is precedence order, and it is the order the
# catalogue is written in: Russian and English first (every live course
# and the bundled Bibles), then the two languages added in 08.2026.
# Where a later language claims an alias an earlier one already holds,
# the earlier one keeps the shared index and the later one gets a
# locale-scoped entry — see ``find_book``.
_ALIAS_PRECEDENCE: tuple[str, ...] = ("ru", "en", "de", "uk")

# alias → slug, for a caller that does not know what language it is
# reading. A few hundred entries of pure Python, built at import.
_ALIAS_INDEX: dict[str, str] = {}
# locale → alias → slug, and only for the aliases where that locale
# disagrees with ``_ALIAS_INDEX``. Empty for a language that invented no
# collision, which is all of them but Ukrainian.
_LOCALE_OVERRIDES: dict[str, dict[str, str]] = {}
# locale → alias → slug, holding only the spellings *that* language
# actually prints.
#
# ``_ALIAS_INDEX`` is promiscuous on purpose: it reads a book name in any
# of the four languages, which is what lets a Russian ``Ин.`` be
# recognised inside a German page and translated. But a caller that is
# *editing* German prose needs the narrower question — is this string a
# spelling German itself uses? ``Rev.`` and ``Ex.`` are in the shared
# table and are not German at all; in German prose they read as
# *Revision* and *Exemplar*, and answering the wide question about them
# is how ``Zeichnung Rev. 3:2`` came back as ``Zeichnung Offb. 3,2``.
_NATIVE_INDEX: dict[str, dict[str, str]] = {}


def _register(alias: str, slug: str, locale: str | None = None) -> None:
    key = _normalize(alias)
    held_by = _ALIAS_INDEX.get(key)
    if held_by is None:
        _ALIAS_INDEX[key] = slug
    elif held_by != slug:
        if locale is None:
            # Two entries of the shared RU/EN table fighting over one
            # key is a typo, not a language difference. Fail at import
            # rather than resolve it by declaration order.
            raise ValueError(f"alias {key!r} maps to both {held_by} and {slug}")
        _LOCALE_OVERRIDES.setdefault(locale, {})[key] = slug


for _slug, _aliases in _BOOKS:
    for _alias in _aliases:
        _register(_alias, _slug)
    # The slug itself is always a valid alias.
    _register(_slug, _slug)

for _locale in _ALIAS_PRECEDENCE:
    _native = _NATIVE_INDEX.setdefault(_locale, {})
    for _slug, _display in _DISPLAY_NAMES.get(_locale, {}).items():
        _register(_display, _slug, _locale)
        _native[_normalize(_display)] = _slug
    for _slug, _extra in _LOCALE_ALIASES.get(_locale, {}).items():
        for _alias in _extra:
            _register(_alias, _slug, _locale)
            _native[_normalize(_alias)] = _slug


__all__ = [
    "all_aliases",
    "all_canonical_slugs",
    "display_book_name",
    "find_book",
    "find_book_written_in",
    "written_as_a_book_name",
]
