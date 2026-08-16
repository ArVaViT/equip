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

from app.models.chapter_block import ChapterBlock
from app.models.course import Chapter, Course, Module
from app.models.user import User, UserRole
from app.services.content_versions.write import record_human_version
from app.services.translation.resolve_for_display import (
    build_localized_course_response_with_tree,
    build_localized_course_summaries,
    localize_chapter_block_rows,
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


class TestTheLessonBody:
    """The longest thing anybody reads, and the last place the spare
    language was still living.

    ``localize_chapter_block_rows`` resolved display → source → any
    locale, unconditionally. So a German student opening a Russian
    lesson got the entire lesson in Russian — while every title around
    it correctly said the course was not available in German.
    """

    def _block(self, db: Session, course: Course) -> ChapterBlock:
        module = db.query(Module).filter(Module.course_id == course.id).one()
        chapter = Chapter(id=str(uuid.uuid4()), module_id=module.id, title="Урок 1", order_index=0)
        db.add(chapter)
        db.flush()
        block = ChapterBlock(id=uuid.uuid4(), chapter_id=chapter.id, block_type="text", order_index=0)
        db.add(block)
        db.flush()
        record_human_version(
            db,
            entity_type="chapter_block",
            entity_id=str(block.id),
            field="content",
            locale="ru",
            text="<p>Пётр встал среди братьев и сказал.</p>",
            authored_by=course.created_by,
        )
        db.commit()
        return block

    def test_a_german_reader_gets_nothing_rather_than_russian(self, db: Session):
        course = _russian_course(db)
        block = self._block(db, course)

        rows = localize_chapter_block_rows(db, [block], display_locale="de", source_locale="ru")

        assert rows[0].content in (None, ""), f"served the Russian lesson to a German reader: {rows[0].content!r}"

    def test_the_russian_reader_gets_the_lesson(self, db: Session):
        course = _russian_course(db)
        block = self._block(db, course)

        rows = localize_chapter_block_rows(db, [block], display_locale="ru", source_locale="ru")

        assert "Пётр" in (rows[0].content or "")

    def test_the_editor_still_sees_their_own_lesson(self, db: Session):
        # A teacher editing their Russian course in a German UI must see
        # what they wrote. Hiding their own material from them would be
        # a different kind of broken.
        course = _russian_course(db)
        block = self._block(db, course)

        rows = localize_chapter_block_rows(
            db,
            [block],
            display_locale="de",
            source_locale="ru",
            fallback="source_then_any",
        )

        assert "Пётр" in (rows[0].content or "")


class TestTheCatalogCard:
    """Module titles ride inside every catalog card, and nobody had
    localized them: they come off the ORM, hydrated at the course's own
    language. So an English catalog carried "Модуль 1…" inside every
    card, and so did the German and Ukrainian ones.

    Found by reading a live production response, not by reading the
    code — which is the point of the audit script this test came from.
    """

    def test_a_module_title_is_not_smuggled_in_in_the_authors_language(self, db: Session):
        course = _russian_course(db)

        summaries = build_localized_course_summaries(db, [course], "de")

        assert [m.title for m in summaries[0].modules] == [""]

    def test_and_it_is_there_for_the_reader_who_has_it(self, db: Session):
        course = _russian_course(db)

        summaries = build_localized_course_summaries(db, [course], "ru")

        assert [m.title for m in summaries[0].modules] == ["Модуль 1. Введение"]
