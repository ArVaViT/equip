"""Tests for the Phase 2 dual-read comparator.

Pins every branch of the decision tree so the wiring in subsequent
sub-PRs can rely on a stable contract. The comparator is read-only
and side-effect-free; tests assert on returned ``MismatchReport``s.

Coverage map (one test per branch, plus normalisation edge cases):

* ``OK`` — both stores agree on the translated text
* ``LEGACY_ONLY_NO_BACKFILL`` — no cv rows for the entity at all
* ``BOTH_FALL_BACK_TO_SOURCE`` — cv has the field in another locale
  but not at display_locale; both paths fall back to source
* ``NEW_FAILED_STATUS`` — cv row at display_locale has status=failed;
  both paths fall back; texts match
* ``TEXT_DIFFERS`` — both paths returned a non-empty value but the
  two values disagree after whitespace normalisation
* ``LOCALE_DIVERGED`` — cv has the field but recorded under a
  different locale than the legacy path expected; texts happen to
  match (fall-back path on both sides)
* ``NEW_ONLY`` — legacy returned source; cv has a translation at
  display_locale
* ``ENTITY_DELETED`` — entity is soft-deleted but cv rows persist
* Whitespace normalisation — trailing newlines, collapsed spaces,
  empty-vs-None equivalence
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from app.services.content_versions import (
    INTERESTING_REASONS,
    MismatchReason,
    compare_resolved_text,
)
from app.services.content_versions.write import (
    record_human_version,
    record_mt_failure,
    record_mt_version,
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


def _unique_entity_id() -> str:
    return f"ent-{uuid.uuid4().hex[:10]}"


# ---------------------------------------------------------------------------
# OK — both stores agree
# ---------------------------------------------------------------------------


class TestOk:
    def test_both_stores_have_matching_translation_at_display_locale(self, db: Session):
        eid = _unique_entity_id()
        # Pre-seed cv with the same text the legacy resolver returned.
        record_human_version(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            locale="ru",
            text="Заголовок",
        )
        # Source row at en (so the resolver doesn't think we're already
        # at the source locale).
        record_human_version(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            locale="en",
            text="Title",
        )
        db.commit()
        report = compare_resolved_text(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            source_locale="en",
            display_locale="ru",
            base_source_text="Title",
            legacy_text="Заголовок",
        )
        assert report.reason is MismatchReason.OK
        assert report.is_interesting is False


# ---------------------------------------------------------------------------
# LEGACY_ONLY_NO_BACKFILL — cv empty for entity (expected pre-Phase-3)
# ---------------------------------------------------------------------------


class TestLegacyOnlyNoBackfill:
    def test_empty_content_versions_for_entity_is_not_interesting(self, db: Session):
        eid = _unique_entity_id()
        # No cv rows at all for this entity.
        report = compare_resolved_text(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            source_locale="en",
            display_locale="ru",
            base_source_text="Title",
            legacy_text="Заголовок",
        )
        assert report.reason is MismatchReason.LEGACY_ONLY_NO_BACKFILL
        assert report.is_interesting is False
        assert report.new_text is None
        assert report.new_status is None
        assert report.new_recorded_locale is None

    def test_legacy_no_backfill_does_not_flag_even_with_text_difference(self, db: Session):
        # Even when legacy returned a different text from what we'd
        # expect, missing-cv-entirely means we have nothing to compare
        # against and shouldn't flag.
        eid = _unique_entity_id()
        report = compare_resolved_text(
            db,
            entity_type="quiz",
            entity_id=eid,
            field="question_text",
            source_locale="ru",
            display_locale="en",
            base_source_text="Question",
            legacy_text="Pytanie",  # arbitrary
        )
        assert report.reason is MismatchReason.LEGACY_ONLY_NO_BACKFILL


# ---------------------------------------------------------------------------
# BOTH_FALL_BACK_TO_SOURCE — no overlay at display_locale, both fall back
# ---------------------------------------------------------------------------


class TestBothFallBackToSource:
    def test_no_overlay_either_side_at_display_locale(self, db: Session):
        eid = _unique_entity_id()
        # cv has en (the source) only — no ru translation.
        record_human_version(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            locale="en",
            text="Title",
        )
        db.commit()
        report = compare_resolved_text(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            source_locale="en",
            display_locale="ru",
            base_source_text="Title",
            legacy_text="Title",  # legacy also fell back
        )
        assert report.reason is MismatchReason.BOTH_FALL_BACK_TO_SOURCE
        assert report.is_interesting is False


# ---------------------------------------------------------------------------
# NEW_FAILED_STATUS — cv row at display_locale is failed; both fall back
# ---------------------------------------------------------------------------


class TestNewFailedStatus:
    def test_failed_at_display_locale_falls_back_and_matches_legacy(self, db: Session):
        eid = _unique_entity_id()
        record_mt_failure(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            locale="ru",
            source_locale="en",
            source_hash="h1",
        )
        db.commit()
        report = compare_resolved_text(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            source_locale="en",
            display_locale="ru",
            base_source_text="Title",
            legacy_text="Title",
        )
        assert report.reason is MismatchReason.NEW_FAILED_STATUS
        assert report.new_status == "failed"
        assert report.is_interesting is False  # known-acceptable

    def test_failed_at_display_locale_but_texts_disagree_flags_text_differs(self, db: Session):
        eid = _unique_entity_id()
        record_mt_failure(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            locale="ru",
            source_locale="en",
            source_hash="h1",
        )
        db.commit()
        report = compare_resolved_text(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            source_locale="en",
            display_locale="ru",
            base_source_text="Title",
            # Legacy somehow returned something other than the source —
            # that's a real bug we want to know about.
            legacy_text="Заголовок",
        )
        assert report.reason is MismatchReason.TEXT_DIFFERS
        assert report.new_status == "failed"
        assert report.is_interesting is True


# ---------------------------------------------------------------------------
# TEXT_DIFFERS — both paths returned text but they disagree
# ---------------------------------------------------------------------------


class TestTextDiffers:
    def test_text_differs_at_display_locale(self, db: Session):
        eid = _unique_entity_id()
        record_human_version(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            locale="ru",
            text="Версия из cv",
        )
        record_human_version(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            locale="en",
            text="Title",
        )
        db.commit()
        report = compare_resolved_text(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            source_locale="en",
            display_locale="ru",
            base_source_text="Title",
            legacy_text="Версия из legacy",
        )
        assert report.reason is MismatchReason.TEXT_DIFFERS
        assert report.is_interesting is True
        assert report.legacy_text == "Версия из legacy"
        assert report.new_text == "Версия из cv"


# ---------------------------------------------------------------------------
# LOCALE_DIVERGED — cv has the field but at an unexpected locale
# ---------------------------------------------------------------------------


class TestLocaleDiverged:
    def test_field_recorded_at_unexpected_locale(self, db: Session):
        # Course says source_locale=ru, but a chapter title was authored
        # in English ("Genesis"). Per-field detection put the cv row at
        # en, not ru. The legacy resolver returns the source column as-is
        # (no ru overlay needed because display == source); the cv row is
        # at neither the display nor source locale. That's the genuine
        # LOCALE_DIVERGED signal — recording locale != either expected.
        eid = _unique_entity_id()
        record_human_version(
            db,
            entity_type="chapter",
            entity_id=eid,
            field="title",
            locale="en",  # cv recorded under en
            text="Genesis",
        )
        db.commit()
        report = compare_resolved_text(
            db,
            entity_type="chapter",
            entity_id=eid,
            field="title",
            source_locale="ru",  # course's declared source
            display_locale="ru",  # user asked for the source language
            base_source_text="Genesis",
            legacy_text="Genesis",  # legacy returned source as-is
        )
        assert report.reason is MismatchReason.LOCALE_DIVERGED
        assert report.new_recorded_locale == "en"
        assert report.is_interesting is True

    def test_cv_at_source_locale_is_benign_fallback(self, db: Session):
        # Normal case: course is en, chapter title is English, cv
        # recorded the field under en. User asks for ru → both stores
        # fall back to source. Recording at source_locale = not diverged.
        eid = _unique_entity_id()
        record_human_version(
            db,
            entity_type="chapter",
            entity_id=eid,
            field="title",
            locale="en",
            text="Title",
        )
        db.commit()
        report = compare_resolved_text(
            db,
            entity_type="chapter",
            entity_id=eid,
            field="title",
            source_locale="en",
            display_locale="ru",
            base_source_text="Title",
            legacy_text="Title",
        )
        assert report.reason is MismatchReason.BOTH_FALL_BACK_TO_SOURCE


# ---------------------------------------------------------------------------
# NEW_ONLY — legacy returned source; cv has a translation
# ---------------------------------------------------------------------------


class TestNewOnly:
    def test_legacy_fell_back_but_cv_has_translation(self, db: Session):
        eid = _unique_entity_id()
        # cv has both source AND translation; legacy somehow missed
        # the overlay row.
        record_human_version(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            locale="en",
            text="Title",
        )
        record_mt_version(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            locale="ru",
            text="Заголовок",
            source_locale="en",
            source_hash="h1",
        )
        db.commit()
        report = compare_resolved_text(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            source_locale="en",
            display_locale="ru",
            base_source_text="Title",
            legacy_text="Title",  # legacy returned source (missed overlay)
        )
        assert report.reason is MismatchReason.NEW_ONLY
        assert report.new_text == "Заголовок"
        assert report.is_interesting is True


# ---------------------------------------------------------------------------
# ENTITY_DELETED — entity gone but cv rows survive
# ---------------------------------------------------------------------------


class TestEntityDeleted:
    def test_deleted_entity_with_surviving_cv_rows_flagged(self, db: Session):
        eid = _unique_entity_id()
        record_human_version(
            db,
            entity_type="chapter",
            entity_id=eid,
            field="title",
            locale="ru",
            text="Глава",
        )
        db.commit()
        report = compare_resolved_text(
            db,
            entity_type="chapter",
            entity_id=eid,
            field="title",
            source_locale="en",
            display_locale="ru",
            base_source_text=None,
            legacy_text=None,
            entity_deleted=True,
        )
        assert report.reason is MismatchReason.ENTITY_DELETED
        assert report.is_interesting is True

    def test_deleted_entity_with_no_cv_rows_not_flagged(self, db: Session):
        # If there were no cv rows AND the entity is deleted, it's the
        # legacy-only-no-backfill case, not an orphan. Treat as benign.
        eid = _unique_entity_id()
        report = compare_resolved_text(
            db,
            entity_type="chapter",
            entity_id=eid,
            field="title",
            source_locale="en",
            display_locale="ru",
            base_source_text=None,
            legacy_text=None,
            entity_deleted=True,
        )
        assert report.reason is MismatchReason.LEGACY_ONLY_NO_BACKFILL


# ---------------------------------------------------------------------------
# Whitespace / normalisation edges
# ---------------------------------------------------------------------------


class TestWhitespaceNormalisation:
    def test_trailing_newline_does_not_count_as_mismatch(self, db: Session):
        eid = _unique_entity_id()
        record_human_version(
            db,
            entity_type="course",
            entity_id=eid,
            field="description",
            locale="ru",
            text="Описание",
        )
        record_human_version(
            db,
            entity_type="course",
            entity_id=eid,
            field="description",
            locale="en",
            text="Description",
        )
        db.commit()
        report = compare_resolved_text(
            db,
            entity_type="course",
            entity_id=eid,
            field="description",
            source_locale="en",
            display_locale="ru",
            base_source_text="Description",
            legacy_text="Описание\n",  # legacy retains trailing newline
        )
        assert report.reason is MismatchReason.OK

    def test_collapsed_whitespace_does_not_count_as_mismatch(self, db: Session):
        eid = _unique_entity_id()
        record_human_version(
            db,
            entity_type="chapter_block",
            entity_id=eid,
            field="content",
            locale="ru",
            text="Слово  второе",
        )
        record_human_version(
            db,
            entity_type="chapter_block",
            entity_id=eid,
            field="content",
            locale="en",
            text="Word two",
        )
        db.commit()
        report = compare_resolved_text(
            db,
            entity_type="chapter_block",
            entity_id=eid,
            field="content",
            source_locale="en",
            display_locale="ru",
            base_source_text="Word two",
            legacy_text="Слово второе",  # single space — equal after normalise
        )
        assert report.reason is MismatchReason.OK

    def test_empty_vs_none_treated_as_equal(self, db: Session):
        eid = _unique_entity_id()
        # No cv row at all for this entity.
        report = compare_resolved_text(
            db,
            entity_type="course",
            entity_id=eid,
            field="description",
            source_locale="en",
            display_locale="ru",
            base_source_text=None,
            legacy_text="",
        )
        # No cv rows → LEGACY_ONLY_NO_BACKFILL regardless of text shape.
        assert report.reason is MismatchReason.LEGACY_ONLY_NO_BACKFILL


# ---------------------------------------------------------------------------
# Structured logging fields
# ---------------------------------------------------------------------------


class TestLogFields:
    def test_log_fields_have_expected_shape(self, db: Session):
        eid = _unique_entity_id()
        record_human_version(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            locale="ru",
            text="Заголовок",
        )
        record_human_version(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            locale="en",
            text="Title",
        )
        db.commit()
        report = compare_resolved_text(
            db,
            entity_type="course",
            entity_id=eid,
            field="title",
            source_locale="en",
            display_locale="ru",
            base_source_text="Title",
            legacy_text="Foo",  # text differs
        )
        fields = report.to_log_fields()
        assert fields["cv_compare_reason"] == "text_differs"
        assert fields["cv_compare_entity_type"] == "course"
        assert fields["cv_compare_entity_id"] == eid
        assert fields["cv_compare_field"] == "title"
        assert fields["cv_compare_display_locale"] == "ru"
        assert fields["cv_compare_new_status"] == "ok"
        # Never dump full text into structured fields.
        assert "Заголовок" not in str(fields)
        assert "Title" not in str(fields)
        # Lengths are surfaced for triage.
        assert fields["cv_compare_legacy_text_len"] == "3"
        assert fields["cv_compare_new_text_len"] == "9"  # len("Заголовок")


# ---------------------------------------------------------------------------
# INTERESTING_REASONS set sanity
# ---------------------------------------------------------------------------


class TestInterestingReasonsSet:
    def test_interesting_set_matches_decision_tree(self):
        # The actionable reasons that should trigger structured warnings
        # in the Phase 2 wiring. Pin the set so adding/removing a reason
        # forces a deliberate choice.
        expected = frozenset(
            {
                MismatchReason.TEXT_DIFFERS,
                MismatchReason.LOCALE_DIVERGED,
                MismatchReason.NEW_ONLY,
                MismatchReason.ENTITY_DELETED,
            }
        )
        assert expected == INTERESTING_REASONS
