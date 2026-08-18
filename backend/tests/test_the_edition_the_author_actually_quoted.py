"""Recognising a quotation means knowing which Bible the author owns.

The layer that swaps a quoted verse for the canonical target-language
text has to first decide "is this a quotation at all?", and it does that
by comparing the author's words against the canonical wording. Which
canonical wording is exactly the question.

Production got it wrong in the most expensive way available. The Russian
edition behind the API is a modern paraphrase; the authors here quote
the Synodal text. Acts 8:4 as an author writes it scores 0.42 against
the API wording and 0.89 against the bundled Synodal one, and the code
asked the API first and stopped there. So no Russian quotation was ever
recognised — in the language the entire catalogue is written in — and
every quoted verse went to the model to be re-worded instead.

Measured over 524 production strings carrying a reference: 34 verses
were substituted before, 68 after. Half the Scripture in the catalogue
was being paraphrased by a machine translator.
"""

from __future__ import annotations

import pytest

from app.services.bible import substitution as sub
from app.services.bible.references import parse_references
from app.services.bible.substitution import canonical_candidates_for_source, pre_substitute

ACTS_8_4_SYNODAL = "Между тем рассеявшиеся ходили и благовествовали слово."
ACTS_8_4_PARAPHRASE = (
    "Между тем, рассеявшиеся, изгнанные из своих мест, возвещали слово Божье везде, куда бы они ни приходили."
)


@pytest.fixture
def acts_8_4():
    refs = parse_references("Деян. 8:4")
    assert refs, "the reference itself must still parse"
    return refs[0].ref


class TestEveryEditionIsWorthComparing:
    def test_both_the_api_and_the_bundle_are_offered(self, acts_8_4, monkeypatch) -> None:
        monkeypatch.setattr(sub, "fetch_verse", lambda ref, locale: ACTS_8_4_PARAPHRASE)
        candidates = canonical_candidates_for_source(acts_8_4, "ru")
        assert ACTS_8_4_PARAPHRASE in candidates
        assert any("благовествовали" in c for c in candidates), (
            "the bundled Synodal text is what the authors actually quote"
        )

    def test_one_edition_is_not_repeated(self, acts_8_4, monkeypatch) -> None:
        # If the API happens to serve the same text as the bundle, it is
        # one candidate, not two.
        monkeypatch.setattr(sub, "fetch_verse", lambda ref, locale: ACTS_8_4_SYNODAL)
        candidates = canonical_candidates_for_source(acts_8_4, "ru")
        assert len(candidates) == len(set(candidates))

    def test_a_locale_without_an_api_edition_still_answers(self, acts_8_4) -> None:
        assert canonical_candidates_for_source(acts_8_4, "en"), "English is bundled"


class TestASynodalQuoteIsRecognised:
    def test_even_when_the_api_serves_a_different_edition(self, monkeypatch) -> None:
        # The exact production shape: the API answers, its answer is a
        # paraphrase, and the author quoted the Synodal text.
        monkeypatch.setattr(sub, "fetch_verse", lambda ref, locale: ACTS_8_4_PARAPHRASE)
        _, subs = pre_substitute("«Рассеявшиеся ходили и благовествовали слово» (Деян. 8:4)", "ru")
        assert subs, "asking the API and stopping there missed every Russian quotation"

    def test_a_paraphrase_by_the_author_is_still_left_alone(self, monkeypatch) -> None:
        # The bar has not been lowered — only widened to more editions.
        monkeypatch.setattr(sub, "fetch_verse", lambda ref, locale: ACTS_8_4_PARAPHRASE)
        _, subs = pre_substitute("«Апостолы решили идти в Самарию» (Деян. 8:4)", "ru")
        assert subs == []

    def test_nothing_is_claimed_when_no_edition_is_available(self, monkeypatch) -> None:
        monkeypatch.setattr(sub, "fetch_verse", lambda ref, locale: None)
        monkeypatch.setattr(sub, "lookup", lambda ref, locale: None)
        _, subs = pre_substitute("«Рассеявшиеся ходили и благовествовали слово» (Деян. 8:4)", "ru")
        assert subs == []
