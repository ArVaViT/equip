# ruff: noqa: RUF001
"""TDD spec for course-creation source-locale resolution.

Today (broken): the API derives ``courses.source_locale`` from
``teacher.preferred_locale``. A teacher with an English UI who
authors a Russian course ends up with ``source_locale='en'``, the
translation pipeline thinks the course is already in English, and
Russian students see the English column (which actually contains
Russian text) while English students see Russian text labelled as
English.

This file defines the contract that replaces that shortcut:
``source_locale`` is derived from the actual content (title +
description), with the teacher's UI locale as a fallback only when
detection has no signal.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.schemas.course import CourseCreate, CourseUpdate
from app.services.course_service._courses import create_course, update_course
from tests.conftest import test_engine  # type: ignore[attr-defined]


@pytest.fixture
def db():
    session = Session(bind=test_engine)
    try:
        yield session
    finally:
        session.close()


def _make_teacher(db: Session, preferred_locale: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"teacher-{uuid.uuid4()}@test",
        full_name="Test Teacher",
        role=UserRole.TEACHER.value,
        preferred_locale=preferred_locale,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _create(
    db: Session,
    teacher: User,
    *,
    title: str,
    description: str | None = None,
) -> object:
    """Mirror the production API-layer call that derives ``source_locale``
    from the teacher's profile. Test must drive the SAME flow the
    route uses so the contract covers the real production path."""
    return create_course(
        db,
        CourseCreate(title=title, description=description),
        user_id=teacher.id,
        source_locale=teacher.preferred_locale,
    )


class TestCreateCourseDetectsRussianContent:
    """The bug Vadym reported."""

    def test_en_ui_teacher_writing_russian_title_gets_ru_source_locale(self, db):
        teacher = _make_teacher(db, preferred_locale="en")
        course = _create(db, teacher, title="Книга Бытия")
        assert course.source_locale == "ru", (
            "An EN-UI teacher who types a Russian title should get a "
            "Russian-sourced course, not 'en'. Otherwise the translation "
            "pipeline never produces an English version for English students."
        )

    def test_en_ui_teacher_writing_russian_description_gets_ru(self, db):
        teacher = _make_teacher(db, preferred_locale="en")
        course = _create(
            db,
            teacher,
            title="Genesis",  # English title, too short for detection
            description="Изучаем первую книгу Библии вместе с группой",
        )
        # Title alone is ambiguous, but description tips Russian.
        assert course.source_locale == "ru"

    def test_real_bug_case_тайтл_detected_as_ru(self, db):
        """The exact data from the production incident:
        title=``Тайтл``, description=``Кто-то что-то сказал``.
        Both Cyrillic, must resolve to ``ru``."""
        teacher = _make_teacher(db, preferred_locale="en")
        course = _create(db, teacher, title="Тайтл", description="Кто-то что-то сказал")
        assert course.source_locale == "ru"


class TestCreateCourseDetectsEnglishContent:
    """Symmetric case: RU-UI teacher writing English content."""

    def test_ru_ui_teacher_writing_english_title_gets_en_source_locale(self, db):
        teacher = _make_teacher(db, preferred_locale="ru")
        course = _create(
            db,
            teacher,
            title="Book of Genesis: A Study Guide",
        )
        assert course.source_locale == "en"


class TestCreateCourseFallbackToUiLocale:
    """When the detector has no signal, fall back to teacher's UI
    locale — this preserves the current behaviour for empty or
    too-short titles so no test fixture breaks unexpectedly."""

    def test_empty_title_falls_back_to_en_for_en_teacher(self, db):
        teacher = _make_teacher(db, preferred_locale="en")
        course = _create(db, teacher, title="X")  # below threshold
        assert course.source_locale == "en"

    def test_empty_title_falls_back_to_ru_for_ru_teacher(self, db):
        teacher = _make_teacher(db, preferred_locale="ru")
        course = _create(db, teacher, title="!")  # punctuation only
        assert course.source_locale == "ru"

    def test_short_ambiguous_title_no_description_falls_back(self, db):
        teacher = _make_teacher(db, preferred_locale="en")
        course = _create(db, teacher, title="Hi", description=None)
        assert course.source_locale == "en"


class TestCreateCourseMatchingLanguage:
    """No-drift cases: when teacher UI and content match, the result
    is identical to today's behaviour — no regression risk."""

    def test_en_ui_teacher_writing_english_course_stays_en(self, db):
        teacher = _make_teacher(db, preferred_locale="en")
        course = _create(
            db,
            teacher,
            title="The Book of Genesis: An Introduction",
            description="A study guide for the first book of the Bible.",
        )
        assert course.source_locale == "en"

    def test_ru_ui_teacher_writing_russian_course_stays_ru(self, db):
        teacher = _make_teacher(db, preferred_locale="ru")
        course = _create(
            db,
            teacher,
            title="Книга Бытия: Введение",
            description="Учебное руководство по первой книге Библии.",
        )
        assert course.source_locale == "ru"


class TestUpdateCourseReDetects:
    """If a teacher rewrites the title in a different language after
    creation, the source_locale must update — otherwise the original
    miscategorisation lingers forever."""

    def test_rewriting_title_to_different_language_updates_source_locale(self, db):
        teacher = _make_teacher(db, preferred_locale="en")
        course = _create(db, teacher, title="Hello English course")
        assert course.source_locale == "en"
        update_course(db, course, CourseUpdate(title="Книга Бытия: курс на русском"))
        db.refresh(course)
        assert course.source_locale == "ru"

    def test_rewriting_title_to_same_language_keeps_source_locale(self, db):
        teacher = _make_teacher(db, preferred_locale="en")
        course = _create(db, teacher, title="Книга Бытия: введение")
        assert course.source_locale == "ru"
        update_course(db, course, CourseUpdate(title="Книга Бытия: пересмотренное издание"))
        db.refresh(course)
        assert course.source_locale == "ru"

    def test_update_without_title_change_does_not_touch_source_locale(self, db):
        """A PATCH that doesn't touch title/description (e.g. just
        changes the cover image) must not re-detect — the existing
        ``source_locale`` is authoritative."""
        teacher = _make_teacher(db, preferred_locale="en")
        course = _create(db, teacher, title="Genesis")  # too short → falls back to en
        # Manually pin source_locale to something other than the
        # would-be detection result; an unrelated update must not
        # rewrite it.
        course.source_locale = "ru"
        db.commit()
        update_course(db, course, CourseUpdate(image_url="https://example.com/cover.png"))
        db.refresh(course)
        assert course.source_locale == "ru"
