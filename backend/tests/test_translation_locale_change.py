# ruff: noqa: RUF001
"""TDD spec: handling a course's ``source_locale`` flip.

The bug this fixes: PR #526 made ``update_course`` re-detect
``source_locale`` from the actual content when the teacher edits
title/description. But the existing ``content_translations`` rows
for the course's entities still target the PREVIOUS source's set of
"other locales", so:

  * Rows for the NEW source locale are now stale and STILL preferred
    over the course's base text (the resolve path treats any
    ``status='ok'`` row as the canonical translation). Student in
    the new source locale sees the old machine translation instead
    of the teacher's new authoritative text.
  * The pipeline's ``source_hash`` short-circuit may re-translate
    field-by-field on the next publish, but the wrong-direction
    rows linger until manually cleared.

Spec: when ``update_course`` flips ``courses.source_locale``, every
``content_translations`` row tied to an entity under that course
must be deleted. The pipeline runs as it does today and repopulates
fresh rows in the new direction.

Tests are written BEFORE the helper exists — first commit is RED.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.models.announcement import Announcement
from app.models.chapter_block import ChapterBlock
from app.models.content_translation import ContentTranslation
from app.models.course import Chapter, Course, Module
from app.models.user import User, UserRole
from app.schemas.course import CourseUpdate
from app.services.course_service._courses import update_course

TEACHER_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


@pytest.fixture
def db():
    from tests.conftest import test_engine

    session = Session(bind=test_engine)
    try:
        yield session
    finally:
        session.close()


def _make_teacher(db: Session) -> User:
    user = User(
        id=TEACHER_ID,
        email=f"locale-change-{uuid.uuid4()}@test",
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
        "title": "Привет курс",  # Russian; source_locale=ru
        "description": "Описание на русском",
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


def _add_module_with_chapter_and_block(
    db: Session, course: Course
) -> tuple[Module, Chapter, ChapterBlock]:
    module = Module(
        id=str(uuid.uuid4()),
        course_id=course.id,
        title="Модуль 1",
        order_index=0,
    )
    db.add(module)
    db.flush()
    chapter = Chapter(
        id=str(uuid.uuid4()),
        module_id=module.id,
        title="Глава 1",
        order_index=0,
        chapter_type="reading",
    )
    db.add(chapter)
    db.flush()
    block = ChapterBlock(
        id=str(uuid.uuid4()),
        chapter_id=chapter.id,
        block_type="text",
        order_index=0,
        content="<p>Содержание блока</p>",
    )
    db.add(block)
    db.commit()
    db.refresh(course)
    return module, chapter, block


def _seed_translation(
    db: Session,
    *,
    entity_type: str,
    entity_id: str,
    field: str,
    locale: str,
    text: str = "translated",
) -> ContentTranslation:
    row = ContentTranslation(
        id=uuid.uuid4(),
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        locale=locale,
        text=text,
        source_hash="placeholder-hash",
        status="ok",
        origin="mt",
    )
    db.add(row)
    db.commit()
    return row


# ----------------------------------------------------------------------------
# The function under test doesn't exist yet — import will fail (RED phase).
# ----------------------------------------------------------------------------
from app.services.translation.course_pipeline import (  # noqa: E402
    purge_course_translations,
)


class TestPurgeCourseTranslationsCoverage:
    """The purge helper must walk the same tree the translation
    pipeline does and delete every row attached to a course-scoped
    entity. Anything it misses leaves a stale row that the resolve
    path will still serve to students.
    """

    def test_purges_course_level_rows(self, db: Session):
        course = _make_course(db)
        _seed_translation(
            db, entity_type="course", entity_id=course.id, field="title", locale="en"
        )
        assert db.query(ContentTranslation).count() == 1
        deleted = purge_course_translations(db, course)
        assert deleted == 1
        assert db.query(ContentTranslation).count() == 0

    def test_purges_module_level_rows(self, db: Session):
        course = _make_course(db)
        module, _chapter, _block = _add_module_with_chapter_and_block(db, course)
        _seed_translation(
            db, entity_type="module", entity_id=str(module.id), field="title", locale="en"
        )
        deleted = purge_course_translations(db, course)
        assert deleted == 1

    def test_purges_chapter_level_rows(self, db: Session):
        course = _make_course(db)
        _module, chapter, _block = _add_module_with_chapter_and_block(db, course)
        _seed_translation(
            db, entity_type="chapter", entity_id=str(chapter.id), field="title", locale="en"
        )
        deleted = purge_course_translations(db, course)
        assert deleted == 1

    def test_purges_chapter_block_rows(self, db: Session):
        course = _make_course(db)
        _module, _chapter, block = _add_module_with_chapter_and_block(db, course)
        _seed_translation(
            db,
            entity_type="chapter_block",
            entity_id=str(block.id),
            field="content",
            locale="en",
        )
        deleted = purge_course_translations(db, course)
        assert deleted == 1

    def test_purges_announcement_rows_tied_to_course(self, db: Session):
        course = _make_course(db)
        ann = Announcement(
            id=str(uuid.uuid4()),
            course_id=course.id,
            title="Объявление",
            content="Текст",
            created_by=TEACHER_ID,
        )
        db.add(ann)
        db.commit()
        _seed_translation(
            db, entity_type="announcement", entity_id=str(ann.id), field="title", locale="en"
        )
        deleted = purge_course_translations(db, course)
        assert deleted == 1

    def test_purges_rows_across_every_entity_type_in_one_call(self, db: Session):
        course = _make_course(db)
        module, chapter, block = _add_module_with_chapter_and_block(db, course)
        ann = Announcement(
            id=str(uuid.uuid4()),
            course_id=course.id,
            title="Объявление",
            content="Текст",
            created_by=TEACHER_ID,
        )
        db.add(ann)
        db.commit()
        for et, eid, field in [
            ("course", course.id, "title"),
            ("course", course.id, "description"),
            ("module", str(module.id), "title"),
            ("chapter", str(chapter.id), "title"),
            ("chapter_block", str(block.id), "content"),
            ("announcement", str(ann.id), "title"),
        ]:
            _seed_translation(db, entity_type=et, entity_id=eid, field=field, locale="en")
        assert db.query(ContentTranslation).count() == 6
        deleted = purge_course_translations(db, course)
        assert deleted == 6
        assert db.query(ContentTranslation).count() == 0


class TestPurgeCourseTranslationsIsolation:
    """Critical: the purge must affect ONLY the course passed in.
    Translations tied to entities under OTHER courses must survive."""

    def test_does_not_touch_other_courses_translations(self, db: Session):
        course_a = _make_course(db, id=str(uuid.uuid4()))
        course_b = _make_course(db, id=str(uuid.uuid4()))
        _seed_translation(
            db, entity_type="course", entity_id=course_a.id, field="title", locale="en"
        )
        _seed_translation(
            db, entity_type="course", entity_id=course_b.id, field="title", locale="en"
        )
        deleted = purge_course_translations(db, course_a)
        assert deleted == 1
        survivor = (
            db.query(ContentTranslation)
            .filter(ContentTranslation.entity_id == course_b.id)
            .one()
        )
        assert survivor is not None

    def test_purges_all_locales_not_just_one(self, db: Session):
        """When source_locale flips, BOTH the new-source-locale row
        (stale because base is now this locale) and the old-source-
        locale row (would only exist if someone manually added it)
        should be cleared. The simplest contract is: purge every row
        for the course's entities, regardless of locale."""
        course = _make_course(db)  # source ru
        # Hypothetical state: two ru rows + two en rows exist
        _seed_translation(
            db, entity_type="course", entity_id=course.id, field="title", locale="en"
        )
        _seed_translation(
            db, entity_type="course", entity_id=course.id, field="title", locale="ru"
        )
        deleted = purge_course_translations(db, course)
        assert deleted == 2

    def test_returns_zero_when_no_translations_exist(self, db: Session):
        course = _make_course(db)
        deleted = purge_course_translations(db, course)
        assert deleted == 0


class TestUpdateCoursePurgesOnSourceLocaleChange:
    """The integration: ``update_course`` should call the purge when
    detection flips ``source_locale``. No purge when nothing changes."""

    def test_locale_change_via_title_rewrite_triggers_purge(self, db: Session):
        course = _make_course(db, source_locale="ru", title="Привет курс")
        _seed_translation(
            db, entity_type="course", entity_id=course.id, field="title", locale="en"
        )
        # Rewrite title to English — detector returns 'en', source_locale flips.
        update_course(db, course, CourseUpdate(title="Welcome to the course"))
        db.refresh(course)
        assert course.source_locale == "en"
        # The stale en-locale row must be gone.
        remaining = db.query(ContentTranslation).filter(
            ContentTranslation.entity_id == course.id
        ).count()
        assert remaining == 0

    def test_locale_unchanged_does_not_purge(self, db: Session):
        course = _make_course(db, source_locale="ru", title="Привет курс")
        _seed_translation(
            db, entity_type="course", entity_id=course.id, field="title", locale="en"
        )
        # Rewrite title but stay in Russian — detector returns 'ru',
        # source_locale stays 'ru', existing translations are still valid.
        update_course(db, course, CourseUpdate(title="Обновлённый курс на русском"))
        db.refresh(course)
        assert course.source_locale == "ru"
        remaining = db.query(ContentTranslation).filter(
            ContentTranslation.entity_id == course.id
        ).count()
        assert remaining == 1, "Translation should survive when source locale didn't flip"

    def test_unrelated_update_does_not_purge(self, db: Session):
        course = _make_course(db, source_locale="ru", title="Привет курс")
        _seed_translation(
            db, entity_type="course", entity_id=course.id, field="title", locale="en"
        )
        update_course(
            db, course, CourseUpdate(image_url="https://example.com/cover.png")
        )
        remaining = db.query(ContentTranslation).filter(
            ContentTranslation.entity_id == course.id
        ).count()
        assert remaining == 1
