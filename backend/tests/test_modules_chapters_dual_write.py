# ruff: noqa: RUF001
"""Phase 1c integration tests: module / chapter create/update
dual-writes into ``content_versions``.

Pins behaviour parallel to ``test_courses_dual_write.py``:

* Each create writes one ``content_versions`` row per translatable
  field with per-field detected locale.
* Each update supersedes only the fields the caller actually wrote.
* Short titles that the detector can't classify fall back to the
  parent course's ``source_locale``.

Modules have (title, description); chapters have just (title,).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.content_version import ContentVersion
from app.models.user import User, UserRole
from app.schemas.course import (
    ChapterCreate,
    ChapterUpdate,
    CourseCreate,
    ModuleCreate,
    ModuleUpdate,
)
from app.services.course_service._chapters import create_chapter, update_chapter
from app.services.course_service._courses import create_course
from app.services.course_service._modules import create_module, update_module


@pytest.fixture
def db():
    from tests.conftest import test_engine

    session = Session(bind=test_engine)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def teacher(db: Session) -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"mc-dw-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Module/Chapter Teacher",
        role=UserRole.TEACHER.value,
    )
    db.add(u)
    db.commit()
    return u


def _active_rows(db: Session, entity_type: str, entity_id: str) -> list[ContentVersion]:
    return (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == entity_id,
            ContentVersion.superseded_by.is_(None),
        )
        .order_by(ContentVersion.field)
        .all()
    )


def _make_course(db: Session, teacher: User, *, locale: str = "ru"):
    title, desc = ("Учебник", "Курс.") if locale == "ru" else ("Textbook", "Course on scripture.")
    return create_course(
        db,
        CourseCreate(title=title, description=desc),
        user_id=teacher.id,
        source_locale=locale,
    )


class TestModuleDualWrite:
    def test_create_writes_title_and_description(self, db: Session, teacher: User):
        course = _make_course(db, teacher)
        module = create_module(
            db,
            course.id,
            ModuleCreate(title="Модуль 1", description="О первой части."),
        )
        rows = {r.field: r for r in _active_rows(db, "module", module.id)}
        assert set(rows.keys()) == {"title", "description"}
        assert rows["title"].text == "Модуль 1"
        assert rows["title"].locale == "ru"
        assert rows["description"].locale == "ru"

    def test_create_with_no_description_skips_description_row(self, db: Session, teacher: User):
        course = _make_course(db, teacher)
        module = create_module(db, course.id, ModuleCreate(title="Модуль", description=None))
        rows = _active_rows(db, "module", module.id)
        assert [r.field for r in rows] == ["title"]

    def test_short_title_falls_back_to_course_source_locale(self, db: Session, teacher: User):
        # Title of just "1" — detector cannot classify; fallback is
        # the parent course's source_locale ("ru" here).
        course = _make_course(db, teacher, locale="ru")
        module = create_module(db, course.id, ModuleCreate(title="1", description=None))
        rows = _active_rows(db, "module", module.id)
        assert len(rows) == 1
        assert rows[0].locale == "ru"

    def test_update_title_supersedes_old_title_only(self, db: Session, teacher: User):
        course = _make_course(db, teacher)
        module = create_module(
            db,
            course.id,
            ModuleCreate(title="Старое", description="Описание."),
        )
        original_title = next(r for r in _active_rows(db, "module", module.id) if r.field == "title")
        update_module(db, module, ModuleUpdate(title="Новое"))
        active_title = next(r for r in _active_rows(db, "module", module.id) if r.field == "title")
        assert active_title.text == "Новое"
        db.refresh(original_title)
        assert original_title.superseded_by == active_title.id
        # description row is untouched (only one version of it).
        desc_versions = (
            db.query(ContentVersion)
            .filter(ContentVersion.entity_id == module.id, ContentVersion.field == "description")
            .count()
        )
        assert desc_versions == 1


class TestChapterDualWrite:
    def test_create_writes_title_row(self, db: Session, teacher: User):
        course = _make_course(db, teacher)
        module = create_module(db, course.id, ModuleCreate(title="Раздел", description=None))
        chapter = create_chapter(db, module.id, ChapterCreate(title="Глава 1"))
        rows = _active_rows(db, "chapter", chapter.id)
        assert [r.field for r in rows] == ["title"]
        assert rows[0].text == "Глава 1"
        assert rows[0].locale == "ru"

    def test_short_chapter_title_falls_back_to_course_source_locale(self, db: Session, teacher: User):
        # English course → English fallback when title has no signal.
        course = _make_course(db, teacher, locale="en")
        module = create_module(db, course.id, ModuleCreate(title="Module", description=None))
        chapter = create_chapter(db, module.id, ChapterCreate(title="1"))
        rows = _active_rows(db, "chapter", chapter.id)
        assert len(rows) == 1
        assert rows[0].locale == "en"

    def test_update_title_supersedes(self, db: Session, teacher: User):
        course = _make_course(db, teacher)
        module = create_module(db, course.id, ModuleCreate(title="Раздел", description=None))
        chapter = create_chapter(db, module.id, ChapterCreate(title="Глава первая"))
        original = next(iter(_active_rows(db, "chapter", chapter.id)))
        update_chapter(db, chapter, ChapterUpdate(title="Глава вторая"))
        active = next(iter(_active_rows(db, "chapter", chapter.id)))
        assert active.text == "Глава вторая"
        db.refresh(original)
        assert original.superseded_by == active.id
