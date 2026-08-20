# ruff: noqa: RUF001, RUF002, RUF003
# Half of this file is the printed forms themselves — Cyrillic and
# Latin book names that look alike on purpose, because telling them
# apart is what the code under test does.
"""The platform could write a German reference and not read one back.

``books._DISPLAY_NAMES`` has known how to print ``Apg. 1,8``, ``1. Mose
1,1`` and ``Дії 1:8`` since the four-language rollout. ``find_book``
knew Russian and English, and ``references.py`` accepted ``:`` and ``.``
as the chapter/verse separator but not the comma German prints. So for a
course authored in German or Ukrainian, ``parse_references`` returned
nothing, ``pre_substitute`` never fired, no ``EQV`` marker was ever
created, and every quoted verse went to the model as ordinary prose to
be re-worded — the failure the whole substitution layer exists to
prevent (#990), silently switched off for three quarters of the
languages served.

Nothing broke, because all four live courses are ``source_locale='ru'``.
The next German course would have shipped with machine-paraphrased
Scripture in it and nothing would have said so.

Measured before the fix:

    'Acts 1:8'              -> ['acts 1:8']
    'Деян. 1:8'             -> ['acts 1:8']
    'Johannes 3,16'         -> []
    'Apg. 1:8'              -> []
    'Apostelgeschichte 1,8' -> []
    '1. Mose 1:1'           -> []
    'Дії 1:8'               -> []
    'Матвія 5:9'            -> []

The asymmetry is what these tests close: what the platform writes, it
reads back — for every book, in every language, checked by walking the
tables rather than by sampling them.
"""

from __future__ import annotations

import pytest

from app.schemas.locale import LOCALE_CODES
from app.services.bible import substitution as sub
from app.services.bible.books import (
    _LOCALE_OVERRIDES,
    all_aliases,
    all_canonical_slugs,
    display_book_name,
    find_book,
    find_book_written_in,
)
from app.services.bible.references import parse_references
from app.services.bible.substitution import post_substitute, pre_substitute

# John 3:16 in the wording a German author copies out of a Luther Bible,
# and in the wording the platform's own German edition (Elberfelder,
# ``api_source.API_BIBLE_IDS``) serves. Two real editions, four
# centuries apart, similarity 0.85 — comfortably over the 0.80 bar and
# nowhere near identical, which is the point: the author is recognised
# as quoting Scripture, not as having copied our file.
JOHN_3_16_LUTHER = (
    "Also hat Gott die Welt geliebt, daß er seinen eingeborenen Sohn gab, "
    "auf daß alle, die an ihn glauben, nicht verloren werden, sondern das "
    "ewige Leben haben."
)
JOHN_3_16_ELBERFELDER = (
    "Denn so hat Gott die Welt geliebt, dass er seinen eingeborenen Sohn gab, "
    "damit jeder, der an ihn glaubt, nicht verloren geht, sondern ewiges "
    "Leben hat."
)


def _first(text: str, locale: str | None = None) -> str | None:
    """The canonical form of the first reference in ``text``, or None."""
    parsed = parse_references(text, locale)
    return str(parsed[0].ref) if parsed else None


def _printed(alias: str) -> str:
    """An alias as a citation prints it: capitalised, and carrying the
    dot an abbreviation carries. Both are what the ordinary-word guard
    in ``books.py`` asks for, and both are what a real citation has."""
    for index, char in enumerate(alias):
        if char.isalpha():
            return alias[:index] + char.upper() + alias[index + 1 :] + "."
    return alias + "."


class TestEveryLanguageReadsItsOwnCitation:
    @pytest.mark.parametrize(
        "citation",
        [
            "Деян. 1:8",  # ru
            "Acts 1:8",  # en
            "Apg. 1,8",  # de
            "Дії 1:8",  # uk
            "Деяния Апостолов 1:8",
            "Apostelgeschichte 1,8",
            "Дії апостолів 1:8",
        ],
    )
    def test_four_languages_name_one_verse(self, citation: str) -> None:
        assert _first(citation) == "acts 1:8"

    @pytest.mark.parametrize(
        ("citation", "expected"),
        [
            ("Johannes 3,16", "john 3:16"),
            ("Joh. 3,16", "john 3:16"),
            ("Матвія 5:9", "matthew 5:9"),
            ("Від Матвія 5:9", "matthew 5:9"),
            ("Об'явлення 21:4", "revelation 21:4"),
            ("Об’явлення 21:4", "revelation 21:4"),  # the other apostrophe
            ("Offenbarung 21,4", "revelation 21:4"),
            ("Псалми 23:1", "psalms 23:1"),
        ],
    )
    def test_a_book_the_parser_used_to_miss(self, citation: str, expected: str) -> None:
        assert _first(citation) == expected

    def test_the_german_comma_is_a_chapter_verse_separator(self) -> None:
        assert _first("Röm 8,28") == "romans 8:28"
        assert _first("1. Kor. 13,4-7") == "1corinthians 13:4-7"
        # And the two separators that already worked still work.
        assert _first("Romans 8:28") == "romans 8:28"
        assert _first("Romans 8.28") == "romans 8:28"

    def test_a_verse_list_is_read_as_its_first_verse(self) -> None:
        # ``Joh 3,16.18`` is verses 16 and 18, not a range. We look up
        # one passage, so 16 is the answer, and the rest of the citation
        # is left standing in the text rather than half-rewritten.
        parsed = parse_references("Joh 3,16.18")
        assert [str(p.ref) for p in parsed] == ["john 3:16"]
        assert parsed[0].raw_text == "Joh 3,16"

    @pytest.mark.parametrize(
        ("citation", "expected"),
        [
            ("1 Кор. 13:4", "1corinthians 13:4"),  # ru
            ("1-е Коринтян 13:4", "1corinthians 13:4"),  # uk
            ("1 Corinthians 13:4", "1corinthians 13:4"),  # en
            ("1. Kor. 13,4", "1corinthians 13:4"),  # de
            ("1. Mose 1,1", "genesis 1:1"),
            ("1 Mose 1,1", "genesis 1:1"),
            ("5. Mose 6,4", "deuteronomy 6:4"),
            ("2. Könige 2,11", "2kings 2:11"),
            ("1 Самуїлова 3:10", "1samuel 3:10"),
        ],
    )
    def test_a_numbered_book_in_each_language(self, citation: str, expected: str) -> None:
        # The number and the name are joined four different ways —
        # ``1 Samuel``, ``1. Mose``, ``1Кор.``, ``1-е Коринтян`` — and
        # they are one book.
        assert _first(citation) == expected


class TestWhatWeWriteWeCanRead:
    """The round trip, as a walk over the tables rather than examples.

    This is the invariant the defect broke: every abbreviation in
    ``_DISPLAY_NAMES`` is one we print next to a quoted verse, so every
    one of them has to come back through the parser as the same book.
    """

    @pytest.mark.parametrize("locale", LOCALE_CODES)
    def test_every_book_this_language_writes_parses_back(self, locale: str) -> None:
        unreadable = []
        for slug in all_canonical_slugs():
            display = display_book_name(slug, locale)
            assert display is not None, f"{locale} cannot write {slug}"
            parsed = parse_references(f"{display} 1:1", locale)
            if not parsed or parsed[0].ref.book != slug:
                unreadable.append((display, slug, [str(p.ref) for p in parsed]))
        assert not unreadable, f"{locale} writes references it cannot read: {unreadable}"

    @pytest.mark.parametrize("locale", LOCALE_CODES)
    def test_the_whole_span_of_the_citation_is_claimed(self, locale: str) -> None:
        # A citation half-matched is worse than one not matched: the
        # substitution would replace part of the printed reference.
        for slug in all_canonical_slugs():
            citation = f"{display_book_name(slug, locale)} 1:1"
            parsed = parse_references(citation, locale)
            assert parsed[0].span == (0, len(citation)), citation

    def test_every_alias_the_index_knows_is_found_in_running_text(self) -> None:
        # ``books._normalize`` folds a printed name into an index key and
        # ``references._alias_pattern`` unfolds it back into a regex.
        # They are a pair, and nothing else proves they still agree.
        missed = []
        for alias in all_aliases():
            citation = _printed(alias)
            parsed = parse_references(f"See {citation} 1:1 for this.")
            if not parsed or parsed[0].ref.book != find_book(alias):
                missed.append(alias)
        assert not missed, f"declared but unfindable: {missed}"


class TestAnOrdinaryWordIsNotABook:
    """Widening the alias table to four languages multiplies a hazard
    that was already live: ``is`` is a declared alias for Isaiah, and
    "The ratio is 1:2" parsed as Isaiah 1:2. German ``am`` and ``Mi``
    and Ukrainian ``об`` are the same shape of trap in three more
    languages."""

    @pytest.mark.parametrize(
        "prose",
        [
            "The ratio is 1:2 in favour of the second group.",
            "the meeting is 9:30 and the room is booked.",
            "Der Gottesdienst beginnt am 10:30 Uhr im großen Saal.",
            "Wir sehen uns am 3,15 — bring die Notizen mit.",
            "Die Bibelstunde ist Mi 10:30, wie immer.",
            "Ми зустрічаємось об 11:30 біля входу.",
            "Розкажи, як 1:2 стало результатом.",
            "I finished my job 1:1 with the brief.",
            "He hummed the song 1:2 out of tune.",
        ],
    )
    def test_prose_that_only_looks_like_a_citation(self, prose: str) -> None:
        assert parse_references(prose) == [], prose

    @pytest.mark.parametrize(
        ("citation", "expected"),
        [
            ("Is. 1:2", "isaiah 1:2"),
            ("Am. 5,24", "amos 5:24"),
            ("Mi. 6,8", "micah 6:8"),
            ("Об. 21:4", "revelation 21:4"),
            ("Як. 1:5", "james 1:5"),
            ("Job 1:1", "job 1:1"),
            ("Song 1:2", "songofsolomon 1:2"),
            ("Дії 1:8", "acts 1:8"),
        ],
    )
    def test_the_same_word_written_as_a_citation_still_reads(self, citation: str, expected: str) -> None:
        # The guard is about how the word is written, not about refusing
        # the book. Every one of these is the form its own language
        # prints — which is why the round-trip walk above passes.
        assert _first(citation) == expected

    def test_a_book_name_inside_a_longer_word_is_not_a_book_name(self) -> None:
        # "Facts 1:8" parsed as Acts 1:8 before the lookbehind: the
        # alternation was happy to start matching in the middle of a
        # word. Two-letter German aliases would have made every word
        # ending in "am" a citation.
        assert parse_references("Facts 1:8") == []
        assert parse_references("Der Traum 1,8 war lang.") == []


class TestTheOneAbbreviationTheLanguagesDisagreeAbout:
    """``1 Цар.`` is 1 Samuel in Synodal Russian, which numbers Samuel
    and Kings straight through to ``4 Цар.``, and 1 Kings in Ukrainian,
    which numbers them the way English does. Same eight characters, two
    books, and no amount of alias-table care makes that go away — only
    knowing the language of the text does."""

    def test_russian_reads_its_own_numbering(self) -> None:
        assert _first("1 Цар. 3:9", "ru") == "1samuel 3:9"
        assert _first("3 Цар. 3:9", "ru") == "1kings 3:9"

    def test_ukrainian_reads_its_own_numbering(self) -> None:
        assert _first("1 Цар. 3:9", "uk") == "1kings 3:9"
        assert _first("1 Царів 3:9") == "1kings 3:9"
        assert _first("1 Самуїлова 3:10", "uk") == "1samuel 3:10"

    def test_a_caller_that_names_no_language_gets_the_catalogue_language(self) -> None:
        # Every live course is Russian, so an unqualified read is a
        # Russian read.
        assert _first("1 Цар. 3:9") == "1samuel 3:9"

    def test_this_is_the_only_disagreement_there_is(self) -> None:
        # Asserted whole, not sampled: a future alias that collides with
        # another language's book has to be looked at by a person, not
        # discovered by a reader who followed a citation to the wrong
        # chapter.
        assert _LOCALE_OVERRIDES == {"uk": {"1 цар": "1kings", "2 цар": "2kings"}}


class TestOnlyTheSpellingsALanguagePrints:
    """``find_book`` is promiscuous on purpose — it reads a name in any
    of the four languages, which is what lets a Russian ``Ин.`` be
    recognised inside a German page. A caller *editing* German prose
    needs the narrower question, because the wide answer is what turned
    ``Zeichnung Rev. 3:2`` into ``Zeichnung Offb. 3,2``."""

    def test_german_reads_the_names_german_prints(self) -> None:
        assert find_book_written_in("Apg.", "de") == "acts"
        assert find_book_written_in("Apg", "de") == "acts"
        assert find_book_written_in("Apostelgeschichte", "de") == "acts"
        assert find_book_written_in("1. Korinther", "de") == "1corinthians"

    def test_but_not_an_english_abbreviation_that_is_a_german_word(self) -> None:
        # ``Rev.`` is *Revision* to a German reader and ``Ex.`` is an
        # *Exemplar*. Both are in the shared table; neither is German.
        assert find_book("Rev.") == "revelation"
        assert find_book_written_in("Rev.", "de") is None
        assert find_book("Ex.") == "exodus"
        assert find_book_written_in("Ex.", "de") is None

    def test_each_language_keeps_its_own_answer(self) -> None:
        assert find_book_written_in("Ин.", "ru") == "john"
        assert find_book_written_in("Ин.", "de") is None
        assert find_book_written_in("Joh.", "de") == "john"
        assert find_book_written_in("Joh.", "ru") is None

    def test_an_unknown_name_is_no_book_in_any_language(self) -> None:
        assert find_book_written_in("", "de") is None
        assert find_book_written_in("Nebenstelle", "de") is None
        assert find_book_written_in("Apg.", "xx") is None


class TestAGermanQuotationIsRecognised:
    """The point of all of the above. Parsing is the means; a German
    author's quoted verse surviving translation as Scripture rather than
    as paraphrase is the end."""

    @pytest.fixture(autouse=True)
    def _german_edition(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # German has no bundled file — the edition comes from the API.
        monkeypatch.setattr(
            sub,
            "fetch_verse",
            lambda ref, locale: JOHN_3_16_ELBERFELDER if locale == "de" else None,
        )

    def test_a_blockquote_citing_the_reference_inside_it(self) -> None:
        html = (
            "<p>Der Kern des Evangeliums:</p>"
            f"<blockquote>{JOHN_3_16_LUTHER} (Joh. 3,16)</blockquote>"
            "<p>Darum ist die Sendung des Sohnes keine Nebensache.</p>"
        )
        markered, subs = pre_substitute(html, "de")
        assert [str(s.ref) for s in subs] == ["john 3:16"], (
            "a German course's Scripture went to the model as prose to be re-worded"
        )
        assert JOHN_3_16_LUTHER not in markered
        assert subs[0].marker in markered

    def test_a_blockquote_citing_the_reference_after_it(self) -> None:
        html = f"<blockquote>{JOHN_3_16_LUTHER}</blockquote> (Apg. 1,8 vgl. Joh. 3,16)"
        _, subs = pre_substitute(html, "de")
        assert [str(s.ref) for s in subs] == ["acts 1:8"]

    def test_the_german_quote_comes_back_as_russian_scripture(self, monkeypatch: pytest.MonkeyPatch) -> None:
        html = f"<blockquote>{JOHN_3_16_LUTHER} (Joh. 3,16)</blockquote>"
        markered, subs = pre_substitute(html, "de")
        synodal = "Ибо так возлюбил Бог мир, что отдал Сына Своего Единородного."
        monkeypatch.setattr(sub, "fetch_verse", lambda ref, locale: synodal)
        rendered = post_substitute(markered, subs, "ru")
        assert synodal in rendered
        # And the citation beside it reads as Russian, not as German.
        assert "(Ин. 3:16)" in rendered

    def test_a_german_paraphrase_is_still_left_to_the_author(self) -> None:
        # The bar has not moved. Only the languages it applies to.
        html = "<blockquote>Gott liebt die Menschen und schickte seinen Sohn zu ihnen. (Joh. 3,16)</blockquote>"
        _, subs = pre_substitute(html, "de")
        assert subs == []
