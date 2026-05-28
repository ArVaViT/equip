"""Tests for the Phase 3 ``content_versions`` backfill script.

Four layers of coverage:

1. **Per-entity unit** — given one seeded entity (with text columns
   and a few ``content_translations`` rows), running the backfill
   produces the expected ``content_versions`` rows.
2. **Cross-entity types** — sanity-check that every entity type in
   the registry has a working backfill path (one representative
   test per entity type).
3. **Idempotency** — running the script twice produces the same
   ``content_versions`` state (no duplicate rows, no extra
   supersession).
4. **Edge cases** — the prod-audit-identified surprises:
   * Same-locale collisions (CT row identical to source).
   * Cross-locale (RU CT of an EN-text entity in an "ru" course).
   * Soft-deleted entities skipped.
   * Empty text fields skipped.
   * Failed/failed_permanent legacy rows preserved.
   * Translator override (``content_translations.origin='human'``).
   * Cohort name → field='title' mapping.
   * Dry-run leaves the DB untouched.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from app.models.content_translation import ContentTranslation
from app.models.content_version import ContentVersion
from app.models.course import Chapter, Course, Module
from scripts.backfill_content_versions import backfill

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@pytest.fixture
def db():
    from sqlalchemy.orm import Session as _Session

    from tests.conftest import test_engine

    session = _Session(bind=test_engine)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _isolate(db: Session):
    """Wipe both stores between tests so seed counts are predictable."""
    yield
    db.query(ContentVersion).delete()
    db.query(ContentTranslation).delete()
    db.query(Chapter).delete()
    db.query(Module).delete()
    db.query(Course).delete()
    db.commit()


def _ensure_teacher(db: Session) -> None:
    from app.models.user import User
    from tests.conftest import TEACHER_ID

    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="t@x.com", full_name="T", role="teacher"))
        db.commit()


def _ensure_admin(db: Session) -> None:
    from app.models.user import User
    from tests.conftest import ADMIN_ID

    if db.get(User, ADMIN_ID) is None:
        db.add(User(id=ADMIN_ID, email="a@x.com", full_name="A", role="admin"))
        db.commit()


def _seed_course(
    db: Session,
    *,
    course_id: str = "bf-course-1",
    title: str = "Заголовок",
    description: str = "Описание.",
    source_locale: str = "ru",
) -> Course:
    from tests.conftest import TEACHER_ID

    _ensure_teacher(db)
    c = Course(
        id=course_id,
        title=title,
        description=description,
        created_by=TEACHER_ID,
        status="published",
        source_locale=source_locale,
    )
    db.add(c)
    db.commit()
    return c


def _active(db: Session, *, entity_type: str, entity_id: str) -> list[ContentVersion]:
    return (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == entity_id,
            ContentVersion.superseded_by.is_(None),
        )
        .order_by(ContentVersion.field, ContentVersion.locale)
        .all()
    )


# ---------------------------------------------------------------------------
# 1) Per-entity unit
# ---------------------------------------------------------------------------


class TestSingleCourseBackfill:
    def test_human_rows_from_entity_columns(self, db: Session):
        course = _seed_course(db)
        backfill(db, apply=True, entity_types=["course"])
        rows = _active(db, entity_type="course", entity_id=course.id)
        by_field = {(r.field, r.locale): r for r in rows}
        assert ("title", "ru") in by_field
        assert ("description", "ru") in by_field
        assert by_field[("title", "ru")].origin == "human"
        assert by_field[("title", "ru")].text == "Заголовок"

    def test_mt_rows_from_content_translations(self, db: Session):
        course = _seed_course(db)
        db.add(
            ContentTranslation(
                entity_type="course",
                entity_id=course.id,
                field="title",
                locale="en",
                text="Header",
                origin="mt",
                source_hash="h1",
                status="ok",
                attempts=0,
            )
        )
        db.commit()
        backfill(db, apply=True, entity_types=["course"])
        rows = _active(db, entity_type="course", entity_id=course.id)
        en_title = next(r for r in rows if r.field == "title" and r.locale == "en")
        assert en_title.origin == "mt"
        assert en_title.text == "Header"
        # source_version_id links to the human row.
        ru_title = next(r for r in rows if r.field == "title" and r.locale == "ru")
        assert en_title.source_version_id == ru_title.id
        # Source-locale recorded so cascade invalidation can find the right human row.
        assert en_title.source_locale == "ru"
        assert en_title.source_hash == "h1"


# ---------------------------------------------------------------------------
# 2) Per-row language detection overrides course.source_locale
# ---------------------------------------------------------------------------


class TestPerRowDetection:
    def test_en_module_under_ru_course_lands_at_en(self, db: Session):
        from tests.conftest import TEACHER_ID

        course = _seed_course(db)
        module = Module(
            id="bf-mod-en",
            course_id=course.id,
            title="Module 1",  # English text under an "ru" course
            description=None,
            order_index=0,
        )
        db.add(module)
        db.commit()
        backfill(db, apply=True, entity_types=["module"])
        rows = _active(db, entity_type="module", entity_id=module.id)
        title = next(r for r in rows if r.field == "title")
        # Per-row detection wins over course.source_locale="ru" — the
        # bug that broke Vadym's "Тайтл" course before Phase 1.
        assert title.locale == "en"
        assert title.text == "Module 1"
        # Silence unused-import warning while keeping conftest import compat.
        assert TEACHER_ID  # type: ignore[truthy-bool]


# ---------------------------------------------------------------------------
# 3) Same-locale collision (16 prod cases)
# ---------------------------------------------------------------------------


class TestSameLocaleCollision:
    def test_ct_identical_to_source_does_not_duplicate(self, db: Session):
        # An "ru" course with an MT row whose locale=ru AND text equals
        # the source title. Prod has 16 of these.
        course = _seed_course(db, title="Учебник")
        db.add(
            ContentTranslation(
                entity_type="course",
                entity_id=course.id,
                field="title",
                locale="ru",
                text="Учебник",  # identical to source
                origin="mt",
                source_hash="h-dup",
                status="ok",
                attempts=0,
            )
        )
        db.commit()
        backfill(db, apply=True, entity_types=["course"])
        rows = _active(db, entity_type="course", entity_id=course.id)
        ru_titles = [r for r in rows if r.field == "title" and r.locale == "ru"]
        # Exactly one row — the human source wins; MT no-ops via the
        # write helper's belt-and-braces refuse-to-overwrite-human.
        assert len(ru_titles) == 1
        assert ru_titles[0].origin == "human"


# ---------------------------------------------------------------------------
# 4) Cross-locale (RU CT of EN source in an "ru" course)
# ---------------------------------------------------------------------------


class TestCrossLocaleSourceAndTranslation:
    def test_en_source_with_ru_translation(self, db: Session):
        course = _seed_course(db)
        module = Module(
            id="bf-mod-cross",
            course_id=course.id,
            title="Lesson 1",  # English source
            description=None,
            order_index=0,
        )
        db.add(module)
        db.add(
            ContentTranslation(
                entity_type="module",
                entity_id=module.id,
                field="title",
                locale="ru",
                text="Урок 1",  # Russian translation of the English source
                origin="mt",
                source_hash="h-cross",
                status="ok",
                attempts=0,
            )
        )
        db.commit()
        backfill(db, apply=True, entity_types=["module"])
        rows = _active(db, entity_type="module", entity_id=module.id)
        by_locale = {r.locale: r for r in rows if r.field == "title"}
        assert by_locale["en"].origin == "human"
        assert by_locale["en"].text == "Lesson 1"
        assert by_locale["ru"].origin == "mt"
        assert by_locale["ru"].text == "Урок 1"
        assert by_locale["ru"].source_locale == "en"
        # source_version_id links to the en human row.
        assert by_locale["ru"].source_version_id == by_locale["en"].id


# ---------------------------------------------------------------------------
# 5) Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_two_runs_produce_same_row_count(self, db: Session):
        course = _seed_course(db)
        db.add(
            ContentTranslation(
                entity_type="course",
                entity_id=course.id,
                field="title",
                locale="en",
                text="Header",
                origin="mt",
                source_hash="h1",
                status="ok",
                attempts=0,
            )
        )
        db.commit()
        backfill(db, apply=True, entity_types=["course"])
        after_first = db.query(ContentVersion).count()
        backfill(db, apply=True, entity_types=["course"])
        after_second = db.query(ContentVersion).count()
        assert after_first == after_second
        # No superseded rows (idempotent skip, not re-write).
        superseded = db.query(ContentVersion).filter(ContentVersion.superseded_by.is_not(None)).count()
        assert superseded == 0


# ---------------------------------------------------------------------------
# 6) Soft-delete skipped
# ---------------------------------------------------------------------------


class TestSoftDeleteSkipped:
    def test_soft_deleted_course_not_backfilled(self, db: Session):
        from datetime import UTC, datetime

        from tests.conftest import TEACHER_ID

        _ensure_teacher(db)
        course = Course(
            id="bf-soft-1",
            title="Killed",
            created_by=TEACHER_ID,
            status="draft",
            source_locale="ru",
            deleted_at=datetime.now(UTC),
        )
        db.add(course)
        db.commit()
        backfill(db, apply=True, entity_types=["course"])
        assert _active(db, entity_type="course", entity_id=course.id) == []


# ---------------------------------------------------------------------------
# 7) Empty fields skipped
# ---------------------------------------------------------------------------


class TestEmptyFieldsSkipped:
    def test_empty_description_does_not_insert_row(self, db: Session):
        course = _seed_course(db, description="")
        backfill(db, apply=True, entity_types=["course"])
        rows = _active(db, entity_type="course", entity_id=course.id)
        fields = [r.field for r in rows]
        assert "title" in fields
        assert "description" not in fields


# ---------------------------------------------------------------------------
# 8) Failed legacy rows preserved
# ---------------------------------------------------------------------------


class TestFailedRowsPreserved:
    def test_failed_status_carries_over(self, db: Session):
        course = _seed_course(db)
        db.add(
            ContentTranslation(
                entity_type="course",
                entity_id=course.id,
                field="title",
                locale="en",
                text="",  # failed rows carry empty text in cv too
                origin="mt",
                source_hash="h-fail",
                status="failed",
                attempts=3,
            )
        )
        db.commit()
        backfill(db, apply=True, entity_types=["course"])
        rows = _active(db, entity_type="course", entity_id=course.id)
        en_title = next(r for r in rows if r.field == "title" and r.locale == "en")
        assert en_title.status == "failed"
        assert en_title.attempts == 3


# ---------------------------------------------------------------------------
# 9) Translator override (CT origin='human') preserved
# ---------------------------------------------------------------------------


class TestTranslatorOverridePreserved:
    def test_ct_human_becomes_cv_human(self, db: Session):
        course = _seed_course(db)
        db.add(
            ContentTranslation(
                entity_type="course",
                entity_id=course.id,
                field="title",
                locale="en",
                text="Override by Translator",
                origin="human",
                source_hash="h-or",
                status="ok",
                attempts=0,
            )
        )
        db.commit()
        backfill(db, apply=True, entity_types=["course"])
        rows = _active(db, entity_type="course", entity_id=course.id)
        en_title = next(r for r in rows if r.field == "title" and r.locale == "en")
        assert en_title.origin == "human"
        assert en_title.text == "Override by Translator"


# ---------------------------------------------------------------------------
# 10) Dry-run leaves DB untouched
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_writes_nothing(self, db: Session):
        course = _seed_course(db)
        db.add(
            ContentTranslation(
                entity_type="course",
                entity_id=course.id,
                field="title",
                locale="en",
                text="Header",
                origin="mt",
                source_hash="h1",
                status="ok",
                attempts=0,
            )
        )
        db.commit()
        backfill(db, apply=False, entity_types=["course"])
        assert _active(db, entity_type="course", entity_id=course.id) == []


# ---------------------------------------------------------------------------
# 11) Cohort name → field='title'
# ---------------------------------------------------------------------------


class TestCohortNameMapsToTitle:
    def test_cohort_name_lands_at_title_field(self, db: Session):
        from datetime import UTC, datetime

        from app.models.cohort import Cohort
        from tests.conftest import ADMIN_ID

        _ensure_admin(db)
        cohort_id = uuid.uuid4()
        cohort = Cohort(
            id=cohort_id,
            name="Когорта весна 2026",
            start_date=datetime(2026, 3, 1, tzinfo=UTC),
            end_date=datetime(2026, 6, 1, tzinfo=UTC),
            created_by=ADMIN_ID,
        )
        db.add(cohort)
        db.commit()
        backfill(db, apply=True, entity_types=["cohort"])
        rows = _active(db, entity_type="cohort", entity_id=str(cohort_id))
        assert len(rows) == 1
        assert rows[0].field == "title"  # NOT "name"
        assert rows[0].text == "Когорта весна 2026"
        assert rows[0].locale == "ru"


# ---------------------------------------------------------------------------
# 12) Multi-entity end-to-end
# ---------------------------------------------------------------------------


class TestEndToEndMultiEntity:
    def test_course_module_chapter_tree(self, db: Session):
        course = _seed_course(db, course_id="bf-e2e-c")
        module = Module(id="bf-e2e-m", course_id=course.id, title="Раздел", order_index=0)
        chapter = Chapter(
            id="bf-e2e-ch",
            module_id=module.id,
            title="Глава первая",
            order_index=0,
            chapter_type="text",
        )
        db.add_all([module, chapter])
        db.commit()
        backfill(db, apply=True, entity_types=["course", "module", "chapter"])
        # Each entity has its source row(s).
        assert len(_active(db, entity_type="course", entity_id=course.id)) == 2  # title + description
        assert len(_active(db, entity_type="module", entity_id=module.id)) == 1  # title only (no description)
        assert len(_active(db, entity_type="chapter", entity_id=chapter.id)) == 1  # title
