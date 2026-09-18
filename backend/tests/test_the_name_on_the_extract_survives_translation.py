"""A copyright notice is not a sentence, and must not be translated like one.

17 U.S.C. § 1202(b) makes it unlawful to remove or alter copyright-management
information — the author, the title, the terms, the identifying number.
Statutory damages per work, no requirement that the underlying copying be
infringing, and § 512's safe harbour does not reach it: the safe harbour
answers for what users upload, and rewriting the notice is the platform's own
act. Post University v. Learneo (D. Conn., March 2026) attached $75.3m to that
reading, counted per work.

The pipeline translates every lesson into three more languages. Before this,
a line reading "© 2019 Тимоти Келлер" went to the model with everything else,
and a machine translator has no notion of a line that must not be touched.

These tests pin both halves of the answer: the notice travels as a marker and
comes back identical, and ordinary prose that merely mentions a book does not.
The second half is not a nicety. Run unanchored against production on
2026-09-17, the "from the book" rule matched 39 rows of 29,015 and was wrong
about every one of them — "Geography that repeats from book to book", "A legal
rule from the book of Deuteronomy". Freezing those in the source language
across four locales would have been a different bug, not a cautious one.
"""

from __future__ import annotations

import re
from typing import ClassVar

import pytest

from app.services.attribution import (
    ATTRIBUTION_MARKER_PREFIX,
    find_attributions,
    post_substitute,
    pre_substitute,
)

_MARKER = re.compile(r"EQA[0-9a-f]{16}")


# What a teacher actually writes under an extract, in the four languages.
PROTECTED = [
    "© 2019 Timothy Keller. All rights reserved.",
    "Copyright 2021 Crossway Books",
    "© 2020 Издательство «Мирт». Все права защищены.",
    "© 2018 Brunnen Verlag. Alle Rechte vorbehalten.",
    "© 2022 Видавництво «Свічадо». Усі права застережено.",
    "Источник: Джон Стотт, «Крест Христа», глава 4",
    "Source: John Stott, The Cross of Christ, chapter 4",
    "Quelle: Dietrich Bonhoeffer, Nachfolge, Kapitel 1",
    "Джерело: Джон Стотт, «Хрест Христа», розділ 4",
    "Из книги Джона Стотта «Крест Христа», 1986",
    "From the book «The Cross of Christ» by John Stott, 1986",
    "Aus dem Buch „Nachfolge“ von Dietrich Bonhoeffer, 1937",
    "З книги «Хрест Христа», 1986",
    "Печатается по: Мирт, 2004",
    "ISBN 978-5-88869-253-1",
]

# What it must leave alone, because it is a sentence.
ORDINARY = [
    # The 39 production rows, in the two shapes they actually took.
    "Geography that repeats from book to book; the structure of the sanctuary.",
    "География, которая повторяется из книги в книгу; устройство святилища.",
    "A legal rule from the book of Deuteronomy",
    "Правовое предписание из книги Второзакония",
    "Правовий припис із книги Повторення Закону",
    "Rechtsvorschrift aus dem Buch Deuteronomium",
    # And the general case.
    "Paul quotes from the book of Isaiah here.",
    "Эта мысль встречается и в других источниках.",
    "The source of the river is in the mountains.",
]


@pytest.mark.parametrize("line", PROTECTED)
def test_an_attribution_is_lifted_out_of_the_text(line: str) -> None:
    hidden, spans = pre_substitute(line)

    assert spans, f"not recognised as an attribution: {line}"
    assert line not in hidden, "the notice was still in the text handed to the model"


@pytest.mark.parametrize("line", ORDINARY)
def test_a_sentence_that_merely_mentions_a_book_is_left_alone(line: str) -> None:
    hidden, spans = pre_substitute(line)

    assert spans == [], f"ordinary prose was frozen: {line} -> {[s.text for s in spans]}"
    assert hidden == line


@pytest.mark.parametrize("line", PROTECTED)
def test_it_comes_back_character_for_character(line: str) -> None:
    hidden, spans = pre_substitute(line)

    assert post_substitute(hidden, spans) == line


def test_the_marker_is_a_word_in_no_language_we_serve() -> None:
    """``VERSE_`` was an English word, and a model asked for Ukrainian
    translated it — production holds a row spelling that marker in Cyrillic
    where Scripture belongs. The verse marker was renamed for this reason;
    a second family must not reintroduce it."""
    _, spans = pre_substitute("© 2019 Timothy Keller")

    assert spans[0].marker.startswith(ATTRIBUTION_MARKER_PREFIX)
    assert _MARKER.fullmatch(spans[0].marker)
    assert spans[0].marker.isascii()
    assert "\x00" not in spans[0].marker


def test_two_attributions_travel_independently() -> None:
    source = "<p>© 2019 Keller</p><p>Ordinary prose.</p><p>ISBN 978-5-88869-253-1</p>"

    hidden, spans = pre_substitute(source)

    assert len(spans) == 2
    assert spans[0].marker != spans[1].marker
    assert post_substitute(hidden, spans) == source


def test_no_tag_is_ever_swallowed() -> None:
    """A span that ate a ``<p>`` would change the tag census, and
    ``validation._check_tags`` parks a row whose markup moved — permanently,
    because every retry makes the same move."""
    source = '<blockquote><p>The extract.</p></blockquote><p class="src">Источник: Стотт, «Крест Христа»</p>'

    hidden, spans = pre_substitute(source)

    assert spans
    assert all("<" not in span.text and ">" not in span.text for span in spans)
    assert re.findall(r"<[^>]*>", hidden) == re.findall(r"<[^>]*>", source)


def test_a_url_inside_an_attribute_is_not_a_source_line() -> None:
    """Markup is out of reach by construction: only the text between tags is
    scanned. Rule 3 of the system prompt already holds attributes and URLs,
    and a second mechanism reaching into them could only disagree with it."""
    source = '<p>Watch <a href="https://example.org/source">the talk</a>.</p>'

    hidden, spans = pre_substitute(source)

    assert spans == []
    assert hidden == source


def test_a_notice_inside_a_paragraph_takes_its_whole_line() -> None:
    """Not just the symbol. "© 2019 Тимоти Келлер. Перевод издательства
    «Мирт»" is one piece of copyright-management information, and a rule that
    protected the symbol alone would hand the name to the model."""
    source = "<p>© 2019 Тимоти Келлер. Перевод издательства «Мирт».</p>"

    hidden, spans = pre_substitute(source)

    assert len(spans) == 1
    assert "Келлер" in spans[0].text
    assert "Мирт" in spans[0].text
    assert post_substitute(hidden, spans) == source


def test_a_credit_under_an_extract_is_protected() -> None:
    source = "<blockquote><p>Слова.</p></blockquote><p>— Джон Стотт, «Крест Христа», 1986</p>"

    hidden, spans = pre_substitute(source)

    assert [span.text for span in spans] == ["— Джон Стотт, «Крест Христа», 1986"]
    assert post_substitute(hidden, spans) == source


def test_a_dash_that_opens_a_sentence_is_not_a_credit() -> None:
    source = "<p>— Что это значит? — спросил он.</p>"

    _, spans = pre_substitute(source)

    assert spans == []


def test_a_fragment_holding_a_verse_marker_is_left_to_the_verse_layer() -> None:
    """The two marker families must stay disjoint. Each is restored by
    finding its own marker in the text; one nested inside the other's span is
    not in the text when its turn comes, and the verse would be lost."""
    source = "Источник: EQV0c0214d57ac3a0bb, глава 4"

    hidden, spans = pre_substitute(source)

    assert spans == []
    assert hidden == source


def test_find_attributions_reads_without_rewriting() -> None:
    source = "<p>Текст.</p><p>Источник: Стотт, «Крест Христа»</p>"

    assert find_attributions(source) == ["Источник: Стотт, «Крест Христа»"]


class TestTheMeasurementBehindTheThreshold:
    """The production corpus on 2026-09-17, as the rules see it.

    29,015 rows in ``content_versions``. The unanchored "from the book" rule
    matched 39 of them and was wrong about all 39; the anchored rules matched
    zero, and zero of those rows were in fact attributions. Those two numbers
    are the argument for every anchor in ``attribution/substitution.py``, so
    the rows themselves are kept here — a rule that loosens will fail on the
    corpus it was measured against rather than in production.
    """

    ROWS_THAT_MATCHED_THE_NAIVE_RULE: ClassVar[list[str]] = [
        "География, которая повторяется из книги в книгу; устройство святилища; праздники, календарь, деньги и меры.",
        "Географія, яка повторюється з книги в книгу; устрій святилища; свята, календар, гроші та міри.",
        "A legal rule from the book of Deuteronomy",
        "Правовое предписание из книги Второзакония",
        "Правовий припис із книги Повторення Закону",
        "Rechtsvorschrift aus dem Buch Deuteronomium",
    ]

    def test_none_of_them_is_protected(self) -> None:
        frozen = [row for row in self.ROWS_THAT_MATCHED_THE_NAIVE_RULE if find_attributions(row)]

        assert frozen == [], frozen

    def test_the_naive_rule_would_have_caught_every_one(self) -> None:
        """Stated so the anchors are visibly load-bearing rather than decorative."""
        naive = re.compile(r"(из книги|з книги|from the book|aus dem Buch)", re.IGNORECASE)

        assert all(naive.search(row) for row in self.ROWS_THAT_MATCHED_THE_NAIVE_RULE)


class TestThroughTheProvider:
    """End to end, with a model that behaves and one that does not.

    The unit tests above prove the substitution is correct. These prove it is
    actually wired in — that ``translate_within`` hides the notice before the
    call and restores it after, and that a model which drops the marker parks
    the row instead of storing a page with the author's name taken off it.
    """

    SOURCE = "<p>Слова из книги.</p>\n<p>© 2019 Тимоти Келлер. Все права защищены.</p>"

    def _provider(self, monkeypatch: pytest.MonkeyPatch, answer):
        from app.services.translation.gemini import GeminiTranslationProvider
        from app.services.translation.protocol import TranslationResult

        provider = GeminiTranslationProvider.__new__(GeminiTranslationProvider)
        provider._model = "fake"  # type: ignore[attr-defined]
        seen: list[str] = []

        def _generate(request):
            seen.append(request.text)
            return TranslationResult(text=answer(request.text), model="fake")

        monkeypatch.setattr(provider, "_generate", _generate)
        return provider, seen

    def _request(self):
        from app.services.translation.protocol import TranslationRequest

        return TranslationRequest(
            text=self.SOURCE,
            source_locale="ru",
            target_locale="de",
            content_kind="html",
        )

    def test_the_model_is_never_shown_the_notice(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider, seen = self._provider(monkeypatch, lambda text: text)

        provider.translate_within(self._request())

        assert "Тимоти Келлер" not in seen[0]
        assert _MARKER.search(seen[0])

    def test_it_is_back_in_the_answer_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider, _ = self._provider(monkeypatch, lambda text: text)

        result = provider.translate_within(self._request())

        assert "© 2019 Тимоти Келлер. Все права защищены." in result.text
        assert result.lost_attribution is False

    def test_the_typography_pass_does_not_touch_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Restored last, after the pass that re-points quotation marks for
        the target language. A verse wants that treatment; a rights line is
        the one string where re-pointing is itself the alteration § 1202
        names."""
        notice = '<p>© 2019 Timothy Keller, "The Reason for God". All rights reserved.</p>'
        from app.services.translation.protocol import TranslationRequest

        provider, _ = self._provider(monkeypatch, lambda text: text)
        result = provider.translate_within(
            TranslationRequest(text=notice, source_locale="ru", target_locale="de", content_kind="html")
        )

        assert '"The Reason for God"' in result.text

    def test_a_model_that_drops_the_marker_is_reported(self, monkeypatch: pytest.MonkeyPatch) -> None:
        provider, _ = self._provider(monkeypatch, lambda text: _MARKER.sub("", text))

        result = provider.translate_within(self._request())

        assert result.lost_attribution is True

    def test_and_the_executor_parks_the_row(self) -> None:
        from app.services.translation.executor import TranslationTask, _ask
        from app.services.translation.protocol import TranslationResult

        class _Provider:
            def translate(self, request):
                return TranslationResult(text="<p>Worte.</p>", model="fake", lost_attribution=True)

        answer = _ask(
            TranslationTask(
                entity_type="chapter_block",
                entity_id="b-1",
                field="content",
                source_locale="ru",
                target_locale="de",
                text=self.SOURCE,
                content_kind="html",
                source_hash="hash-1",
            ),
            _Provider(),
        )

        assert answer.issues_summary is not None
        assert "attribution_dropped" in answer.issues_summary
