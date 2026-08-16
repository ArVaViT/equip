"""What a German reader gets from a course that has never been translated.

Not Russian. That is the whole rule, and it was being broken on the
most-visited page on the platform.

``pick_overlay_value`` was doing its job: no German row, so ``None``,
so the caller decides. Every caller decided with ``or mod.title`` — the
source column, in the author's language. A German reader opening a
Russian course got the course title, every module name and every lesson
name in Russian, and nothing anywhere said the course was not available
in their language.

Two shapes of the same failure:

* the detail page served another language;
* the catalog crashed, because the read schema required a title of at
  least one character and an untranslated course resolves to ``""``.
  Every German and Ukrainian visitor got a 500 on ``GET /courses``.

The empty string is the honest answer. The web app already renders it
as "not translated yet" (``orNotTranslated``), which is what a reader
should see when the platform has nothing for them.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.course import Course, Module
from app.models.user import User, UserRole
from app.services.content_versions.write import record_human_version
from app.services.translation.resolve_for_display import (
    build_localized_course_response_with_tree,
    build_localized_course_summaries,
    populate_spine_texts,
)
from app.services.translation.service import reset_translation_provider_cache

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def _translation_is_configured(monkeypatch: pytest.MonkeyPatch):
    """The rule only exists where the platform translates. On a deploy
    with no provider there is one language and serving it is right."""
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()
    yield
    reset_translation_provider_cache()


def _russian_course(db: Session) -> Course:
    """A course as production has them: Russian, with no German anywhere."""
    teacher = User(
        id=uuid.uuid4(),
        email=f"t-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Автор",
        role=UserRole.TEACHER.value,
        preferred_locale="ru",
    )
    db.add(teacher)
    db.flush()
    course = Course(
        id=f"course-{uuid.uuid4().hex[:8]}",
        created_by=teacher.id,
        status="published",
        source_locale="ru",
    )
    db.add(course)
    db.flush()
    record_human_version(
        db,
        entity_type="course",
        entity_id=course.id,
        field="title",
        locale="ru",
        text="Книга Деяний Апостолов",
        authored_by=teacher.id,
    )
    module = Module(id=str(uuid.uuid4()), course_id=course.id, order_index=0)
    db.add(module)
    db.flush()
    record_human_version(
        db,
        entity_type="module",
        entity_id=str(module.id),
        field="title",
        locale="ru",
        text="Модуль 1. Введение",
        authored_by=teacher.id,
    )
    db.commit()
    db.refresh(course)
    # What ``get_course`` does before the route builds a response: fills
    # the runtime title attributes from cv at the course's own language.
    # It is the value the reader path used to fall back to.
    populate_spine_texts(db, [course])
    return course


class TestTheDetailPage:
    def test_a_german_reader_is_not_handed_russian(self, db: Session):
        course = _russian_course(db)

        response = build_localized_course_response_with_tree(db, course, "de")

        assert response.title == "", f"served the Russian title to a German reader: {response.title!r}"

    def test_the_modules_are_not_handed_over_either(self, db: Session):
        course = _russian_course(db)

        response = build_localized_course_response_with_tree(db, course, "de")

        assert [m.title for m in response.modules] == [""]

    def test_the_reader_whose_language_it_is_still_gets_it(self, db: Session):
        course = _russian_course(db)

        response = build_localized_course_response_with_tree(db, course, "ru")

        assert response.title == "Книга Деяний Апостолов"


class TestTheCatalog:
    def test_it_does_not_crash_on_a_course_with_no_title_here(self, db: Session):
        # The 500 every German visitor got: the read schema required a
        # title of at least one character, and an untranslated course
        # has none.
        course = _russian_course(db)

        summaries = build_localized_course_summaries(db, [course], "de")

        assert len(summaries) == 1
        assert summaries[0].title == ""

    def test_and_still_shows_the_course_to_its_own_readers(self, db: Session):
        course = _russian_course(db)

        summaries = build_localized_course_summaries(db, [course], "ru")

        assert summaries[0].title == "Книга Деяний Апостолов"
