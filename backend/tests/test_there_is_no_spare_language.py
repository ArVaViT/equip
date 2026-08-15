"""Nobody is served a language they did not choose.

Vadym's first rule for the multilingual platform, stated as he stated
it: there is no principal language and no spare one; what a person sees
follows from what they chose. Serving another language quietly is not a
kindness — it decides for the reader that some language beats nothing,
and it decides it without telling them.

Until now the resolve path ended in ``overlay.get(key, base)``: no
translation for your locale meant you got the teacher's original. A
Ukrainian student opening a lesson would find Russian and nothing to
say the platform simply had not translated it yet.

What replaces it is not a blank page. ``None`` means "not in your
language", and the surface above says so. And it is a narrow state:
under the publication gate a course cannot enter the catalog until
every language has it, so a reader meets this only in the gap between
a teacher posting something and the worker translating it.

The one thing still served as-is: text the detector cannot assign a
language to at all — "OK", "2026", a proper name. That is the same
string in every language, not a foreign one being substituted.
"""

from __future__ import annotations

import pytest

from app.services.translation.resolve_for_display import pick_overlay_value

KEY = ("chapter", "ch-1", "title")


@pytest.fixture(autouse=True)
def _translation_enabled(monkeypatch: pytest.MonkeyPatch):
    """The rule is about a platform that translates.

    Where no provider is configured there is only one language, and
    serving the text that exists is not substituting a language for the
    reader's — so the resolver keeps the old behaviour there, and these
    tests would describe that instead of what they mean to.
    """
    from pydantic import SecretStr

    from app.core.config import settings
    from app.services.translation.service import reset_translation_provider_cache

    monkeypatch.setattr(settings, "GEMINI_API_KEY", SecretStr("test-key"), raising=False)
    reset_translation_provider_cache()
    yield
    reset_translation_provider_cache()


def _pick(
    base: str | None,
    *,
    source_locale: str = "ru",
    display_locale: str = "uk",
    overlay: dict[tuple[str, str, str], str] | None = None,
) -> str | None:
    return pick_overlay_value(
        overlay or {},
        KEY[0],
        KEY[1],
        KEY[2],
        base,
        source_locale=source_locale,  # type: ignore[arg-type]
        display_locale=display_locale,  # type: ignore[arg-type]
    )


class TestUntranslatedIsNotSubstituted:
    def test_a_ukrainian_reader_is_not_handed_russian(self):
        assert _pick("Апостол Павел написал это послание", display_locale="uk") is None

    def test_a_german_reader_is_not_handed_english(self):
        assert (
            _pick(
                "The apostle Paul wrote this letter",
                source_locale="en",
                display_locale="de",
            )
            is None
        )

    def test_a_russian_reader_is_not_handed_ukrainian(self):
        assert (
            _pick(
                "Апостол Павло написав це послання",
                source_locale="uk",
                display_locale="ru",
            )
            is None
        )

    @pytest.mark.parametrize("display", ["en", "de", "uk"])
    def test_the_rule_holds_for_every_language(self, display: str):
        assert _pick("Изучаем первую книгу Библии вместе", display_locale=display) is None


class TestWhatIsStillServed:
    def test_the_translation_when_there_is_one(self):
        overlay = {KEY: "Вивчаємо книгу Буття"}
        assert _pick("Изучаем книгу Бытия", display_locale="uk", overlay=overlay) == "Вивчаємо книгу Буття"

    def test_the_base_when_it_is_already_in_the_reader_language(self):
        assert _pick("Вивчаємо книгу Буття", source_locale="uk", display_locale="uk") == "Вивчаємо книгу Буття"

    @pytest.mark.parametrize("text", ["OK", "2026", "Genesis 1:1", "Equip"])
    def test_text_that_carries_no_language(self, text: str):
        # Not a foreign language being substituted — the same string in
        # any language. The detector declines to name one, which is the
        # signal this leans on.
        assert _pick(text, display_locale="uk") == text

    def test_nothing_at_all_stays_nothing(self):
        assert _pick(None, display_locale="uk") is None
