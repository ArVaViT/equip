# ruff: noqa: RUF001
"""Tests for the ``content_versions`` write helpers.

These pin the contract that every dual-write call site in Phase 1
relies on. Three operations, each with a small set of well-defined
behaviours:

* ``record_human_version`` — insert; idempotent on identical text;
  supersedes existing human or MT; preserves history; MT-over-human
  never happens via this path.
* ``record_mt_version`` — insert; idempotent on identical text +
  source_hash; supersedes existing MT; NEVER supersedes a human
  row (the orchestrator's own guard plus belt-and-braces here).
* ``record_mt_failure`` — bumps attempts on the active MT row in
  place (no version history); promotes to failed_permanent on
  threshold; inserts a fresh failed row if nothing existed;
  refuses to touch a human row.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.content_version import (
    CONTENT_VERSION_MAX_ATTEMPTS,
    ContentVersion,
)
from app.services.content_versions import (
    record_human_version,
    record_mt_failure,
    record_mt_version,
)


@pytest.fixture
def db():
    from tests.conftest import test_engine

    session = Session(bind=test_engine)
    try:
        yield session
    finally:
        session.close()


def _active_for(db: Session, *, entity_id: str, field: str, locale: str) -> ContentVersion | None:
    return (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == "course",
            ContentVersion.entity_id == entity_id,
            ContentVersion.field == field,
            ContentVersion.locale == locale,
            ContentVersion.superseded_by.is_(None),
        )
        .one_or_none()
    )


def _all_for(db: Session, *, entity_id: str, field: str, locale: str) -> list[ContentVersion]:
    return (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == "course",
            ContentVersion.entity_id == entity_id,
            ContentVersion.field == field,
            ContentVersion.locale == locale,
        )
        .order_by(ContentVersion.created_at)
        .all()
    )


class TestRecordHumanVersion:
    def test_inserts_when_no_active_row(self, db: Session):
        row = record_human_version(
            db,
            entity_type="course",
            entity_id="hv-1",
            field="title",
            locale="ru",
            text="Заголовок",
        )
        db.commit()
        assert row.origin == "human"
        assert row.status == "ok"
        assert row.text == "Заголовок"
        assert row.superseded_by is None
        assert _active_for(db, entity_id="hv-1", field="title", locale="ru") is row

    def test_idempotent_on_identical_text(self, db: Session):
        first = record_human_version(
            db,
            entity_type="course",
            entity_id="hv-2",
            field="title",
            locale="ru",
            text="Один",
        )
        db.commit()
        second = record_human_version(
            db,
            entity_type="course",
            entity_id="hv-2",
            field="title",
            locale="ru",
            text="Один",
        )
        db.commit()
        # Same row, no supersession.
        assert second.id == first.id
        rows = _all_for(db, entity_id="hv-2", field="title", locale="ru")
        assert len(rows) == 1

    def test_supersedes_when_text_changes(self, db: Session):
        first = record_human_version(
            db,
            entity_type="course",
            entity_id="hv-3",
            field="title",
            locale="ru",
            text="v1",
        )
        db.commit()
        second = record_human_version(
            db,
            entity_type="course",
            entity_id="hv-3",
            field="title",
            locale="ru",
            text="v2",
        )
        db.commit()
        # Old row preserved + marked superseded by new row.
        db.refresh(first)
        assert first.superseded_by == second.id
        assert second.text == "v2"
        # Exactly one ACTIVE row.
        assert _active_for(db, entity_id="hv-3", field="title", locale="ru") is second
        # History preserved.
        assert {r.text for r in _all_for(db, entity_id="hv-3", field="title", locale="ru")} == {"v1", "v2"}

    def test_human_supersedes_existing_mt(self, db: Session):
        mt = record_mt_version(
            db,
            entity_type="course",
            entity_id="hv-4",
            field="title",
            locale="ru",
            text="MT-перевод",
            source_locale="en",
            source_hash="abc",
        )
        db.commit()
        human = record_human_version(
            db,
            entity_type="course",
            entity_id="hv-4",
            field="title",
            locale="ru",
            text="Человек написал",
        )
        db.commit()
        db.refresh(mt)
        assert mt.superseded_by == human.id
        active = _active_for(db, entity_id="hv-4", field="title", locale="ru")
        assert active is human
        assert active.origin == "human"

    def test_empty_text_rejected(self, db: Session):
        with pytest.raises(ValueError):
            record_human_version(
                db,
                entity_type="course",
                entity_id="hv-5",
                field="title",
                locale="ru",
                text="",
            )

    def test_records_authored_by_when_known(self, db: Session):
        from app.models.user import User, UserRole

        # ``authored_by`` is a real FK to ``profiles``; insert a real
        # user row so the FK check passes (it's enforced even on
        # SQLite when foreign_keys pragma is on, which it is for the
        # test engine).
        author = User(
            id=uuid.uuid4(),
            email="authored-by-test@example.com",
            full_name="Author",
            role=UserRole.TEACHER.value,
        )
        db.add(author)
        db.flush()
        row = record_human_version(
            db,
            entity_type="course",
            entity_id="hv-6",
            field="title",
            locale="ru",
            text="С автором",
            authored_by=author.id,
        )
        db.commit()
        assert row.authored_by == author.id


class TestRecordMtVersion:
    def test_inserts_when_no_active_row(self, db: Session):
        row = record_mt_version(
            db,
            entity_type="course",
            entity_id="mv-1",
            field="title",
            locale="ru",
            text="МТ",
            source_locale="en",
            source_hash="h1",
        )
        db.commit()
        assert row.origin == "mt"
        assert row.status == "ok"
        assert row.source_locale == "en"
        assert row.source_hash == "h1"

    def test_idempotent_when_text_and_hash_unchanged(self, db: Session):
        first = record_mt_version(
            db,
            entity_type="course",
            entity_id="mv-2",
            field="title",
            locale="ru",
            text="МТ",
            source_locale="en",
            source_hash="h1",
        )
        db.commit()
        second = record_mt_version(
            db,
            entity_type="course",
            entity_id="mv-2",
            field="title",
            locale="ru",
            text="МТ",
            source_locale="en",
            source_hash="h1",
        )
        db.commit()
        assert second.id == first.id
        assert len(_all_for(db, entity_id="mv-2", field="title", locale="ru")) == 1

    def test_supersedes_when_translation_changes(self, db: Session):
        first = record_mt_version(
            db,
            entity_type="course",
            entity_id="mv-3",
            field="title",
            locale="ru",
            text="МТ v1",
            source_locale="en",
            source_hash="h1",
        )
        db.commit()
        second = record_mt_version(
            db,
            entity_type="course",
            entity_id="mv-3",
            field="title",
            locale="ru",
            text="МТ v2",
            source_locale="en",
            source_hash="h2",
        )
        db.commit()
        db.refresh(first)
        assert first.superseded_by == second.id
        active = _active_for(db, entity_id="mv-3", field="title", locale="ru")
        assert active is second

    def test_refuses_to_supersede_human_row(self, db: Session):
        human = record_human_version(
            db,
            entity_type="course",
            entity_id="mv-4",
            field="title",
            locale="ru",
            text="Человек",
        )
        db.commit()
        returned = record_mt_version(
            db,
            entity_type="course",
            entity_id="mv-4",
            field="title",
            locale="ru",
            text="МТ хочет заменить",
            source_locale="en",
            source_hash="h1",
        )
        db.commit()
        # No supersession; human row still active and untouched.
        assert returned.id == human.id
        active = _active_for(db, entity_id="mv-4", field="title", locale="ru")
        assert active is human
        assert active.text == "Человек"

    def test_source_version_id_stored(self, db: Session):
        human = record_human_version(
            db,
            entity_type="course",
            entity_id="mv-5",
            field="title",
            locale="en",
            text="The source",
        )
        db.commit()
        mt = record_mt_version(
            db,
            entity_type="course",
            entity_id="mv-5",
            field="title",
            locale="ru",
            text="Источник",
            source_locale="en",
            source_hash="h1",
            source_version_id=human.id,
        )
        db.commit()
        assert mt.source_version_id == human.id


class TestRecordMtFailure:
    def test_inserts_failed_row_when_nothing_exists(self, db: Session):
        row = record_mt_failure(
            db,
            entity_type="course",
            entity_id="mf-1",
            field="title",
            locale="ru",
            source_locale="en",
            source_hash="h1",
        )
        db.commit()
        assert row.status == "failed"
        assert row.attempts == 1
        assert row.origin == "mt"
        assert row.text == ""

    def test_bumps_attempts_on_existing_failed_row(self, db: Session):
        first = record_mt_failure(
            db,
            entity_type="course",
            entity_id="mf-2",
            field="title",
            locale="ru",
            source_locale="en",
            source_hash="h1",
        )
        db.commit()
        second = record_mt_failure(
            db,
            entity_type="course",
            entity_id="mf-2",
            field="title",
            locale="ru",
            source_locale="en",
            source_hash="h1",
        )
        db.commit()
        # Same row updated in place — no version history for failures.
        assert second.id == first.id
        assert second.attempts == 2
        assert second.status == "failed"
        assert len(_all_for(db, entity_id="mf-2", field="title", locale="ru")) == 1

    def test_promotes_to_failed_permanent_at_threshold(self, db: Session):
        for _ in range(CONTENT_VERSION_MAX_ATTEMPTS):
            row = record_mt_failure(
                db,
                entity_type="course",
                entity_id="mf-3",
                field="title",
                locale="ru",
                source_locale="en",
                source_hash="h1",
            )
            db.commit()
        assert row.attempts == CONTENT_VERSION_MAX_ATTEMPTS
        assert row.status == "failed_permanent"

    def test_a_failed_attempt_does_not_take_a_good_translation_off_the_page(self, db: Session):
        """Production, 2026-08-20: the Gemini prepayment ran out in the
        middle of a rebuild, every call began returning 429, and 98
        finished translations vanished from the site in eight minutes —
        about seventy a minute. Nothing was wrong with any of them. The
        rows still held their text; they had simply been marked failed,
        and reads serve only ``status='ok'``.

        A translator we cannot reach today says nothing about whether
        what we published yesterday is fit to read."""
        good = record_mt_version(
            db,
            entity_type="course",
            entity_id="mf-outage",
            field="title",
            locale="de",
            text="Etwa vier Jahrhunderte",
            source_locale="ru",
            source_hash="h1",
        )
        db.commit()

        after = record_mt_failure(
            db,
            entity_type="course",
            entity_id="mf-outage",
            field="title",
            locale="de",
            source_locale="ru",
            source_hash="h1",
        )
        db.commit()

        assert after.id == good.id
        assert after.status == "ok", "the reader keeps the translation that was already fine"
        assert after.text == "Etwa vier Jahrhunderte"
        assert after.attempts == 1, "and the attempt is still counted, so the retry queue finds it"

    def test_an_outage_that_lasts_never_makes_a_good_translation_permanent(self, db: Session):
        """Five failures used to promote a row to ``failed_permanent``,
        which nothing retries — so an outage long enough to exhaust the
        retries withheld a correct translation for good. 80 rows reached
        that state in production before this was noticed."""
        for _ in range(CONTENT_VERSION_MAX_ATTEMPTS + 2):
            record_mt_version(
                db,
                entity_type="course",
                entity_id="mf-outage-long",
                field="title",
                locale="de",
                text="Etwa vier Jahrhunderte",
                source_locale="ru",
                source_hash="h1",
            )
            break
        db.commit()
        for _ in range(CONTENT_VERSION_MAX_ATTEMPTS + 2):
            row = record_mt_failure(
                db,
                entity_type="course",
                entity_id="mf-outage-long",
                field="title",
                locale="de",
                source_locale="ru",
                source_hash="h1",
            )
            db.commit()

        assert row.status == "ok", "however long the outage, the page keeps what it had"
        assert row.attempts == CONTENT_VERSION_MAX_ATTEMPTS + 2

    def test_a_row_with_nothing_to_serve_still_fails_the_way_it_always_did(self, db: Session):
        """The change is about protecting servable text, not about going
        quiet. A row that never had a translation — or holds the empty
        string a failure inserts — still fails, still counts its
        attempts, and still turns terminal at the threshold."""
        for _ in range(CONTENT_VERSION_MAX_ATTEMPTS):
            row = record_mt_failure(
                db,
                entity_type="course",
                entity_id="mf-empty",
                field="title",
                locale="de",
                source_locale="ru",
                source_hash="h1",
            )
            db.commit()

        assert row.status == "failed_permanent"
        assert row.attempts == CONTENT_VERSION_MAX_ATTEMPTS

    def test_does_not_touch_human_row(self, db: Session):
        human = record_human_version(
            db,
            entity_type="course",
            entity_id="mf-4",
            field="title",
            locale="ru",
            text="Человек",
        )
        db.commit()
        returned = record_mt_failure(
            db,
            entity_type="course",
            entity_id="mf-4",
            field="title",
            locale="ru",
            source_locale="en",
            source_hash="h1",
        )
        db.commit()
        # No change; human row untouched.
        assert returned.id == human.id
        assert returned.status == "ok"
        assert returned.attempts == 0
        assert len(_all_for(db, entity_id="mf-4", field="title", locale="ru")) == 1

    def test_a_failure_on_a_good_row_counts_the_attempt_and_keeps_serving(self, db: Session):
        """This test used to assert the opposite, and its own comment
        contained the mistake: it said students "fall back to the source
        until the retry succeeds". They do not. ``read.py`` sets
        ``fallback="none"`` whenever translation is enabled, so a row
        withheld for being non-ok leaves the reader with nothing at all.

        The behaviour was documented as chosen, and it was never
        examined against what a reader sees. Production examined it on
        2026-08-20."""
        ok = record_mt_version(
            db,
            entity_type="course",
            entity_id="mf-5",
            field="title",
            locale="ru",
            text="МТ ok",
            source_locale="en",
            source_hash="h1",
        )
        db.commit()
        returned = record_mt_failure(
            db,
            entity_type="course",
            entity_id="mf-5",
            field="title",
            locale="ru",
            source_locale="en",
            source_hash="h2",
        )
        db.commit()

        assert returned.id == ok.id
        assert returned.status == "ok", "the good translation stays on the page"
        assert returned.attempts == 1, "the attempt is counted all the same"
        assert returned.text == "МТ ok"
        assert returned.source_hash == "h2", "and the row knows which source it is now behind"
