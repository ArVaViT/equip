# ruff: noqa: RUF001
"""Pin the chapter column-vs-cv synchronization invariant.

Chapter is unique among the bilingual entities: ``chapters.title`` is
still a real column (unlike ``courses.title`` and ``modules.title``,
which were dropped in Phase 5g). Every write path is responsible for
keeping the column and the ``content_versions`` source-locale row in
lockstep. This file pins that contract so a future refactor that
forgets one side breaks CI.

Invariant tested:

    chapter.title (column)
        == cv.text WHERE entity_type='chapter' AND field='title'
                     AND locale = course.source_locale
                     AND superseded_by IS NULL
                     AND status = 'ok'

after every create / update operation. A 5bl audit (course-title
audit follow-up on the module/chapter surface) raised false
positives because the auditor read the column-and-cv dualism as a
sync hazard rather than the deliberate architecture it is. The test
+ the docstring on ``app/models/course.py::Chapter`` together
document the contract so the next reviewer doesn't repeat the
walk.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.content_version import ContentVersion, ContentVersionStatus
from app.models.user import User, UserRole
from app.schemas.course import (
    ChapterCreate,
    ChapterUpdate,
    CourseCreate,
    ModuleCreate,
)
from app.services.course_service._chapters import create_chapter, update_chapter
from app.services.course_service._courses import create_course
from app.services.course_service._modules import create_module


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
        email=f"chap-inv-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Chapter Invariant Teacher",
        role=UserRole.TEACHER.value,
    )
    db.add(u)
    db.commit()
    return u


def _active_cv_title(db: Session, chapter_id: str, *, locale: str) -> str | None:
    """Read the active+ok cv title row at a specific locale."""
    row = (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == "chapter",
            ContentVersion.entity_id == chapter_id,
            ContentVersion.field == "title",
            ContentVersion.locale == locale,
            ContentVersion.superseded_by.is_(None),
            ContentVersion.status == ContentVersionStatus.OK,
        )
        .one_or_none()
    )
    return row.text if row is not None else None


def _make_ru_course(db: Session, teacher: User):
    """RU-source course so the chapter's source-locale row sits at locale='ru'."""
    return create_course(
        db,
        CourseCreate(title="Учебник", description="Курс."),
        user_id=teacher.id,
        source_locale="ru",
    )


def test_create_chapter_holds_column_eq_cv_source(db: Session, teacher: User):
    """After ``create_chapter`` the column and the source-locale cv row
    carry the same text. This is the foundational write-path invariant."""
    course = _make_ru_course(db, teacher)
    module = create_module(db, course.id, ModuleCreate(title="Раздел", description=None))
    chapter = create_chapter(db, module.id, ChapterCreate(title="Глава первая"))

    cv_title = _active_cv_title(db, chapter.id, locale="ru")
    assert chapter.title == "Глава первая"
    assert cv_title == chapter.title, "create_chapter must dual-write: column and cv source row diverged"


def test_update_chapter_keeps_column_eq_cv_source(db: Session, teacher: User):
    """After ``update_chapter`` the column and the *new* source-locale cv
    row carry the same text — the previous cv row was superseded, not
    abandoned."""
    course = _make_ru_course(db, teacher)
    module = create_module(db, course.id, ModuleCreate(title="Раздел", description=None))
    chapter = create_chapter(db, module.id, ChapterCreate(title="Старое название"))

    update_chapter(db, chapter, ChapterUpdate(title="Новое название"))
    db.refresh(chapter)

    cv_title = _active_cv_title(db, chapter.id, locale="ru")
    assert chapter.title == "Новое название"
    assert cv_title == chapter.title, "update_chapter must dual-write: column and cv source row diverged after update"


def test_update_chapter_without_title_leaves_column_eq_cv_source(db: Session, teacher: User):
    """An update that doesn't touch ``title`` must not desync the
    column from cv — even though the patch is a no-op for title."""
    course = _make_ru_course(db, teacher)
    module = create_module(db, course.id, ModuleCreate(title="Раздел", description=None))
    chapter = create_chapter(db, module.id, ChapterCreate(title="Глава"))

    # PATCH with no title field — only structural fields would change.
    update_chapter(db, chapter, ChapterUpdate(order_index=5))
    db.refresh(chapter)

    cv_title = _active_cv_title(db, chapter.id, locale="ru")
    assert chapter.title == "Глава"
    assert cv_title == chapter.title, "non-title update must not desync column from cv"
