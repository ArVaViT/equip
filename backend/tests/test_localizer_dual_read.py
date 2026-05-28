"""Phase 2b tests: ``Localizer.pick`` fires the dual-read comparator.

Pins the wiring contract:

* When ``Localizer`` is built via ``Localizer.build(db, ...)``, every
  ``pick`` call fires ``maybe_compare_and_log`` behind the legacy
  return value.
* When ``Localizer`` is constructed directly (without ``db``), the
  comparator is never called — preserves the existing test surface.
* The sampler gate works: rate=0.0 short-circuits without touching
  the DB; rate=1.0 always fires.
* INTERESTING reasons produce a structured warning log; benign
  reasons are silent.
* A comparator exception NEVER bubbles out of ``pick``.
* The legacy return value is unchanged regardless of comparator
  outcome.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from app.services.content_versions import set_compare_sample_rate
from app.services.content_versions.write import record_human_version
from app.services.translation.resolve_for_display import Localizer

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
def sample_rate_one():
    """Force the comparator to always fire for this test."""
    set_compare_sample_rate(1.0)
    yield
    set_compare_sample_rate(0.0)


class TestLocalizerWithoutDb:
    """Constructing Localizer directly (no db) keeps it as a pure
    in-memory helper — comparator never fires. Lets existing tests
    and any inline helper that builds its own overlay map continue
    working unchanged."""

    def test_pick_returns_overlay_value_when_no_db(self, sample_rate_one: None):
        loc = Localizer(
            overlay={("course", "c1", "title"): "Заголовок"},
            source_locale="en",
            display_locale="ru",
        )
        result = loc.pick("course", "c1", "title", "Title")
        assert result == "Заголовок"
        # No db ⇒ comparator never called; no failure even though
        # the rate is 1.0.

    def test_pick_falls_back_to_base_when_no_overlay(self):
        loc = Localizer(overlay={}, source_locale="en", display_locale="ru")
        assert loc.pick("course", "c1", "title", "Title") == "Title"


class TestLocalizerWithDbAndSamplerOff:
    """db is held but rate=0.0 — comparator must not run. Confirms
    the sampler gate is the actual gate."""

    def test_pick_works_normally_when_sample_rate_zero(self, db: Session, caplog: pytest.LogCaptureFixture):
        set_compare_sample_rate(0.0)
        loc = Localizer.build(db, [], source_locale="en", display_locale="ru")
        with caplog.at_level(logging.WARNING, logger="app.services.content_versions.compare"):
            result = loc.pick("course", "unsampled-1", "title", "Title")
        assert result == "Title"
        assert "content_versions dual-read" not in caplog.text


class TestLocalizerFiresInterestingMismatch:
    """When the new store has a translation the legacy missed
    (``NEW_ONLY``), the comparator fires and a structured warning
    lands in the log."""

    def test_new_only_mismatch_is_logged(
        self,
        db: Session,
        sample_rate_one: None,
        caplog: pytest.LogCaptureFixture,
    ):
        # Pre-seed cv with both source and translation.
        record_human_version(
            db, entity_type="course", entity_id="cv-new-only", field="title", locale="en", text="Title"
        )
        record_human_version(
            db, entity_type="course", entity_id="cv-new-only", field="title", locale="ru", text="Заголовок"
        )
        db.commit()
        # Build Localizer with an empty overlay (legacy will fall back
        # to source) but db hooked in so comparator runs.
        loc = Localizer.build(db, [], source_locale="en", display_locale="ru")
        with caplog.at_level(logging.WARNING, logger="app.services.content_versions.compare"):
            result = loc.pick("course", "cv-new-only", "title", "Title")
        # Legacy return unchanged.
        assert result == "Title"
        # Structured warning fired with NEW_ONLY reason.
        records = [r for r in caplog.records if "content_versions dual-read" in r.message]
        assert len(records) == 1
        assert getattr(records[0], "cv_compare_reason", None) == "new_only"
        assert getattr(records[0], "cv_compare_entity_type", None) == "course"
        assert getattr(records[0], "cv_compare_entity_id", None) == "cv-new-only"
        # Lengths surface for triage but the full text is never dumped.
        assert "Заголовок" not in caplog.text
        assert "Title" not in caplog.text


class TestLocalizerSilentOnBenignReasons:
    """``LEGACY_ONLY_NO_BACKFILL`` (the pre-Phase-3 expected state)
    must NOT fire a warning even when the sampler is wide open."""

    def test_no_cv_rows_is_silent(
        self,
        db: Session,
        sample_rate_one: None,
        caplog: pytest.LogCaptureFixture,
    ):
        # No cv rows for this entity.
        loc = Localizer.build(db, [], source_locale="en", display_locale="ru")
        with caplog.at_level(logging.WARNING, logger="app.services.content_versions.compare"):
            result = loc.pick("course", "cv-silent-1", "title", "Title")
        assert result == "Title"
        assert "content_versions dual-read" not in caplog.text


class TestLocalizerExceptionsAreSwallowed:
    """A bug in the comparator (or a flaky DB read) must NEVER affect
    the response. The pick return value depends only on the legacy
    overlay map."""

    def test_comparator_exception_does_not_propagate(
        self,
        db: Session,
        sample_rate_one: None,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ):
        # Replace compare_resolved_text with a function that raises.
        def boom(*args: object, **kwargs: object):
            raise RuntimeError("simulated comparator failure")

        monkeypatch.setattr("app.services.content_versions.compare.compare_resolved_text", boom)
        loc = Localizer.build(db, [], source_locale="en", display_locale="ru")
        with caplog.at_level(logging.ERROR, logger="app.services.content_versions.compare"):
            # Should not raise.
            result = loc.pick("course", "cv-err-1", "title", "Title")
        assert result == "Title"
        # The swallowed exception logged at ERROR with a traceable message.
        assert any("dual-read comparator raised" in r.message for r in caplog.records)


class TestLocalizerPicksUpSamplerAtCallTime:
    """The sampler rate is consulted on every call, so flipping it
    mid-test takes effect immediately for the next pick."""

    def test_flipping_rate_to_one_starts_firing(
        self,
        db: Session,
        caplog: pytest.LogCaptureFixture,
    ):
        record_human_version(db, entity_type="course", entity_id="cv-flip", field="title", locale="en", text="Title")
        record_human_version(
            db, entity_type="course", entity_id="cv-flip", field="title", locale="ru", text="Заголовок"
        )
        db.commit()
        loc = Localizer.build(db, [], source_locale="en", display_locale="ru")
        with caplog.at_level(logging.WARNING, logger="app.services.content_versions.compare"):
            set_compare_sample_rate(0.0)
            loc.pick("course", "cv-flip", "title", "Title")  # silent
            assert "content_versions dual-read" not in caplog.text
            set_compare_sample_rate(1.0)
            try:
                loc.pick("course", "cv-flip", "title", "Title")  # fires
                assert "content_versions dual-read" in caplog.text
            finally:
                set_compare_sample_rate(0.0)
