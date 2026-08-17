"""TDD spec: per-entity source-language detection.

After PR #526 (course-level detection) and PR #527 (purge on locale
flip), the next bilingual gap is per-entity drift: a teacher writing
inside a RU-source course can author one chapter in English (or vice
versa). The pipeline today reads ``course.source_locale`` for every
nested entity, mistranslates the off-language ones, and the resolve
path serves the wrong language to students.

Spec:
  * Pipeline: each ``reconcile_entity`` call detects the actual
    language of EACH text field and uses that — not the course's
    declared source — as the translation source. Fields with no
    detection signal fall back to the course's source_locale.
  * Resolve: the display path detects the language of an entity's
    base text per field; when display_locale matches the detected
    source, return the base text (no overlay lookup); otherwise
    serve the overlay.

Tests written BEFORE implementation — RED first commit.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.models.course import Chapter, Course, Module
from app.models.user import User, UserRole
from app.services.translation.registry import reconcile_entity
from app.services.translation.service import reset_translation_provider_cache

# These tests count rows and provider calls, so the size of the
# supported set is one of their inputs. They describe the "ru" + "en"
# set they were written against; the wider set has tests of its own.
pytestmark = pytest.mark.usefixtures("two_locales")
TEACHER_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


@pytest.fixture
def db():
    from tests.conftest import test_engine

    session = Session(bind=test_engine)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    """Enable the translation provider for these tests; mirrors the
    existing pattern from ``test_translation_orchestrator.py``."""
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()
    yield
    reset_translation_provider_cache()


def _make_teacher(db: Session) -> User:
    existing = db.query(User).filter(User.id == TEACHER_ID).first()
    if existing:
        return existing
    user = User(
        id=TEACHER_ID,
        email=f"per-entity-{uuid.uuid4()}@test",
        full_name="Test Teacher",
        role=UserRole.TEACHER.value,
        preferred_locale="en",
    )
    db.add(user)
    db.commit()
    return user


def _make_course(db: Session, **overrides: Any) -> Course:
    _make_teacher(db)
    defaults = {
        "id": str(uuid.uuid4()),
        "title": "RU course default title",
        "description": "RU course default description",
        "status": "published",
        "source_locale": "ru",
        "created_by": TEACHER_ID,
    }
    defaults.update(overrides)
    course = Course(**defaults)
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _make_chapter(db: Session, course: Course, *, title: str) -> Chapter:
    module = Module(
        id=str(uuid.uuid4()),
        course_id=course.id,
        title="Some module",
        order_index=0,
    )
    db.add(module)
    db.flush()
    chapter = Chapter(
        id=str(uuid.uuid4()),
        module_id=module.id,
        title=title,
        order_index=0,
        chapter_type="reading",
    )
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter


class _RecordingProvider:
    """Records the locale arguments each translate call was given, so
    the test can assert which direction the orchestrator picked."""

    name = "recording"

    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def translate(self, request):
        self.calls.append(
            {
                "text": request.text,
                "source_locale": request.source_locale,
                "target_locale": request.target_locale,
                "content_kind": request.content_kind,
            }
        )
        from app.services.translation.protocol import TranslationResult
        from tests._fake_translation import fake_translate

        # Transliterate rather than echo the source with a locale tag.
        # ``f"[en] Введение..."`` is Russian text presented as an English
        # translation — exactly what ``validation.py`` exists to catch —
        # so the orchestrator now (correctly) treats it as a bad answer
        # and asks again, and a test counting provider calls sees two.
        # The shared fake produces something that reads as the language
        # it claims to be, which is what a recording provider should be
        # standing in for.
        return TranslationResult(
            text=fake_translate(request.text, target_locale=request.target_locale),
            model="recording",
        )


class TestReconcileEntityDetectsPerFieldLanguage:
    """When an entity's text is in a different language than its
    course's declared source, the orchestrator must translate FROM
    the entity's actual language to all OTHER supported locales —
    not from the course's declared (and wrong) source."""

    def test_english_chapter_in_russian_course_translates_en_to_ru(self, db: Session):
        course = _make_course(db, source_locale="ru")
        chapter = _make_chapter(db, course, title="Welcome to the chapter on Genesis")
        provider = _RecordingProvider()

        reconcile_entity(db, "chapter", chapter, provider=provider)

        # The chapter title is English. Pipeline should detect EN and
        # translate to RU (the "other" locale relative to EN), NOT to
        # EN (which would be the "other" relative to the course's
        # declared RU).
        assert len(provider.calls) == 1, "Should make one EN→RU call, not RU→EN"
        call = provider.calls[0]
        assert call["source_locale"] == "en"
        assert call["target_locale"] == "ru"

    def test_russian_chapter_in_english_course_translates_ru_to_en(self, db: Session):
        course = _make_course(db, source_locale="en")
        chapter = _make_chapter(db, course, title="Введение в книгу Бытия и её главы")
        provider = _RecordingProvider()

        reconcile_entity(db, "chapter", chapter, provider=provider)

        assert len(provider.calls) == 1
        call = provider.calls[0]
        assert call["source_locale"] == "ru"
        assert call["target_locale"] == "en"

    def test_chapter_in_same_language_as_course_uses_course_source(self, db: Session):
        """No regression for the common case: chapter matches course."""
        course = _make_course(db, source_locale="ru")
        chapter = _make_chapter(db, course, title="Введение в книгу Бытия и её главы")
        provider = _RecordingProvider()

        reconcile_entity(db, "chapter", chapter, provider=provider)

        # Russian chapter, Russian course → translate RU→EN.
        assert len(provider.calls) == 1
        assert provider.calls[0]["source_locale"] == "ru"
        assert provider.calls[0]["target_locale"] == "en"

    def test_chapter_with_unintelligible_title_falls_back_to_course_source(self, db: Session):
        """Too short / no signal: fall back to course.source_locale.
        Otherwise a 2-letter title silently flips translation direction."""
        course = _make_course(db, source_locale="ru")
        chapter = _make_chapter(db, course, title="X")  # below detector threshold
        provider = _RecordingProvider()

        reconcile_entity(db, "chapter", chapter, provider=provider)

        assert len(provider.calls) == 1
        # Fall back to course source (ru) → translate to other locale (en).
        assert provider.calls[0]["source_locale"] == "ru"
        assert provider.calls[0]["target_locale"] == "en"


class TestReconcileEntityHandlesMixedFieldLanguages:
    """An entity can have title in one language and description in
    another (e.g. a Russian course with an English announcement that
    accidentally has a Russian subtitle). Each field is detected
    independently — the orchestrator's per-field translate call uses
    each field's own detected source."""

    def test_module_with_mixed_field_languages_translates_each_separately(self, db: Session):
        course = _make_course(db, source_locale="ru")
        module = Module(
            id=str(uuid.uuid4()),
            course_id=course.id,
            title="Module 1: Introduction to Genesis",  # English
            description="Описание модуля на русском языке",  # Russian
            order_index=0,
        )
        db.add(module)
        db.commit()
        db.refresh(module)
        provider = _RecordingProvider()

        reconcile_entity(db, "module", module, provider=provider)

        # Two calls — one per field, each with its own detected source.
        assert len(provider.calls) == 2
        title_call = next(c for c in provider.calls if "Genesis" in c["text"])
        desc_call = next(c for c in provider.calls if "Описание" in c["text"])

        assert title_call["source_locale"] == "en"
        assert title_call["target_locale"] == "ru"

        assert desc_call["source_locale"] == "ru"
        assert desc_call["target_locale"] == "en"
