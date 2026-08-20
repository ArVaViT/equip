"""A phrase in quotes is prose, not Scripture.

Rule 2 of the system prompt tells the model to leave a quoted verse
alone — it arrives as an EQV token and the canonical target-language
text is restored afterwards. The model generalised that to anything
inside quotation marks, and a Bible-study course discusses words for a
living: half its questions open with an idiom in quotes.

Production stopped on «Злачное место» in the shepherd psalm. Asked for
German, the model returned the Russian sentence untouched; asked without
the quotation marks, the same model produced "Was bedeutet 'grüne Auen'
im Psalm vom Hirten?" — the right answer, blocked by punctuation.

The second half of this file covers what the model did when it half
complied: it answered twice, source first, then the fence markers it had
been given, then the actual translation.
"""

from __future__ import annotations

from app.services.translation.gemini import GeminiTranslationProvider
from app.services.translation.prompt import build_system_prompt


class TestThePromptSaysItPlainly:
    def test_quotes_are_named_as_translatable(self) -> None:
        prompt = build_system_prompt(source_locale="ru", target_locale="de")
        assert "Quotation marks do not mean do-not-translate" in prompt

    def test_only_the_token_is_untouchable(self) -> None:
        prompt = build_system_prompt(source_locale="ru", target_locale="de")
        assert "Only an EQV" in prompt

    def test_an_idiom_is_never_spelled_out_in_the_target_alphabet(self) -> None:
        # The specific trap: production carried "Zlatschnoje mesto" —
        # a Russian idiom written in German letters, with an invented
        # etymology beside it. A reader who does not know Russian learns
        # nothing from its sounds.
        #
        # The rule deliberately stops there and does NOT tell the model
        # to substitute the wording of a German Bible: an earlier version
        # did, and it contradicted the rule two lines below, which says
        # to translate a quoted passage literally rather than recite an
        # edition from memory. Reciting is what #990 was about.
        prompt = build_system_prompt(source_locale="ru", target_locale="de")
        assert "never spell it out in German letters" in prompt
        assert "do not recite a German Bible from memory" in prompt


class TestAReplyThatRepeatedTheQuestion:
    def test_the_translation_is_taken_out_of_it(self) -> None:
        echoed = (
            "«Злачное место» в псалме про пастыря означает:\n"
            "===BEGIN_48ea127f66c6755d===\n"
            "„Grüne Auen“ im Psalm vom Hirten bedeutet:\n"
            "===END_48ea127f66c6755d==="
        )
        assert GeminiTranslationProvider._unwrap_echoed_fence(echoed) == "„Grüne Auen“ im Psalm vom Hirten bedeutet:"

    def test_an_ordinary_reply_is_untouched(self) -> None:
        plain = "Paulus schreibt an die Gemeinde in Korinth."
        assert GeminiTranslationProvider._unwrap_echoed_fence(plain) == plain

    def test_a_reply_that_is_only_scaffolding_is_left_to_fail(self) -> None:
        # Unwrapping must not manufacture a translation out of nothing —
        # the structural check has to still see something wrong.
        only_fence = "===BEGIN_48ea127f66c6755d===\n===END_48ea127f66c6755d==="
        assert "===" in GeminiTranslationProvider._unwrap_echoed_fence(only_fence)

    def test_markup_inside_the_answer_survives(self) -> None:
        echoed = "source text\n===BEGIN_aaaa===\n<p>Der <strong>Bund</strong> mit Abraham.</p>\n===END_aaaa==="
        assert GeminiTranslationProvider._unwrap_echoed_fence(echoed) == "<p>Der <strong>Bund</strong> mit Abraham.</p>"
