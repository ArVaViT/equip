"""A lesson too long to ask for in one breath is asked for in several.

The block that forced this carries 85 tags — ``div``, ``em``, ``h2``,
``img``, ``p``, ``strong``. Asked to translate the whole thing in one
call, the model sometimes came back with markup that does not match: all
seven ``<em>`` gone (the tags marking the terms the lesson is about), or
six ``<strong>`` invented, or a chapter-and-verse reference missing.
Structural validation caught it every time and parked the row, which is
right — and left the reader with nothing at all where a lesson should
be. Two blocks were in exactly that state, and they were the last
remaining cause of parked rows.

Retrying does not help: sampling is at temperature 0, so the identical
question gets the identical answer, and the correcting pass that quotes
the defect back only sometimes recovers a document this large.

So a long block is cut at top-level block boundaries, each piece is
translated on its own, and the pieces are concatenated. What these tests
pin is everything that must not change when it is: the document comes
back with the markup it left with, a short block still costs one call,
a mangled piece fails the whole document rather than serving half of it,
a quoted verse still gets its canonical text, and a nested list or a
callout wrapper is never cut open.
"""

# ruff: noqa: RUF001, RUF003
# The fixtures are Russian lesson prose; a Cyrillic "о" next to a
# Latin tag name is the subject matter, not a typo.

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

import httpx
import pytest

from app.services.bible.references import BibleRef
from app.services.bible.store import lookup
from app.services.translation.executor import TranslationTask, _ask
from app.services.translation.gemini import GeminiTranslationProvider
from app.services.translation.html_split import _top_level_nodes, split_html_for_translation
from app.services.translation.protocol import TranslationPaused, TranslationRequest
from app.services.translation.validation import tag_names, validate_translation
from tests._fake_translation import fake_translate

if TYPE_CHECKING:
    from collections.abc import Callable

_FENCED = re.compile(r"===BEGIN_[0-9a-f]+===\n(.*)\n===END_[0-9a-f]+===", re.DOTALL)
_MARKER = re.compile(r"EQV[0-9a-f]+")


def _sent_text(request: httpx.Request) -> str:
    """The content the model was actually asked to translate."""
    body = json.loads(request.content.decode())
    prompt = body["contents"][0]["parts"][0]["text"]
    match = _FENCED.search(prompt)
    assert match is not None, f"no fenced content in prompt: {prompt[:200]!r}"
    return match.group(1)


def _provider(reply: Callable[[str], str], sent: list[str]) -> GeminiTranslationProvider:
    """A Gemini provider whose wire is a function from ask to answer."""

    def handler(request: httpx.Request) -> httpx.Response:
        text = _sent_text(request)
        sent.append(text)
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": reply(text)}]}}],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 10},
            },
        )

    return GeminiTranslationProvider(
        api_key="fake-key",
        model="gemini-2.5-flash-lite",
        timeout_seconds=5.0,
        max_output_tokens=4096,
        max_retries=0,
        client=httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0),
    )


def _translated(text: str) -> str:
    return fake_translate(text, target_locale="en")


def _long_lesson(sections: int = 8) -> str:
    """A Russian lesson block shaped like the one that fails.

    Headings, prose with inline emphasis, an illustration and a callout —
    the tag census the failing production block has, at the size that
    provokes it.
    """
    parts = []
    for index in range(1, sections + 1):
        parts.append(f"<h2>Урок {index}</h2>")
        parts.append(
            f"<p>Здесь мы говорим о <em>слове</em> и о том, что значит <strong>служение</strong> в главе {index}.</p>"
        )
        parts.append(f'<div><img src="/img/{index}.png" alt="Иллюстрация"></div>')
    return "".join(parts)


class TestALargeDocumentIsCutUpAndPutBackTogether:
    def test_the_markup_it_leaves_with_is_the_markup_it_comes_back_with(self) -> None:
        source = _long_lesson()
        assert len(tag_names(source)) > 40, "the fixture must be big enough to be split"
        sent: list[str] = []
        provider = _provider(_translated, sent)
        try:
            result = provider.translate(
                TranslationRequest(text=source, source_locale="ru", target_locale="en", content_kind="html")
            )
        finally:
            provider.close()

        assert len(sent) > 1, "a document this large must not go in one call"
        assert tag_names(result.text) == tag_names(source)
        blocking = [
            issue.code
            for issue in validate_translation(
                source=source,
                translated=result.text,
                source_locale="ru",
                target_locale="en",
                content_kind="html",
            )
            if issue.blocking
        ]
        assert blocking == [], "the reassembled document must pass the same check that parks rows"

    def test_the_pieces_are_the_document_and_nothing_else(self) -> None:
        """Reassembly is a concatenation, so the cut has to be a partition.

        No separator, no re-wrapping, no re-indenting: anything the
        splitter adds or drops here is a corrupted lesson downstream.
        """
        source = _long_lesson()
        pieces = split_html_for_translation(source)
        assert len(pieces) > 1
        assert "".join(pieces) == source

    @pytest.mark.parametrize(
        "tail",
        [
            pytest.param("</div>", id="a closing tag with nothing open"),
            pytest.param("<div><p>висит</p>", id="an element left open at the end"),
            pytest.param("<div><p>перепутано</div></p>", id="tags closed in the wrong order"),
        ],
    )
    def test_a_document_we_cannot_read_is_not_cut_up(self, tail: str) -> None:
        """Not splitting is always a legal answer.

        Cutting a document we have misread is exactly how a fragment ends
        up unbalanced, which is the failure this module exists to remove.
        """
        source = _long_lesson() + tail
        assert split_html_for_translation(source) == [source]

    def test_every_section_reaches_the_reader(self) -> None:
        """Each piece is translated, and all of them are in the answer."""
        source = _long_lesson()
        sent: list[str] = []
        provider = _provider(_translated, sent)
        try:
            result = provider.translate(
                TranslationRequest(text=source, source_locale="ru", target_locale="en", content_kind="html")
            )
        finally:
            provider.close()
        assert "".join(sent) == source, "the model saw the whole document, once, in order"
        for index in range(1, 9):
            assert f"/img/{index}.png" in result.text


class TestAShortBlockIsStillOneCall:
    def test_a_small_document_is_not_cut_up(self) -> None:
        """More calls cost more money and more latency, and the failure
        this fixes does not happen to small documents."""
        source = "<h2>Заголовок</h2><p>Короткий <em>абзац</em> о служении.</p>"
        assert len(tag_names(source)) <= 40
        sent: list[str] = []
        provider = _provider(_translated, sent)
        try:
            result = provider.translate(
                TranslationRequest(text=source, source_locale="ru", target_locale="en", content_kind="html")
            )
        finally:
            provider.close()
        assert len(sent) == 1
        assert sent[0] == source
        assert result.text == _translated(source)

    def test_only_html_is_ever_cut_up(self) -> None:
        """A heading or an answer option has no block structure to cut
        along, and none of them is remotely large enough to need it."""
        source = " ".join(f"Предложение номер {n} про служение." for n in range(1, 60))
        sent: list[str] = []
        provider = _provider(_translated, sent)
        try:
            provider.translate(
                TranslationRequest(text=source, source_locale="ru", target_locale="en", content_kind="plain")
            )
        finally:
            provider.close()
        assert len(sent) == 1


class TestAMangledPieceFailsTheWholeDocument:
    """Half a lesson in the reader's language and half in the author's is
    not a better outcome than the gap. One bad piece rejects the lot."""

    @staticmethod
    def _drop_em_in_one_section(text: str) -> str:
        rendered = _translated(text)
        if "Урок 3" in text:
            rendered = rendered.replace("<em>", "").replace("</em>", "")
        return rendered

    def test_the_reassembled_document_does_not_pass_validation(self) -> None:
        source = _long_lesson()
        sent: list[str] = []
        provider = _provider(self._drop_em_in_one_section, sent)
        try:
            result = provider.translate(
                TranslationRequest(text=source, source_locale="ru", target_locale="en", content_kind="html")
            )
        finally:
            provider.close()
        codes = [
            issue.code
            for issue in validate_translation(
                source=source,
                translated=result.text,
                source_locale="ru",
                target_locale="en",
                content_kind="html",
            )
        ]
        assert "markup_mismatch" in codes

    def test_the_bad_piece_earns_a_correcting_pass_of_its_own(self) -> None:
        """The whole point of cutting the document up: the model is asked
        to fix a paragraph, not a lesson."""
        source = _long_lesson()
        sent: list[str] = []
        provider = _provider(self._drop_em_in_one_section, sent)
        try:
            provider.translate(
                TranslationRequest(text=source, source_locale="ru", target_locale="en", content_kind="html")
            )
        finally:
            provider.close()
        repeats = [text for text in sent if sent.count(text) > 1]
        assert repeats, "the piece that came back wrong must be asked again"
        assert all("Урок 3" in text for text in repeats), "and only that piece"
        assert len(set(repeats)) == 1

    def test_the_row_is_parked_rather_than_served(self) -> None:
        source = _long_lesson()
        sent: list[str] = []
        provider = _provider(self._drop_em_in_one_section, sent)
        task = TranslationTask(
            entity_type="chapter_block",
            entity_id="block-1",
            field="content",
            source_locale="ru",
            target_locale="en",
            text=source,
            content_kind="html",
            source_hash="hash-1",
        )
        try:
            answer = _ask(task, provider)
        finally:
            provider.close()
        assert answer.issues_summary is not None
        assert "markup_mismatch" in answer.issues_summary


class TestAVerseInsideOnePieceStillGetsItsCanonicalText:
    @staticmethod
    def _lesson_with_a_quotation() -> str:
        canonical_ru = lookup(BibleRef("acts", 1, 8), "ru")
        assert canonical_ru is not None
        return (
            _long_lesson()
            + f"<blockquote>«{canonical_ru}»</blockquote>"
            + "<p> (Деян. 1:8). Это центральный стих урока.</p>"
        )

    def test_the_placeholder_travels_whole_inside_a_single_piece(self) -> None:
        """A marker split across two pieces restores nothing, and the
        verse is silently deleted with the reference left standing."""
        source = self._lesson_with_a_quotation()
        sent: list[str] = []
        provider = _provider(_translated, sent)
        try:
            provider.translate(
                TranslationRequest(text=source, source_locale="ru", target_locale="en", content_kind="html")
            )
        finally:
            provider.close()
        markers = {marker for text in sent for marker in _MARKER.findall(text)}
        assert len(markers) == 1, "the quotation was recognised and markered exactly once"
        marker = markers.pop()
        carrying = [text for text in sent if marker in text]
        assert len(carrying) == 1, "the marker must be whole, in one piece"
        assert carrying[0].count(marker) == 1

    def test_the_canonical_target_text_is_restored(self) -> None:
        source = self._lesson_with_a_quotation()
        canonical_en = lookup(BibleRef("acts", 1, 8), "en")
        assert canonical_en is not None
        sent: list[str] = []
        provider = _provider(_translated, sent)
        try:
            result = provider.translate(
                TranslationRequest(text=source, source_locale="ru", target_locale="en", content_kind="html")
            )
        finally:
            provider.close()
        assert not _MARKER.search(result.text), "no sentinel may reach the reader"
        assert canonical_en in result.text
        assert result.lost_scripture is False


class TestNestedListsAndCalloutsSurvive:
    @staticmethod
    def _lesson_with_structure() -> str:
        return (
            _long_lesson()
            + '<div class="callout"><h3>Запомните</h3><p>Служение — это <em>дар</em>.</p></div>'
            + "<ul><li>первое<ul><li>вложенное</li><li>ещё вложенное</li></ul></li><li>второе</li></ul>"
        )

    def test_the_document_round_trips(self) -> None:
        source = self._lesson_with_structure()
        sent: list[str] = []
        provider = _provider(_translated, sent)
        try:
            result = provider.translate(
                TranslationRequest(text=source, source_locale="ru", target_locale="en", content_kind="html")
            )
        finally:
            provider.close()
        assert tag_names(result.text) == tag_names(source)

    def test_no_piece_is_an_unbalanced_fragment(self) -> None:
        """A cut inside an element would hand the model half a ``<div>``,
        which is inventing the failure this module exists to remove."""
        for piece in split_html_for_translation(self._lesson_with_structure()):
            assert _top_level_nodes(piece) is not None, f"unbalanced piece: {piece[:120]!r}"

    def test_a_list_is_never_separated_from_its_items(self) -> None:
        pieces = split_html_for_translation(self._lesson_with_structure())
        holding = [piece for piece in pieces if "<ul>" in piece]
        assert len(holding) == 1
        assert holding[0].count("<ul>") == holding[0].count("</ul>") == 2

    def test_a_callout_wrapper_is_never_cut_open(self) -> None:
        pieces = split_html_for_translation(self._lesson_with_structure())
        holding = [piece for piece in pieces if 'class="callout"' in piece]
        assert len(holding) == 1
        assert "</div>" in holding[0]
        assert "Запомните" in holding[0]


class _SpentAfter:
    """A clock that allows ``allowance`` calls and then says no."""

    def __init__(self, allowance: int) -> None:
        self.allowance = allowance
        self.asked = 0

    def can_afford_one_call(self) -> bool:
        self.asked += 1
        return self.asked <= self.allowance


class TestADocumentThatRunsOutOfTimeWritesNothing:
    def test_the_pass_is_paused_rather_than_half_written(self) -> None:
        source = _long_lesson()
        sent: list[str] = []
        provider = _provider(_translated, sent)
        try:
            with pytest.raises(TranslationPaused):
                provider.translate_within(
                    TranslationRequest(text=source, source_locale="ru", target_locale="en", content_kind="html"),
                    budget=_SpentAfter(1),
                )
        finally:
            provider.close()
        assert len(sent) < len(split_html_for_translation(source))

    def test_the_row_is_deferred_and_not_recorded(self) -> None:
        """No text, no failure, no retry spent — the job simply comes
        back to this document with a fresh allowance."""
        source = _long_lesson()
        sent: list[str] = []
        provider = _provider(_translated, sent)
        task = TranslationTask(
            entity_type="chapter_block",
            entity_id="block-2",
            field="content",
            source_locale="ru",
            target_locale="en",
            text=source,
            content_kind="html",
            source_hash="hash-2",
        )
        try:
            answer = _ask(task, provider, _SpentAfter(1))  # type: ignore[arg-type]
        finally:
            provider.close()
        assert answer.deferred is True
        assert answer.failed is False
        assert answer.text is None

    def test_the_first_call_is_the_one_the_executor_already_authorised(self) -> None:
        """``execute_plan`` checks the budget before the batch. Asking
        again for the first piece would refuse work that was already paid
        for; every call splitting *added* is what has to be asked about.
        """
        source = _long_lesson()
        sent: list[str] = []
        provider = _provider(_translated, sent)
        clock = _SpentAfter(0)
        try:
            with pytest.raises(TranslationPaused):
                provider.translate_within(
                    TranslationRequest(text=source, source_locale="ru", target_locale="en", content_kind="html"),
                    budget=clock,
                )
        finally:
            provider.close()
        assert len(sent) == 1
