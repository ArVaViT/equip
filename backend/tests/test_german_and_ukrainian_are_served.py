# ruff: noqa: RUF001
# Four languages of sample text, two of them Cyrillic. Letters that
# look like Latin ones are the subject matter here.
"""German and Ukrainian are languages this platform serves.

Not "supported in the codebase" — served: a person can have German as
their language, a teacher can write a course in Ukrainian, the pipeline
translates into both, and a course does not reach the catalog until it
has them.

These tests read the live ``LOCALE_CODES`` on purpose. Most of the
translation suites pin themselves to the two-locale set so their
arithmetic keeps meaning what it meant; this file is the one that has
to fail if a language is quietly dropped.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.core.i18n import catalog_keys, t
from app.models.course import Course
from app.models.user import User
from app.schemas.locale import LOCALE_CODES, LOCALE_DISPLAY_NAMES, normalize_locale
from app.services.content_versions import record_human_version
from app.services.language_detection import detect_locale
from app.services.translation.completeness import course_translation_completeness
from app.services.translation.orchestrator import other_locales
from app.services.translation.service import reset_translation_provider_cache
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

EXPECTED = ("ru", "en", "de", "uk")


class TestTheSupportedSet:
    def test_all_four_are_served(self):
        assert LOCALE_CODES == EXPECTED

    def test_each_has_a_name_the_model_is_addressed_by(self):
        # The translation prompt says "translate from Russian to
        # German"; a missing entry would send the model a locale code.
        assert set(LOCALE_DISPLAY_NAMES) == set(EXPECTED)
        assert LOCALE_DISPLAY_NAMES["de"] == "German"
        assert LOCALE_DISPLAY_NAMES["uk"] == "Ukrainian"

    @pytest.mark.parametrize("code", EXPECTED)
    def test_the_backend_catalog_speaks_every_language(self, code: str):
        # Notification and email text is written server-side, in the
        # recipient's language, before the frontend ever sees it.
        #
        # Placeholders are filled from the string itself rather than from a
        # fixed list: a key that introduces a new one should fail this test
        # for being untranslated, never for being unexpected.
        import re

        from app.core.i18n import _CATALOG

        for key in catalog_keys():
            template = _CATALOG[code].get(key) or _CATALOG["en"][key]
            args = {name: "x" for name in re.findall(r"\{(\w+)\}", template)}
            rendered = t(code, key, **args)
            assert rendered != key, f"{code} is missing {key}"
            assert "{" not in rendered, f"{code}:{key} left a placeholder unfilled"

    @pytest.mark.parametrize(
        "header,expected",
        [
            ("de", "de"),
            ("de-DE", "de"),
            ("de-AT,de;q=0.9", "de"),
            ("uk", "uk"),
            ("uk-UA", "uk"),
            # A language we do not serve is answered in English, not in
            # Russian — and it is answered, rather than 500ing.
            ("fr", "en"),
        ],
    )
    def test_accept_language_resolves(self, header: str, expected: str):
        assert normalize_locale(header) == expected


class TestTranslationTargets:
    @pytest.mark.parametrize(
        "source,targets",
        [
            ("ru", {"en", "de", "uk"}),
            ("de", {"ru", "en", "uk"}),
            ("uk", {"ru", "en", "de"}),
        ],
    )
    def test_every_other_language_is_a_target(self, source: str, targets: set[str]):
        assert set(other_locales(source)) == targets


class TestDetection:
    """The detector decides what language a teacher actually wrote in.
    With four languages it has two same-script pairs to separate."""

    def test_ukrainian_is_not_read_as_russian(self):
        assert detect_locale("Вивчаємо першу книгу Біблії разом") == "uk"

    def test_russian_is_not_read_as_ukrainian(self):
        assert detect_locale("Изучаем первую книгу Библии вместе") == "ru"

    def test_german_is_not_read_as_english(self):
        assert detect_locale("Wir lesen das erste Buch der Bibel zusammen") == "de"

    def test_english_is_still_english(self):
        assert detect_locale("Studying the first book of the Bible together") == "en"


class TestPublication:
    @pytest.fixture(autouse=True)
    def _translation_enabled(self, monkeypatch: pytest.MonkeyPatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "GEMINI_API_KEY", SecretStr("test-key"), raising=False)
        reset_translation_provider_cache()
        yield
        reset_translation_provider_cache()

    def test_a_course_waits_for_german_and_ukrainian_too(self, db: Session):
        if db.get(User, TEACHER_ID) is None:
            db.add(User(id=TEACHER_ID, email="teacher@example.com", role="teacher"))
            db.commit()
        course = Course(
            id=str(uuid.uuid4()),
            title="Курс о Деяниях",
            created_by=TEACHER_ID,
            status="published",
            source_locale="ru",
        )
        db.add(course)
        db.commit()
        record_human_version(
            db,
            entity_type="course",
            entity_id=str(course.id),
            field="title",
            locale="ru",
            text="Курс о Деяниях",
        )
        db.commit()

        completeness = course_translation_completeness(db, course)

        assert not completeness.is_complete
        # Three languages to fill, not one. Before this, a course was
        # "complete" the moment English existed.
        assert set(completeness.by_locale()) == {"en", "de", "uk"}
