"""A verse arriving in the language the reader did not ask for.

    In Hiob 1,1 heißt es: „There was a man in the land of Uz, whose name
    was Job.“ Dieser Vers identifiziert Hiob direkt als Subjekt.

Sixteen live rows read like that on 2026-08-22, and were stored as good
translations. When the canonical text of a quoted verse cannot be had
for the target language, ``post_substitute`` puts back the author's own
quotation — which is in the author's language — and that fallback is
right when it is the only answer there is. That day it was not: the
YouVersion API was answering 429, the key is shared between production
and anything run by hand, and a burst of manual lookups had exhausted
the quota. The right answer existed and would have arrived on the next
pass.

Nothing structural could see it. The text sent and the text returned
both look complete, because they are — every word is there, just not
every word in one language. Eleven of the twenty-seven rows tripped
``untranslated_run`` and were parked; the other sixteen carried an
English run too short to move a whole-document verdict, and the shortest
of them tripped nothing at all.

So the provider says so, the way it already says ``lost_scripture``. And
it says it only for the transient kind: a verse this edition will never
carry is the case the fallback was written for, and holding a row back
forever over it would serve nobody. ``absence_is_remembered`` draws that
line off the cache — a 404 is remembered, a 429 deliberately is not —
without asking a service that is already refusing to answer.
"""

from __future__ import annotations

import pytest

from app.services.bible import api_source
from app.services.bible.api_source import absence_is_remembered
from app.services.bible.references import BibleRef
from app.services.translation.executor import TranslationTask, _issues_in
from app.services.translation.protocol import TranslationResult

_JOB = BibleRef(book="job", chapter=1, verse_start=1, verse_end=1)


@pytest.fixture(autouse=True)
def _a_key_and_an_empty_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """The state production is in: a key configured, nothing cached yet."""
    monkeypatch.setenv("YOUVERSION_API_KEY", "not-a-real-key")
    monkeypatch.setattr(api_source, "_cache", {})


class TestTellingTheTwoEmptyAnswersApart:
    def test_a_verse_nobody_has_asked_about_is_not_a_remembered_absence(self) -> None:
        """Nothing in the cache means nothing is known — which is the
        state a 429 leaves behind, because ``fetch_verse`` refuses to
        remember one."""
        assert absence_is_remembered(_JOB, "de") is False

    def test_a_publisher_that_answered_404_is_remembered(self) -> None:
        """A verse this edition genuinely does not carry — a
        versification difference — is data, and ``fetch_verse`` caches
        it. Asking again would tell us the same thing tomorrow."""
        api_source._cache[("de", "JOB.1.1-1")] = None
        assert absence_is_remembered(_JOB, "de") is True

    def test_a_verse_we_have_is_not_an_absence_at_all(self) -> None:
        api_source._cache[("de", "JOB.1.1-1")] = "Es war ein Mann im Land Us…"
        assert absence_is_remembered(_JOB, "de") is False

    def test_a_language_with_no_edition_configured_is_permanent(self) -> None:
        """Nothing is coming for a language the table has no id for, so a
        row must not be held back waiting for it."""
        assert absence_is_remembered(_JOB, "fr") is True

    def test_no_key_configured_is_permanent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CI, preview and local development have no key. Every verse
        falls back there, always, and that is not a defect to park a row
        over."""
        monkeypatch.delenv("YOUVERSION_API_KEY", raising=False)
        assert absence_is_remembered(_JOB, "de") is True

    def test_a_psalm_asks_the_edition_under_its_own_number(self) -> None:
        """Psalm 51:1 reaches the Russian edition as Psalm 50:3 — the
        chapter moves because Russian follows the Septuagint, and the
        verse moves because that edition numbers the psalm's heading.
        Both shifts are in the cache key, so this has to remap before it
        looks; asking under the reference's own number would read every
        psalm as never asked about.

        (No psalm currently has *no* honest mapping — checked across all
        150 in all three languages — so the ``remap_psalm is None`` arm
        is unreachable today and is there for an edition that splits one.)
        """
        psalm = BibleRef(book="psalms", chapter=51, verse_start=1, verse_end=1)
        assert absence_is_remembered(psalm, "ru") is False
        api_source._cache[("ru", "PSA.51.1-1")] = None
        assert absence_is_remembered(psalm, "ru") is False, "that is a key nobody will ever ask under"
        api_source._cache[("ru", "PSA.50.3-3")] = None
        assert absence_is_remembered(psalm, "ru") is True


class TestTheRowIsHeldBack:
    def _task(self) -> TranslationTask:
        return TranslationTask(
            entity_type="daily_challenge_question",
            entity_id="1",
            field="explanation",
            source_locale="en",
            target_locale="de",
            text='In Job 1:1, it states, "There was a man in the land of Uz, whose name was Job."',
            content_kind="plain",
            source_hash="hash",
        )

    def test_the_live_row_is_named_and_blocks(self) -> None:
        """The row exactly as production carried it. Nothing else about
        it is wrong — which is the whole difficulty."""
        result = TranslationResult(
            text="In Hiob 1,1 heißt es: „There was a man in the land of Uz, whose name was Job.“",
            input_tokens=1,
            output_tokens=1,
            scripture_in_source_language=True,
        )
        named = [i for i in _issues_in(self._task(), result) if i.code == "scripture_in_source_language"]
        assert named, "the provider said so and the executor has to act on it"
        assert named[0].blocking is True

    def test_the_same_row_without_the_flag_is_not_named(self) -> None:
        """A German verse in German prose. The flag is the only thing
        that separates the two, because the shapes are identical."""
        result = TranslationResult(
            text="In Hiob 1,1 heißt es: „Es war ein Mann im Land Us, der hieß Hiob.“",
            input_tokens=1,
            output_tokens=1,
        )
        assert [i for i in _issues_in(self._task(), result) if i.code == "scripture_in_source_language"] == []
