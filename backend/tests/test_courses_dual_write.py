# ruff: noqa: RUF001
"""Phase 1b integration tests: course create/update dual-writes
into ``content_versions``.

Pins the contract: every course title/description that gets written
to the entity column ALSO appears as an active human row in
``content_versions`` with the correct per-field detected locale.

Reads stay on the entity columns for now (Phase 2 is when the
dual-read layer flips on); these tests just verify the SHADOW
write — the resolve path is untouched.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.content_version import ContentVersion
from app.models.user import User, UserRole
from app.schemas.course import CourseCreate, CourseUpdate
from app.services.course_service._courses import create_course, update_course


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
        email=f"dual-write-{uuid.uuid4().hex[:8]}@example.com",
        full_name="Dual-Write Teacher",
        role=UserRole.TEACHER.value,
    )
    db.add(u)
    db.commit()
    return u


def _active_rows(db: Session, course_id: str) -> list[ContentVersion]:
    return (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == "course",
            ContentVersion.entity_id == course_id,
            ContentVersion.superseded_by.is_(None),
        )
        .order_by(ContentVersion.field)
        .all()
    )


class TestCreateCourseDualWrite:
    def test_writes_title_and_description_rows(self, db: Session, teacher: User):
        course = create_course(
            db,
            CourseCreate(title="Bible Study 101", description="Intro to scripture."),
            user_id=teacher.id,
            source_locale="en",
        )
        rows = _active_rows(db, course.id)
        by_field = {r.field: r for r in rows}
        assert set(by_field.keys()) == {"title", "description"}
        assert by_field["title"].text == "Bible Study 101"
        assert by_field["title"].origin == "human"
        assert by_field["title"].status == "ok"
        assert by_field["title"].authored_by == teacher.id
        assert by_field["description"].text == "Intro to scripture."

    def test_per_field_locale_detection(self, db: Session, teacher: User):
        # English title, Russian description — each row should land
        # in the correct locale.
        course = create_course(
            db,
            CourseCreate(title="Bible Study 101", description="Введение в Писание."),
            user_id=teacher.id,
            source_locale="en",
        )
        rows = {r.field: r for r in _active_rows(db, course.id)}
        assert rows["title"].locale == "en"
        assert rows["description"].locale == "ru"

    def test_skips_empty_description(self, db: Session, teacher: User):
        course = create_course(
            db,
            CourseCreate(title="Bible Study 101", description=None),
            user_id=teacher.id,
            source_locale="en",
        )
        rows = _active_rows(db, course.id)
        assert [r.field for r in rows] == ["title"]

    def test_falls_back_to_course_source_locale_when_undetectable(self, db: Session, teacher: User):
        # ASCII non-letter title — detector returns None, falls back
        # to the course source_locale.
        course = create_course(
            db,
            CourseCreate(title="123", description=None),
            user_id=teacher.id,
            source_locale="ru",
        )
        rows = _active_rows(db, course.id)
        assert len(rows) == 1
        assert rows[0].locale == "ru"


class TestUpdateCourseDualWrite:
    def test_title_change_supersedes_old_title_row(self, db: Session, teacher: User):
        course = create_course(
            db,
            CourseCreate(title="Старый заголовок", description="Описание."),
            user_id=teacher.id,
            source_locale="ru",
        )
        original_title_row = next(r for r in _active_rows(db, course.id) if r.field == "title")
        update_course(db, course, CourseUpdate(title="Новый заголовок"))
        # Active row count unchanged (still 2: title + description).
        active = _active_rows(db, course.id)
        assert len(active) == 2
        active_title = next(r for r in active if r.field == "title")
        assert active_title.text == "Новый заголовок"
        # Original title row is now superseded but preserved in history.
        db.refresh(original_title_row)
        assert original_title_row.superseded_by == active_title.id
        # Description row was NOT touched (PATCH only included title).
        descs = (
            db.query(ContentVersion)
            .filter(
                ContentVersion.entity_id == course.id,
                ContentVersion.field == "description",
            )
            .all()
        )
        assert len(descs) == 1  # never re-written → no version history bump

    def test_unchanged_title_is_idempotent(self, db: Session, teacher: User):
        course = create_course(
            db,
            CourseCreate(title="Стабильный", description="Текст."),
            user_id=teacher.id,
            source_locale="ru",
        )
        original_title_id = next(r.id for r in _active_rows(db, course.id) if r.field == "title")
        # PATCH with identical title text → no supersession.
        update_course(db, course, CourseUpdate(title="Стабильный"))
        active_title = next(r for r in _active_rows(db, course.id) if r.field == "title")
        assert active_title.id == original_title_id

    def test_non_text_patch_does_not_touch_content_versions(self, db: Session, teacher: User):
        course = create_course(
            db,
            CourseCreate(title="Курс", description="Описание."),
            user_id=teacher.id,
            source_locale="ru",
        )
        ids_before = {r.id for r in _active_rows(db, course.id)}
        # PATCH that touches only image_url — content_versions stays untouched.
        update_course(db, course, CourseUpdate(image_url="https://example.com/x.png"))
        ids_after = {r.id for r in _active_rows(db, course.id)}
        assert ids_before == ids_after
