"""Phase 4 tests: ``CONTENT_VERSIONS_READ_PRIMARY=1`` flips the
overlay source from ``content_translations`` to ``content_versions``.

Pins the contract:

* With the flag OFF, ``fetch_overlay_triples_bulk`` /
  ``batch_fetch_course_translations`` read from
  ``content_translations`` exactly as before.
* With the flag ON, the same functions return the same dict shape
  but sourced from ``content_versions``.
* The dict shape contract (``(entity_type, entity_id, field) ->
  text`` and ``(entity_id, field) -> text``) is identical across
  flag states — call sites stay byte-for-byte unchanged.
* Cv-only data (no legacy row) becomes visible when flag is ON.
* Cv-superseded rows are excluded.
* Cv ``status='failed'`` rows are excluded (resolver falls back to
  source via the upstream call site).
* Flipping the flag mid-session takes effect immediately.

The downstream consumer ``pick_overlay_value`` is unchanged in
Phase 4 (its per-field detection logic still runs), so testing the
fetchers in isolation is sufficient. Integration via Localizer is
covered by ``test_localizer_dual_read.py``'s existing fixtures
when re-run with the flag toggled.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.models.content_translation import ContentTranslation
from app.services.content_versions import set_read_primary
from app.services.content_versions.write import record_human_version, record_mt_version
from app.services.translation.resolve_for_display import (
    batch_fetch_course_translations,
    fetch_overlay_triples_bulk,
)

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


@pytest.fixture
def read_primary_on():
    set_read_primary(True)
    yield
    set_read_primary(False)


@pytest.fixture
def read_primary_off():
    # Explicit OFF — covers the case where the test runs under
    # CI with ``CONTENT_VERSIONS_READ_PRIMARY=1`` in the env, which
    # would otherwise leak the ON state into "flag OFF" tests.
    set_read_primary(False)
    yield
    set_read_primary(False)


@pytest.fixture(autouse=True)
def _isolate(db: Session):
    """Wipe both stores between tests so seed counts are predictable."""
    from app.models.content_version import ContentVersion

    yield
    db.query(ContentVersion).delete()
    db.query(ContentTranslation).delete()
    db.commit()


class TestFlagOffPreservesLegacyBehavior:
    def test_overlay_triples_reads_from_content_translations(self, db: Session, read_primary_off: None):
        # Flag default OFF; only the legacy store has a row.
        db.add(
            ContentTranslation(
                entity_type="course",
                entity_id="ct-only",
                field="title",
                locale="ru",
                text="Из legacy",
                origin="mt",
                source_hash="h",
                status="ok",
                attempts=0,
            )
        )
        db.commit()
        result = fetch_overlay_triples_bulk(db, [("course", "ct-only", "title")], "ru")
        assert result == {("course", "ct-only", "title"): "Из legacy"}

    def test_overlay_triples_does_not_read_cv_when_flag_off(self, db: Session, read_primary_off: None):
        # Cv has a row; legacy doesn't. With flag OFF the cv row is invisible.
        record_human_version(db, entity_type="course", entity_id="cv-only", field="title", locale="ru", text="Из cv")
        db.commit()
        result = fetch_overlay_triples_bulk(db, [("course", "cv-only", "title")], "ru")
        assert result == {}


class TestFlagOnReadsFromCv:
    def test_overlay_triples_reads_from_content_versions(self, db: Session, read_primary_on: None):
        record_human_version(db, entity_type="course", entity_id="flip-1", field="title", locale="ru", text="Из cv")
        db.commit()
        result = fetch_overlay_triples_bulk(db, [("course", "flip-1", "title")], "ru")
        assert result == {("course", "flip-1", "title"): "Из cv"}

    def test_overlay_triples_ignores_legacy_when_flag_on(self, db: Session, read_primary_on: None):
        # Legacy has a row; cv doesn't. With flag ON the legacy row is invisible.
        db.add(
            ContentTranslation(
                entity_type="course",
                entity_id="legacy-ignored",
                field="title",
                locale="ru",
                text="Должно быть невидимым",
                origin="mt",
                source_hash="h",
                status="ok",
                attempts=0,
            )
        )
        db.commit()
        result = fetch_overlay_triples_bulk(db, [("course", "legacy-ignored", "title")], "ru")
        assert result == {}

    def test_overlay_triples_excludes_failed_status(self, db: Session, read_primary_on: None):
        from app.services.content_versions.write import record_mt_failure

        record_mt_failure(
            db,
            entity_type="course",
            entity_id="failed-1",
            field="title",
            locale="ru",
            source_locale="en",
            source_hash="h",
        )
        db.commit()
        result = fetch_overlay_triples_bulk(db, [("course", "failed-1", "title")], "ru")
        assert result == {}

    def test_overlay_triples_excludes_superseded_rows(self, db: Session, read_primary_on: None):
        # v1 inserted then superseded by v2; only v2 should appear.
        v1 = record_human_version(db, entity_type="course", entity_id="sup-1", field="title", locale="ru", text="v1")
        db.commit()
        v2 = record_human_version(db, entity_type="course", entity_id="sup-1", field="title", locale="ru", text="v2")
        db.commit()
        result = fetch_overlay_triples_bulk(db, [("course", "sup-1", "title")], "ru")
        assert result == {("course", "sup-1", "title"): "v2"}
        # v1 still exists in the table but is superseded.
        db.refresh(v1)
        assert v1.superseded_by == v2.id

    def test_overlay_triples_handles_mt_origin_row(self, db: Session, read_primary_on: None):
        record_mt_version(
            db,
            entity_type="course",
            entity_id="mt-1",
            field="title",
            locale="ru",
            text="Машинный",
            source_locale="en",
            source_hash="h",
        )
        db.commit()
        result = fetch_overlay_triples_bulk(db, [("course", "mt-1", "title")], "ru")
        assert result == {("course", "mt-1", "title"): "Машинный"}


class TestCourseBulkFetchHonorsFlag:
    def test_course_bulk_reads_legacy_when_flag_off(self, db: Session, read_primary_off: None):
        db.add(
            ContentTranslation(
                entity_type="course",
                entity_id="course-flag-off",
                field="title",
                locale="ru",
                text="Из legacy",
                origin="mt",
                source_hash="h",
                status="ok",
                attempts=0,
            )
        )
        db.commit()
        result = batch_fetch_course_translations(db, course_ids=["course-flag-off"], display_locale="ru")
        assert result == {("course-flag-off", "title"): "Из legacy"}

    def test_course_bulk_reads_cv_when_flag_on(self, db: Session, read_primary_on: None):
        record_human_version(
            db, entity_type="course", entity_id="course-flag-on", field="title", locale="ru", text="Из cv"
        )
        record_human_version(
            db,
            entity_type="course",
            entity_id="course-flag-on",
            field="description",
            locale="ru",
            text="Описание cv",
        )
        db.commit()
        result = batch_fetch_course_translations(db, course_ids=["course-flag-on"], display_locale="ru")
        assert result == {
            ("course-flag-on", "title"): "Из cv",
            ("course-flag-on", "description"): "Описание cv",
        }

    def test_course_bulk_filters_to_title_and_description_only(self, db: Session, read_primary_on: None):
        # Imagine a stray field somehow landed in cv; the catalog
        # bulk fetcher must only return title + description (the
        # course-summary contract).
        record_human_version(db, entity_type="course", entity_id="catalog", field="title", locale="ru", text="Title")
        record_human_version(
            db,
            entity_type="course",
            entity_id="catalog",
            field="instructions",
            locale="ru",
            text="Лишнее",
        )
        db.commit()
        result = batch_fetch_course_translations(db, course_ids=["catalog"], display_locale="ru")
        assert "title" in {k[1] for k in result}
        assert "instructions" not in {k[1] for k in result}


class TestFlagFlipMidSession:
    def test_flipping_flag_changes_result_immediately(self, db: Session):
        # Same key in both stores with different text. Flipping the
        # flag toggles which store wins on the very next call.
        record_human_version(db, entity_type="course", entity_id="both", field="title", locale="ru", text="Из cv")
        db.add(
            ContentTranslation(
                entity_type="course",
                entity_id="both",
                field="title",
                locale="ru",
                text="Из legacy",
                origin="mt",
                source_hash="h",
                status="ok",
                attempts=0,
            )
        )
        db.commit()

        # Flag OFF (default) → legacy
        set_read_primary(False)
        result_off = fetch_overlay_triples_bulk(db, [("course", "both", "title")], "ru")
        assert result_off == {("course", "both", "title"): "Из legacy"}

        # Flag ON → cv
        try:
            set_read_primary(True)
            result_on = fetch_overlay_triples_bulk(db, [("course", "both", "title")], "ru")
            assert result_on == {("course", "both", "title"): "Из cv"}
        finally:
            set_read_primary(False)


class TestBulkFetchersHandleEmptyKeys:
    """Cosmetic invariant: passing empty input returns an empty dict
    without hitting the DB. Important for catalog routes that pass
    empty course_ids when no courses match a filter."""

    def test_empty_keys_short_circuits(self, db: Session, read_primary_on: None):
        assert fetch_overlay_triples_bulk(db, [], "ru") == {}
        assert batch_fetch_course_translations(db, course_ids=[], display_locale="ru") == {}
