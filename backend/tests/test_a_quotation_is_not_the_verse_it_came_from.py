# Russian and German prose fixtures quoted from production.
"""An author who quotes half a verse is not quoting the verse.

The defect
----------
Similarity alone cannot tell "these are the words of this verse" from
"these are the words of this verse and a clause before them". Both score
high; only one of them is safe to paste back whole. So a memory-verse
callout reading, in the Russian source,

    «Веруй в Господа Иисуса Христа, и спасёшься ты и весь дом твой»
    (Деян. 16:31)

reached the German reader on 2026-08-22 as

    „Sie aber sprachen: Glaube an den Herrn Jesus, und du wirst
    gerettet werden, du und dein Haus.“

— the narrator's line pulled inside the author's quotation marks. The
English column of the same lesson reads worse, because English opens and
closes with the same character and the Berean text of Acts 16:31 already
carries a pair of its own:

    "They replied, "Believe in the Lord Jesus and you will be saved, you
    and your household."

Editors reported four separate complaints against this one cause:
framing inside the marks, more quoted than the source quoted, a lead-in
stated and then repeated inside the quotation, and an editorial bracket
reaching a student — ``„Petrus aber [sprach] zu ihnen: Tut Buße…“``,
where the bracket is Elberfelder's and lives in the dragged-in head.

What is measured, and what is not
---------------------------------
The head. Over every quotation in the live sources on 2026-08-22, 163 of
232 have no head at all; under twelve characters the head is a
conjunction the author dropped (``И``, ``Итак``, ``And``, ``Now``,
``Между тем``) and from twelve up it is almost uniformly somebody
speaking. Fifty decline at that bar and 182 stand.

The *tail* is not measured, deliberately. A quotation that stops early is
still the opening of the verse the citation names, and a reader shown
the rest of that verse has been shown the cited verse. Nothing is
attributed to Scripture that Scripture does not say.
"""

from __future__ import annotations

from app.services.bible.references import BibleRef
from app.services.bible.substitution import (
    Substitution,
    _canonical_head,
    _requote,
    pre_substitute,
)

ACTS_16_31_KJV = "So they said, Believe on the Lord Jesus Christ, and thou shalt be saved, and thy house."


class TestTheHeadIsMeasured:
    def test_a_quotation_that_begins_where_the_verse_begins_has_no_head(self) -> None:
        author = "I am the way, the truth, and the life: no man cometh unto the Father, but by me."
        assert _canonical_head(author, author) == 0

    def test_a_narrators_line_in_front_of_the_verse_is_a_head(self) -> None:
        author = "I am the way, the truth, and the life: no man cometh unto the Father, but by me."
        canonical = f"Jesus saith unto him, {author}"
        assert _canonical_head(author, canonical) == len("Jesus saith unto him, ")

    def test_a_dropped_conjunction_is_not_a_head_worth_declining_over(self) -> None:
        author = "Рассеявшиеся ходили и благовествовали слово"
        canonical = "Между тем рассеявшиеся ходили и благовествовали слово."
        assert 0 < _canonical_head(author, canonical) <= 12

    def test_the_same_verse_in_another_edition_is_not_a_head(self) -> None:
        # The measurement finds where the words line up, and a rewording
        # moves that as surely as a skipped clause. These two openings
        # are the same sentence; only one of them is the KJV's.
        author = (
            "For God did not send his Son into the world to condemn the world, "
            "but in order that the world might be saved through him."
        )
        kjv = (
            "For God sent not his Son into the world to condemn the world; "
            "but that the world through him might be saved."
        )
        assert _canonical_head(author, kjv) == 0

    def test_a_quotation_too_short_to_place_is_not_measured(self) -> None:
        # Three words matched in the middle of a verse say nothing about
        # where the author started.
        assert _canonical_head("the Lord is good", "Oh taste and see that the Lord is good") == 0


class TestTheSubstitutionIsDeclined:
    def test_the_verse_a_narrator_introduces_keeps_the_authors_own_words(self) -> None:
        text = "Acts 16:31 says, 'Believe on the Lord Jesus Christ, and thou shalt be saved, and thy house.'"
        markered, subs = pre_substitute(text, "en")
        assert subs == []
        assert markered == text

    def test_the_whole_verse_quoted_whole_is_still_substituted(self) -> None:
        text = f"Acts 16:31 says, '{ACTS_16_31_KJV}'"
        _markered, subs = pre_substitute(text, "en")
        assert [sub.ref for sub in subs] == [BibleRef("acts", 16, 31)]

    def test_a_quotation_that_stops_early_is_still_substituted(self) -> None:
        # The tail is not a defect: the reader is shown the rest of the
        # verse the citation names.
        text = "Acts 16:31 says, 'So they said, Believe on the Lord Jesus Christ, and thou shalt be saved,'"
        _markered, subs = pre_substitute(text, "en")
        assert [sub.ref for sub in subs] == [BibleRef("acts", 16, 31)]


class TestAnEnglishVerseIsNotWrappedTwice:
    """English opens and closes with the same character, so a pair added
    around a verse that already carries one cannot be read — there is
    nothing in ``"They replied, "Believe in the Lord Jesus…""`` to say
    which mark answers which. The Berean edition sets direct speech in
    quotation marks and the blockquote is a quotation to the eye without
    any of this, so the marks that are there stay and no more are added.
    """

    def _quoted_verse_substitution(self) -> Substitution:
        return Substitution(
            marker="EQV0000000000000000",
            ref=BibleRef("acts", 16, 31),
            original_inner="«Веруй в Господа Иисуса Христа»",
            opening_quote_lost=True,
            closing_quote_lost=True,
        )

    def test_a_verse_that_already_quotes_is_not_given_a_second_pair(self) -> None:
        canonical = 'They replied, "Believe in the Lord Jesus and you will be saved, you and your household."'
        sub = self._quoted_verse_substitution()
        assert _requote(canonical, sub, f"<blockquote>{sub.marker}</blockquote>", "en") == canonical

    def test_a_german_verse_that_quotes_still_gets_the_german_pair(self) -> None:
        # ``„…“`` around a verse holding ``“`` is still readable, because
        # the two marks are different characters. Only the language whose
        # marks are one character has to abstain.
        canonical = "Sie aber sprachen: Glaube an den Herrn Jesus."
        sub = self._quoted_verse_substitution()
        pointed = _requote(canonical, sub, f"<blockquote>{sub.marker}</blockquote>", "de")
        assert pointed == f"„{canonical}“"
