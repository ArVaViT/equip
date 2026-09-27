# ruff: noqa: RUF001
"""A quoted verse ends the way a quotation ends, not the way the verse does.

Found on 2026-09-26 in the first Daily Challenge question whose Russian
went through the pipeline. Romans 1:1 ends in a comma in every edition,
because Paul's sentence runs to verse 7, and the reader got

    Римлянам 1:1 гласит: «От Павла, … Божьей Радостной Вести,». Этот стих…

and in German, where the author's full stop had been inside the English
quotation marks and so inside the marker:

    Römer 1,1 besagt: „Paulus, … abgesondert zum Evangelium Gottes“ Dieser Vers…

and on Acts 27:1, where the edition's verse ends in a stop and the model
wrote a second one after the marker:

    Деян. 27:1 гласит: «…из императорского полка.».

Counted on live rows the same day: 47 German and 53 Ukrainian Daily
Challenge explanations close a quotation on a comma, colon or semicolon.

The words stay the edition's. Only the punctuation at the seam moves.
"""

from __future__ import annotations

import pytest

from app.services.bible import substitution
from app.services.bible.references import BibleRef
from app.services.bible.substitution import Substitution, post_substitute

_MARKER = "EQV0123456789abcdef"


def _sub(original_inner: str) -> Substitution:
    return Substitution(
        marker=_MARKER,
        ref=BibleRef("romans", 1, 1),
        original_inner=original_inner,
        ref_tail="",
        opening_quote_lost=True,
        closing_quote_lost=True,
    )


@pytest.fixture
def edition(monkeypatch):
    """Say what the edition prints, without a network."""
    texts: dict[str, str] = {}

    def _canonical(ref, locale):
        return texts.get(locale)

    monkeypatch.setattr(substitution, "canonical_for_display", _canonical)
    return texts


class TestAVerseThatRunsOn:
    def test_the_comma_the_verse_ends_in_does_not_close_the_quotation(self, edition) -> None:
        edition["ru"] = "От Павла, слуги Иисуса Христа, избранного для возвещения Божьей Радостной Вести,"
        html = f"Римлянам 1:1 гласит: {_MARKER}. Этот стих ясно указывает на его призвание."
        out = post_substitute(html, [_sub("Paul, a servant of Christ Jesus, set apart for the gospel of God.")], "ru")
        assert "Радостной Вести». Этот стих" in out

    @pytest.mark.parametrize("mark", [",", ";", ":"])
    def test_every_mark_that_means_it_goes_on(self, edition, mark: str) -> None:
        edition["de"] = f"Und Gott redete alle diese Worte und sprach{mark}"
        out = post_substitute(
            f"2. Mose 20,1 besagt: {_MARKER}, was darauf hindeutet …",
            [_sub("And God spake all these words, saying,")],
            "de",
        )
        assert "und sprach“, was" in out


class TestTheAuthorsFullStop:
    def test_it_comes_back_when_a_new_sentence_follows(self, edition) -> None:
        edition["de"] = "Paulus, Knecht Jesu Christi, berufener Apostel, abgesondert zum Evangelium Gottes"
        out = post_substitute(
            f"Römer 1,1 besagt: {_MARKER} Dieser Vers zeigt es deutlich.",
            [_sub("Paul, a servant of Christ Jesus, set apart for the gospel of God.")],
            "de",
        )
        assert "Evangelium Gottes“. Dieser Vers" in out

    def test_it_comes_back_at_the_very_end(self, edition) -> None:
        edition["uk"] = "Павел, слуга Ісуса Христа, вибраний на благовістуваннє Боже,"
        out = post_substitute(
            f"Римлян 1:1 зазначає: {_MARKER}", [_sub("Paul, … set apart for the gospel of God.")], "uk"
        )
        assert out.endswith("благовістуваннє Боже».")

    def test_english_keeps_it_inside_the_marks(self, edition) -> None:
        edition["en"] = "Paul, a servant of Christ Jesus, called to be an apostle, and set apart for the gospel of God—"
        out = post_substitute(f"Romans 1:1 says, {_MARKER} This verse…", [_sub("Павел, раб Иисуса Христа.")], "en")
        assert 'for the gospel of God." This verse' in out

    def test_not_before_a_citation(self, edition) -> None:
        """«…» (Рим. 1:1). — the stop belongs after the citation, where the
        author put it."""
        edition["ru"] = "От Павла, слуги Иисуса Христа"
        out = post_substitute(f"Он пишет: {_MARKER} (Рим. 1:1).", [_sub("Paul, a servant of Christ Jesus.")], "ru")
        assert "Христа» (Рим. 1:1)." in out

    def test_not_before_a_sentence_that_goes_on(self, edition) -> None:
        edition["ru"] = "От Павла, слуги Иисуса Христа"
        out = post_substitute(
            f"Слова {_MARKER} показывают, кем он был.", [_sub("Paul, a servant of Christ Jesus.")], "ru"
        )
        assert "Христа» показывают" in out

    def test_not_when_the_author_had_none(self, edition) -> None:
        edition["de"] = "Paulus, Knecht Jesu Christi"
        out = post_substitute(f"Er schreibt {_MARKER} Dieser …", [_sub("Paul, a servant of Christ Jesus")], "de")
        assert "Christi“ Dieser" in out


class TestTwoStops:
    def test_russian_keeps_the_one_after_the_guillemet(self, edition) -> None:
        edition["ru"] = "Павла и других заключенных передали сотнику по имени Юлий, из императорского полка."
        out = post_substitute(f"Деян. 27:1 гласит: {_MARKER}.", [_sub("… a centurion named Julius.")], "ru")
        assert out.endswith("императорского полка».")

    def test_german_keeps_the_editions(self, edition) -> None:
        edition["de"] = "… einem Hauptmann, mit Namen Julius, von der Schar des Augustus."
        out = post_substitute(f"Apg 27,1 besagt: {_MARKER}.", [_sub("… a centurion named Julius.")], "de")
        assert out.endswith("des Augustus.“")

    def test_russian_moves_a_lone_stop_outside(self, edition) -> None:
        edition["ru"] = "Как может юноша содержать в чистоте свой путь? Живя согласно слову Твоему."
        out = post_substitute(f"Псалом 118:9 гласит: {_MARKER}", [_sub("How can a young man keep his way pure?")], "ru")
        assert out.endswith("слову Твоему».")


class TestWhatItMustNotTouch:
    def test_a_question_mark_stays_inside(self, edition) -> None:
        edition["ru"] = "Кто сей, омрачающий Провидение словами без смысла?"
        out = post_substitute(
            f"Бог спрашивает: {_MARKER}. Это вопрос.", [_sub("Who is this that darkens counsel?")], "ru"
        )
        assert "без смысла?». Это вопрос." in out

    def test_a_verse_set_without_marks_is_left_as_printed(self, edition) -> None:
        edition["ru"] = "От Павла, слуги Иисуса Христа,"
        sub = Substitution(
            marker=_MARKER,
            ref=BibleRef("romans", 1, 1),
            original_inner="Paul, a servant of Christ Jesus,",
            ref_tail="",
            opening_quote_lost=False,
            closing_quote_lost=False,
        )
        out = post_substitute(f"<blockquote>{_MARKER}</blockquote>", [sub], "ru")
        assert out == "<blockquote>От Павла, слуги Иисуса Христа,</blockquote>"

    def test_an_ellipsis_is_not_two_stops(self, edition) -> None:
        edition["de"] = "Am Anfang war das Wort…"
        out = post_substitute(
            f"Johannes 1,1 besagt: {_MARKER}. Dies …", [_sub("In the beginning was the Word...")], "de"
        )
        assert "das Wort…“. Dies" in out
