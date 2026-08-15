"""A quotation spanning two verses is the common case, not the edge one.

`John 3:14-15`, `Genesis 1:1-3`, `Romans 8:1-2` — the Daily Challenge
explanations quote ranges constantly, and so does any teacher writing
about a passage rather than a proof text.

The API reference for a range was built as `JHN.3.14-JHN.3.15`, which
reads like the obvious form and answers 404 for every range there is.
Nothing broke: `fetch_verse` returns `None` for any reason at all, and
`None` means "keep the author's own quotation". So every quotation
spanning two verses reached German and Ukrainian readers in English,
quietly, while the single-verse ones beside them came through in
Luther and Kulish.

Verified against the live API on 2026-08-15: the short form returns
both verses joined, the long form returns nothing.
"""

from __future__ import annotations

import pytest

from app.services.bible.api_source import _usfm_ref
from app.services.bible.references import BibleRef


class TestTheReferenceTheApiAnswers:
    def test_a_single_verse(self):
        assert _usfm_ref(BibleRef("john", 3, 16)) == "JHN.3.16"

    def test_a_range_names_the_book_once(self):
        # The whole defect in one assertion: the second book code is
        # what the API refuses.
        assert _usfm_ref(BibleRef("john", 3, 14, 15)) == "JHN.3.14-15"

    def test_a_long_range(self):
        assert _usfm_ref(BibleRef("genesis", 1, 1, 3)) == "GEN.1.1-3"

    def test_a_book_outside_the_canon_has_no_reference(self):
        assert _usfm_ref(BibleRef("nonexistent", 1, 1)) is None

    @pytest.mark.parametrize(
        ("ref", "expected"),
        [
            (BibleRef("romans", 8, 1, 2), "ROM.8.1-2"),
            (BibleRef("psalms", 23, 1, 6), "PSA.23.1-6"),
            (BibleRef("1john", 4, 8), "1JN.4.8"),
        ],
    )
    def test_the_shape_holds_across_books(self, ref: BibleRef, expected: str):
        assert _usfm_ref(ref) == expected


def test_a_range_never_contains_the_book_code_twice():
    """The regression, stated as a rule rather than as a string.

    Any range that names its book on both sides is the form the API
    404s on, whatever the book.
    """
    for ref in (
        BibleRef("john", 3, 14, 15),
        BibleRef("genesis", 1, 1, 3),
        BibleRef("acts", 2, 1, 4),
    ):
        usfm = _usfm_ref(ref)
        assert usfm is not None
        book = usfm.split(".")[0]
        assert usfm.count(book) == 1, usfm
