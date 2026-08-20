# ruff: noqa: RUF001
"""A verse quoted by the author must still look quoted after we swap it.

The substitution layer replaces a recognised quotation with a marker and
pastes the canonical target-language text back afterwards. The canonical
text is bare — an edition prints Scripture, not somebody's quotation of
it — so for two years the marks the author typed went into the marker
with the verse and never came out.

A bilingual editor read the whole of generation 8 on 2026-08-19 and
counted the result. Of the eighteen featured-verse blockquotes, the
Russian source has quotation marks on eighteen; German has five,
Ukrainian five, English six. The verses that kept their marks are the
ones the layer did *not* recognise: they went to the model as ordinary
prose and came back with the author's punctuation intact. So one lesson
shows the same verse both ways, sometimes twenty lines apart.

The second half of the reading is a different fault with the same
symptom. Six English blockquotes open with no mark and close with one.
That is not the author's punctuation half-surviving — it is the Berean
Standard Bible's. BSB sets direct speech in quotation marks, speech runs
across verse boundaries, and a request for Acts 1:8 comes back as
``But you will receive power … to the ends of the earth.”`` with the
opening mark stranded in verse 7. Verified against the live API on
2026-08-20: of the four editions this platform quotes, only the English
one does it.

Both are fixed here, and the fix has one thing it must never do, which
is add a mark to something that already has one.
"""

from __future__ import annotations

import pytest

from app.schemas.locale import LOCALE_CODES, QUOTATION_MARKS
from app.services.bible import substitution as sub
from app.services.bible.substitution import _swallowed_quotes, post_substitute, pre_substitute
from app.services.translation.typography import normalize_typography

# Acts 1:8 as each of the four editions the platform actually quotes
# prints it — abridged, but with the punctuation each one really uses.
ACTS_1_8 = {
    "en": (
        "But you will receive power when the Holy Spirit comes upon you, "
        "and you will be My witnesses to the ends of the earth."
    ),
    "de": (
        "Aber ihr werdet Kraft empfangen, wenn der Heilige Geist auf euch gekommen ist; "
        "und ihr werdet meine Zeugen sein bis an das Ende der Erde."
    ),
    "uk": ("А приймете силу, як зійде сьвятий Дух на вас; і будете менї сьвідками аж до краю землї."),
    "ru": ("Когда на вас сойдет Святой Дух, вы получите силу и будете Моими свидетелями до края земли."),
}

# The same verse as BSB really answers it: a closing mark whose opening
# is in the previous verse.
ACTS_1_8_EN_WITH_ORPHAN_MARK = ACTS_1_8["en"] + "”"

# A verse the edition quotes in full — both marks present, nothing
# stranded anywhere.
ACTS_2_38_EN_FULLY_QUOTED = "Peter replied, “Repent and be baptized, every one of you.”"


@pytest.fixture
def editions(monkeypatch):
    """Every locale answers with its own edition, and none of it is a
    network call. Returns the table so a test can assert against it."""

    def fake_fetch(ref, locale):
        return ACTS_1_8.get(locale)

    monkeypatch.setattr(sub, "fetch_verse", fake_fetch)
    return ACTS_1_8


@pytest.fixture
def english_edition_that_quotes_speech(monkeypatch):
    """English answers the way BSB really does; the rest are unchanged."""

    def fake_fetch(ref, locale):
        if locale == "en":
            return ACTS_1_8_EN_WITH_ORPHAN_MARK
        return ACTS_1_8.get(locale)

    monkeypatch.setattr(sub, "fetch_verse", fake_fetch)


def _quoted_by_the_author() -> str:
    return f'<blockquote>"{ACTS_1_8["en"]}" (Acts 1:8).</blockquote>'


def _left_bare_by_the_author() -> str:
    return f"<blockquote>{ACTS_1_8['en']}</blockquote> (Acts 1:8)."


def _all_marks_in(text: str) -> list[str]:
    return [char for char in text if char in '"«»„“”']


def _marks_in(text: str) -> int:
    return len(_all_marks_in(text))


class TestAVerseTheAuthorQuotedComesBackQuoted:
    @pytest.mark.parametrize("locale", ["ru", "en", "de", "uk"])
    def test_in_the_marks_that_language_writes(self, editions, locale) -> None:
        markered, subs = pre_substitute(_quoted_by_the_author(), "en")
        assert len(subs) == 1, "the author copied the edition verbatim; this is a quotation"

        final = post_substitute(markered, subs, locale)

        opening, closing = QUOTATION_MARKS[locale]
        assert opening + editions[locale] + closing in final

    def test_the_author_typed_english_marks_and_a_german_reader_gets_german_ones(self, editions) -> None:
        markered, subs = pre_substitute(_quoted_by_the_author(), "en")
        final = post_substitute(markered, subs, "de")
        assert "„" in final and "“" in final
        assert '"' not in final, "the source language's marks must not reach the German page"

    @pytest.mark.parametrize("locale", ["ru", "en", "de", "uk"])
    def test_the_restored_marks_are_left_alone_by_the_typography_pass(self, editions, locale) -> None:
        # The two modules read the same table, so what substitution
        # writes is already what typography would have written. (The pass
        # still re-points the German *reference* — ``Apg. 1,8`` — which is
        # its own job and not this test's business.)
        markered, subs = pre_substitute(_quoted_by_the_author(), "en")
        final = post_substitute(markered, subs, locale)
        opening, closing = QUOTATION_MARKS[locale]

        pointed = normalize_typography(final, locale)

        assert opening + editions[locale] + closing in pointed


class TestAVerseTheAuthorDidNotQuoteComesBackBare:
    def test_a_blockquote_with_no_marks_gains_none(self, editions) -> None:
        markered, subs = pre_substitute(_left_bare_by_the_author(), "en")
        assert len(subs) == 1

        final = post_substitute(markered, subs, "de")

        assert ACTS_1_8["de"] in final
        assert _marks_in(final) == 0, "a blockquote is already a quotation to the eye"

    def test_a_closing_mark_in_the_paragraph_above_is_not_this_verse_s(self, editions) -> None:
        # ``</p><blockquote>`` is a boundary a reader sees. Before the
        # scan learned to stop there, the previous sentence's closing
        # mark counted as this verse's opening one.
        html = f"<p>Он сказал: «слово».</p><blockquote>{ACTS_1_8['en']}</blockquote> (Acts 1:8)."
        _markered, subs = pre_substitute(html, "en")
        assert len(subs) == 1
        assert (subs[0].opening_quote_lost, subs[0].closing_quote_lost) == (False, False)

    def test_a_paraphrase_is_not_touched_at_all(self, editions) -> None:
        # Nothing to restore because nothing was replaced — the guard
        # that keeps this fix inside the substitution layer.
        html = "<blockquote>The Spirit will come and you will speak of Me everywhere.</blockquote> (Acts 1:8)."
        markered, subs = pre_substitute(html, "en")
        assert subs == []
        assert markered == html


class TestOneMarkInsideTheSpanAndOneOutsideIt:
    """The case that produced six mismatched English blockquotes.

    Where the marks fall depends on where the author put the citation.
    ``«…до края земли (Деян. 1:8)»`` leaves the opening mark inside the
    replaced span, where it is destroyed, and the closing mark after the
    citation, where it survives untouched. Restoring both gives the verse
    two closing marks; restoring neither is the defect.
    """

    def test_only_the_swallowed_mark_is_restored(self, editions) -> None:
        html = f'<blockquote>"{ACTS_1_8["en"]} (Acts 1:8)"</blockquote>'
        markered, subs = pre_substitute(html, "en")
        assert len(subs) == 1
        assert (subs[0].opening_quote_lost, subs[0].closing_quote_lost) == (True, False)

        final = post_substitute(markered, subs, "en")

        assert '"' + ACTS_1_8["en"] in final, "the eaten opening mark comes back"
        assert _marks_in(final) == 2, "and the surviving closing mark is not joined by a second"

    @pytest.mark.parametrize(
        ("replaced", "before", "after", "expected"),
        [
            ("«Но вы примете силу» ", "<blockquote>", "(Деян. 1:8).</blockquote>", (True, True)),
            ("«Но вы примете силу ", "<blockquote>", "(Деян. 1:8)».</blockquote>", (True, False)),
            ("Но вы примете силу» ", "<blockquote>«", "(Деян. 1:8).</blockquote>", (False, True)),
            ("Но вы примете силу", "Пётр писал: «", "» и добавил.", (False, False)),
            ("Но вы примете силу ", "<blockquote>", "(Деян. 1:8).</blockquote>", (False, False)),
        ],
        ids=[
            "both marks inside the span",
            "opening inside, closing after the citation",
            "opening outside, closing inside",
            "both marks outside — the inline case, already correct",
            "no marks at all",
        ],
    )
    def test_each_side_is_answered_on_its_own(self, replaced, before, after, expected) -> None:
        assert _swallowed_quotes(replaced, before, after) == expected

    def test_one_mark_alone_is_not_a_quotation(self) -> None:
        # A plural possessive at the end of the span, and nothing at the
        # start. We cannot tell a half-open quotation from an apostrophe,
        # so nothing is restored.
        assert _swallowed_quotes("the disciples' ", "<blockquote>", "(Acts 1:8).</blockquote>") == (False, False)


class TestNothingGainsDoubleMarksByBeingProcessedTwice:
    def test_running_the_restore_again_changes_nothing(self, editions) -> None:
        markered, subs = pre_substitute(_quoted_by_the_author(), "en")
        once = post_substitute(markered, subs, "en")
        assert post_substitute(once, subs, "en") == once

    def test_a_page_translated_from_an_already_translated_page(self, editions) -> None:
        # The realistic version: the output of one full cycle is fed
        # through the next one, which recognises the quotation again
        # because it now looks exactly like the edition.
        markered, subs = pre_substitute(_quoted_by_the_author(), "en")
        once = post_substitute(markered, subs, "en")

        markered_again, subs_again = pre_substitute(once, "en")
        twice = post_substitute(markered_again, subs_again, "en")

        assert _marks_in(twice) == 2
        assert '""' not in twice

    def test_a_model_that_closed_the_quotation_itself_is_not_corrected_twice(self, editions) -> None:
        # A model handed an opaque token beside a citation sometimes
        # supplies the mark it thinks is missing. That mark counts.
        markered, subs = pre_substitute(_quoted_by_the_author(), "en")
        tampered = markered.replace(subs[0].marker, subs[0].marker + '"')

        final = post_substitute(tampered, subs, "en")

        assert _marks_in(final) == 2
        assert '""' not in final

    def test_an_inline_quotation_keeps_its_own_marks_and_no_others(self, editions) -> None:
        # ``_QUOTED_SPAN`` replaces only what is *between* the marks, so
        # the author's are still standing. This path was never broken and
        # must not be "fixed".
        html = f'Luke records: "{ACTS_1_8["en"]}" (Acts 1:8).'
        markered, subs = pre_substitute(html, "en")
        assert len(subs) == 1

        final = post_substitute(markered, subs, "en")

        assert _marks_in(final) == 2


class TestTheEditionsOwnMarkIsNotTheAuthors:
    def test_an_orphan_closing_mark_does_not_reach_the_reader(self, english_edition_that_quotes_speech) -> None:
        # The exact production shape: BSB's Acts 1:8 ends in a mark whose
        # opening is in verse 7, set inside a blockquote the author left
        # bare. The reader saw a verse that closes a quotation it never
        # opened.
        markered, subs = pre_substitute(_left_bare_by_the_author(), "en")
        final = post_substitute(markered, subs, "en")

        assert _marks_in(final) == 0
        assert ACTS_1_8["en"] in final, "only the mark goes; the verse is untouched"

    def test_the_author_s_marks_replace_it_rather_than_join_it(self, english_edition_that_quotes_speech) -> None:
        markered, subs = pre_substitute(_quoted_by_the_author(), "en")
        final = post_substitute(markered, subs, "en")

        assert '"' + ACTS_1_8["en"] + '"' in final
        assert _marks_in(final) == 2

    def test_a_verse_the_edition_quotes_in_full_keeps_both_marks(self, monkeypatch) -> None:
        monkeypatch.setattr(sub, "fetch_verse", lambda ref, locale: ACTS_2_38_EN_FULLY_QUOTED)
        html = f"<blockquote>{ACTS_2_38_EN_FULLY_QUOTED}</blockquote> (Acts 2:38)."
        markered, subs = pre_substitute(html, "en")
        assert len(subs) == 1

        final = post_substitute(markered, subs, "en")

        assert ACTS_2_38_EN_FULLY_QUOTED in final, "a balanced pair belongs to the verse"

    def test_an_unpaired_mark_in_the_middle_is_left_where_it_is(self, monkeypatch) -> None:
        # ``Jesus answered, “I am the way…`` — the opening of a speech
        # that closes two verses later. It is unbalanced and it is the
        # edition's, but from one verse there is no telling whether
        # removing it or completing it is the smaller lie.
        john_14_6 = "Jesus answered, “I am the way and the truth and the life."
        monkeypatch.setattr(sub, "fetch_verse", lambda ref, locale: john_14_6)
        html = f"<blockquote>{john_14_6}</blockquote> (John 14:6)."
        markered, subs = pre_substitute(html, "en")
        assert len(subs) == 1

        final = post_substitute(markered, subs, "en")

        assert john_14_6 in final


class TestOneLessonShowsOneShape:
    """The editor's actual complaint, end to end.

    A lesson that quotes a verse the layer recognises and another it does
    not has to present both the same way. The recognised one is restored
    here; the unrecognised one keeps the marks the author typed and is
    re-pointed by the typography pass. Only if the two agree is the
    lesson consistent, which is why they read the same table.
    """

    @pytest.mark.parametrize("locale", ["en", "de", "uk"])
    def test_a_restored_verse_and_a_paraphrase_are_marked_alike(self, editions, locale) -> None:
        lesson = (
            f'<blockquote>"{ACTS_1_8["en"]}" (Acts 1:8).</blockquote>'
            "<p>Luke says it again: «the Spirit will make you witnesses everywhere» (Acts 1:8).</p>"
        )
        markered, subs = pre_substitute(lesson, "en")
        assert len(subs) == 1, "the paraphrase is not a quotation the layer recognises"

        final = normalize_typography(post_substitute(markered, subs, locale), locale)

        assert set(_all_marks_in(final)) == set(QUOTATION_MARKS[locale]), (
            "every mark on the page is one this language writes"
        )
        assert len(_all_marks_in(final)) == 4, "two quotations, two pairs"


class TestEveryLanguageHasItsQuotationMarks:
    def test_no_served_locale_is_missing_from_the_table(self) -> None:
        assert set(QUOTATION_MARKS) == set(LOCALE_CODES)

    @pytest.mark.parametrize("locale", list(LOCALE_CODES))
    def test_a_quotation_set_in_them_is_a_fixed_point_of_the_typography_pass(self, locale) -> None:
        opening, closing = QUOTATION_MARKS[locale]
        quoted = f"{opening}Ein Wort{closing}"
        assert normalize_typography(quoted, locale) == quoted
