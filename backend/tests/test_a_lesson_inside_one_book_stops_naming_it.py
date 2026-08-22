# ruff: noqa: RUF001
# Russian prose fixtures, quoted from production; single Cyrillic letters
# are words here and the punctuation is the author's.
"""A citation that names chapter and verse and no book.

The defect
----------
A course about the book of Acts writes ``Деян. 1:8`` once, on the first
page, and after that writes ``(1:8)`` — exactly as its reader stops
reading the book's name. The reference parser required a book name, so
every one of those citations was invisible, and the verse quoted beside
it was never recognised as a quotation. It went to the model as prose
and came back as the model's own rendering.

Read on the page, that is one verse printed twice in one lesson, two
different ways. Production, German, entity
``15e7b130-888b-4edf-b936-a8e15241c052``, on 2026-08-22 — the
memory-verse callout, whose citation reads ``(Apg. 1,8)``::

    „Aber ihr werdet Kraft empfangen, wenn der Heilige Geist auf euch
    gekommen ist; und ihr werdet meine Zeugen sein, sowohl in
    Jerusalem …“

and, four screens down, the same verse under the heading
"Schlüsselvers und Aufbau", whose citation reads ``(1,8)``::

    „Aber ihr werdet Kraft empfangen, wenn der Heilige Geist auf euch
    kommen wird, und ihr werdet meine Zeugen sein in Jerusalem …“

Elberfelder, and then a model's German. The Russian source has the two
blockquotes word for word identical; the only difference between them is
that one names its book.

Measured over the live catalogue on 2026-08-22: 196 book-less citations
in the Russian sources of the three published courses, against 13
blockquotes whose citation names its book. Five of the eighteen
blockquotes a reader can reach were unrecognised for this reason alone.

How the book is recovered
-------------------------
Not by guessing. The candidates are the books this document already
names in full somewhere, offered nearest-citation-first, and the words
decide — the same division of labour the inline path already used to
pair a quotation with one of several references. A wrong book answers
with a verse that does not resemble the quotation, and is dropped.
"""

from __future__ import annotations

from app.services.bible.references import BibleRef, parse_bare_references
from app.services.bible.substitution import pre_substitute

# The Russian source of the two blockquotes above, verbatim from
# ``chapter_block`` ``15e7b130-888b-4edf-b936-a8e15241c052``.
ACTS_1_8 = (
    "«Но вы примете силу, когда сойдёт на вас Дух Святой; и будете Мне свидетелями "
    "в Иерусалиме и во всей Иудее и Самарии и даже до края земли»"
)


class TestTheCitationIsRead:
    def test_a_citation_with_no_book_is_found_where_one_with_a_book_would_be(self) -> None:
        found = parse_bare_references("<blockquote>…до края земли» (1:8).</blockquote>")
        assert [(ref.chapter, ref.verse_start, ref.verse_end) for ref in found] == [(1, 8, None)]

    def test_a_citation_that_names_its_book_is_not_read_twice(self) -> None:
        # ``(Деян. 1:8)`` is already a reference. The bare pattern
        # allows nothing between the paren and the first digit, so it
        # does not also match the numbers inside it.
        assert parse_bare_references("Как сказано в (Деян. 1:8), сила приходит от Духа.") == []

    def test_a_range_and_a_german_comma_are_both_citations(self) -> None:
        found = parse_bare_references("(28:30–31) und (1,8)")
        assert [(ref.chapter, ref.verse_start, ref.verse_end) for ref in found] == [(28, 30, 31), (1, 8, None)]

    def test_numbers_that_are_not_in_parentheses_are_not_a_citation(self) -> None:
        # The whole guard. Outside parentheses, ``18:30`` is a time,
        # ``2:1`` is a score and ``1:8`` is a ratio, and nothing in the
        # string tells them from a chapter and a verse.
        assert parse_bare_references("Занятие начинается в 18:30, счёт 2:1, масштаб 1:8.") == []


class TestTheBookComesFromTheDocument:
    def test_the_body_quotation_is_recognised_by_the_book_the_lesson_names(self) -> None:
        html = (
            "<p><strong>Чтение Писания:</strong> Деяния 1:1–26.</p>"
            "<h2>Программный стих и композиция</h2>"
            f"<blockquote>{ACTS_1_8} (1:8).</blockquote>"
        )
        _markered, subs = pre_substitute(html, "ru")
        assert [sub.ref for sub in subs] == [BibleRef("acts", 1, 8)]

    def test_the_two_quotations_of_one_verse_are_both_recognised(self) -> None:
        # The defect this file exists for: one lesson, one verse, two
        # blockquotes, and only the one naming its book was replaced.
        html = (
            "<p><strong>Чтение Писания:</strong> Деяния 1:1–26.</p>"
            f'<div class="callout callout-verse"><blockquote>{ACTS_1_8} (Деян. 1:8).</blockquote></div>'
            f"<blockquote>{ACTS_1_8} (1:8).</blockquote>"
        )
        _markered, subs = pre_substitute(html, "ru")
        assert [sub.ref for sub in subs] == [BibleRef("acts", 1, 8), BibleRef("acts", 1, 8)]

    def test_a_document_that_never_names_a_book_substitutes_nothing(self) -> None:
        html = f"<blockquote>{ACTS_1_8} (1:8).</blockquote>"
        markered, subs = pre_substitute(html, "ru")
        assert subs == []
        assert markered == html

    def test_a_book_the_words_do_not_fit_is_declined_rather_than_pasted(self) -> None:
        # Genesis 1:8 exists and is "И назвал Бог твердь небом". The
        # document names Genesis and nothing else, so Genesis is the
        # only candidate — and it is refused, because the quotation is
        # Acts. Proximity orders the candidates; the words answer.
        html = f"<p>Читайте Бытие 1:1–31.</p><blockquote>{ACTS_1_8} (1:8).</blockquote>"
        _markered, subs = pre_substitute(html, "ru")
        assert subs == []


class TestTheCitationIsLeftAsTheAuthorWroteIt:
    def test_a_book_less_citation_does_not_gain_a_book_name(self) -> None:
        # ``_localize_ref_tail`` rewrites ``(Деян. 1:8)`` into the target
        # language's short form. There is no book name in ``(1:8)`` to
        # rewrite, and putting one there would print a word the author
        # chose to leave out.
        html = f"<p><strong>Чтение Писания:</strong> Деяния 1:1–26.</p><blockquote>{ACTS_1_8} (1:8).</blockquote>"
        _markered, subs = pre_substitute(html, "ru")
        assert [sub.ref_tail for sub in subs] == [""]

    def test_a_citation_that_names_its_book_still_carries_its_tail(self) -> None:
        html = f"<p><strong>Чтение Писания:</strong> Деяния 1:1–26.</p><blockquote>{ACTS_1_8} (Деян. 1:8).</blockquote>"
        _markered, subs = pre_substitute(html, "ru")
        assert subs[0].ref_tail.strip().startswith("(Деян. 1:8)")
