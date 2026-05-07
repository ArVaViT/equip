"""Canonical 66-book Bible map + RU/EN alias lookup.

Each canonical slug (lower-case, no spaces — e.g. ``acts``,
``1corinthians``) maps to a set of aliases used in Russian and English
print abbreviations. ``find_book`` is a fast normalize-and-lookup that
returns the canonical slug for any reasonable spelling, or ``None``.

Aliases are conservative: only forms commonly used in printed
references (Деян. / Деяния / Acts / Acts.) are accepted. Extending this
map is a one-line change per new alias — keep additions tested.
"""

from __future__ import annotations

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
    ("numbers", ("numbers", "num", "nm", "числа", "чис")),
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
    ("matthew", ("matthew", "matt", "mt", "матфей", "мф", "от матфея")),
    ("mark", ("mark", "mk", "марк", "мк", "от марка")),
    ("luke", ("luke", "lk", "лука", "лк", "от луки")),
    ("john", ("john", "jn", "иоанн", "ин", "от иоанна")),
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
    ("philippians", ("philippians", "phil", "флп", "филиппийцам", "к филиппийцам")),
    ("colossians", ("colossians", "col", "кол", "колоссянам", "к колоссянам")),
    (
        "1thessalonians",
        ("1thessalonians", "1 thessalonians", "1thess", "1 thess", "1 фессалоникийцам", "1 фес", "1фес"),
    ),
    (
        "2thessalonians",
        ("2thessalonians", "2 thessalonians", "2thess", "2 thess", "2 фессалоникийцам", "2 фес", "2фес"),
    ),
    ("1timothy", ("1timothy", "1 timothy", "1tim", "1 tim", "1 тимофею", "1 тим", "1тим")),
    ("2timothy", ("2timothy", "2 timothy", "2tim", "2 tim", "2 тимофею", "2 тим", "2тим")),
    ("titus", ("titus", "tit", "тит", "к титу")),
    ("philemon", ("philemon", "phlm", "флм", "к филимону")),
    ("hebrews", ("hebrews", "heb", "евр", "евреям", "к евреям")),
    ("james", ("james", "jas", "иак", "иакова")),
    ("1peter", ("1peter", "1 peter", "1pet", "1 pet", "i peter", "1 петра", "1 пет", "1пет")),
    ("2peter", ("2peter", "2 peter", "2pet", "2 pet", "ii peter", "2 петра", "2 пет", "2пет")),
    ("1john", ("1john", "1 john", "1jn", "1 jn", "i john", "1 иоанна", "1 ин", "1ин")),
    ("2john", ("2john", "2 john", "2jn", "2 jn", "ii john", "2 иоанна", "2 ин", "2ин")),
    ("3john", ("3john", "3 john", "3jn", "3 jn", "iii john", "3 иоанна", "3 ин", "3ин")),
    ("jude", ("jude", "иуд", "иуды", "послание иуды")),
    ("revelation", ("revelation", "rev", "откр", "откровение", "откровение иоанна")),
)


def _normalize(s: str) -> str:
    """Lower-case, strip dots/whitespace, collapse internal runs of
    whitespace to a single space. Keeps Cyrillic vs Latin distinct
    intentionally — ё/е normalization is handled by the alias list
    when we add the variant explicitly."""
    s = s.strip().lower().rstrip(".")
    return " ".join(s.split())


# Build the alias → slug index at import time. This is a small pure-Python
# dict (a few hundred entries) so import cost is negligible.
_ALIAS_INDEX: dict[str, str] = {}
for slug, aliases in _BOOKS:
    for alias in aliases:
        _ALIAS_INDEX[_normalize(alias)] = slug
    # The slug itself is always a valid alias.
    _ALIAS_INDEX[slug] = slug


def find_book(name: str) -> str | None:
    """Return the canonical book slug for a printed book name / abbreviation,
    or ``None`` if no match. Tolerant of trailing dots, whitespace, and
    case. Returns the project's canonical lowercase slug (``acts``,
    ``1corinthians``)."""
    if not name:
        return None
    return _ALIAS_INDEX.get(_normalize(name))


def all_canonical_slugs() -> tuple[str, ...]:
    """Test-time helper: every canonical book slug in canon order."""
    return tuple(slug for slug, _ in _BOOKS)


__all__ = ["all_canonical_slugs", "find_book"]
