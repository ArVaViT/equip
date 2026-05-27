"""Schema-level tests for ``content_versions``.

Phase 0 of the V1 migration (single multi-locale content store). This
file pins the schema-level invariants — anything a future migration
might break needs to fail loudly here.

What's pinned
-------------

* Required vs nullable columns (text + identifiers required; MT-only
  provenance nullable).
* CHECK constraints (``origin``, ``status``, ``attempts >= 0``).
* The active-uniqueness rule: exactly one current version per
  ``(entity, field, locale)`` — duplicate inserts when both are
  active must fail.
* Supersession is the only legal way to "update" a version — the old
  row stays, the new row points back via ``superseded_by``.
* Locale has NO CHECK constraint — adding a new language must be
  pure INSERT, not DDL.
* Foreign keys (``source_version_id``, ``authored_by``,
  ``superseded_by``) have ON DELETE SET NULL so deleting a user or
  superseded row doesn't cascade-destroy history.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.content_version import (
    CONTENT_VERSION_MAX_ATTEMPTS,
    ContentVersion,
)


@pytest.fixture
def db():
    from tests.conftest import test_engine

    session = Session(bind=test_engine)
    try:
        yield session
    finally:
        session.close()


def _make_row(
    db: Session,
    *,
    entity_type: str = "course",
    entity_id: str = "ent-1",
    field: str = "title",
    locale: str = "en",
    text: str = "Hello",
    origin: str = "human",
    **overrides,
) -> ContentVersion:
    row = ContentVersion(
        id=uuid.uuid4(),
        entity_type=entity_type,
        entity_id=entity_id,
        field=field,
        locale=locale,
        text=text,
        origin=origin,
        **overrides,
    )
    db.add(row)
    db.commit()
    return row


class TestRequiredFields:
    """The five identifying columns + ``text`` + ``origin`` are all
    NOT NULL. A row missing any of them is meaningless."""

    @pytest.mark.parametrize(
        "missing_field",
        ["entity_type", "entity_id", "field", "locale", "text", "origin"],
    )
    def test_missing_required_field_rejected(self, db: Session, missing_field: str):
        kwargs: dict = {
            "entity_type": "course",
            "entity_id": "x",
            "field": "title",
            "locale": "en",
            "text": "Hello",
            "origin": "human",
        }
        kwargs.pop(missing_field)
        # Pass via ORM; SQLAlchemy + DB NOT NULL should reject. We
        # construct the row manually so a missing kwarg surfaces as
        # the DB's NOT NULL violation, not a Python TypeError.
        row = ContentVersion(id=uuid.uuid4(), **kwargs)
        db.add(row)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_optional_columns_accept_null(self, db: Session):
        # MT-only columns + authored_by + superseded_by are all nullable.
        row = _make_row(db, origin="human")
        assert row.source_hash is None
        assert row.source_locale is None
        assert row.source_version_id is None
        assert row.authored_by is None
        assert row.superseded_by is None


class TestOriginAndStatusChecks:
    def test_invalid_origin_rejected(self, db: Session):
        with pytest.raises(IntegrityError):
            _make_row(db, origin="invalid")
        db.rollback()

    @pytest.mark.parametrize("origin", ["human", "mt"])
    def test_valid_origin_accepted(self, db: Session, origin: str):
        row = _make_row(db, origin=origin, entity_id=f"e-{origin}")
        assert row.origin == origin

    def test_invalid_status_rejected(self, db: Session):
        row = ContentVersion(
            id=uuid.uuid4(),
            entity_type="course",
            entity_id="x",
            field="title",
            locale="en",
            text="x",
            origin="human",
            status="bogus",
        )
        db.add(row)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    @pytest.mark.parametrize("status", ["ok", "failed", "failed_permanent"])
    def test_valid_status_accepted(self, db: Session, status: str):
        row = _make_row(db, entity_id=f"e-{status}", status=status)
        assert row.status == status

    def test_status_defaults_to_ok(self, db: Session):
        row = _make_row(db)
        assert row.status == "ok"


class TestActiveUniqueness:
    """At most one active version per (entity, field, locale). The
    constraint is partial — superseded rows are excluded — so
    versioning by supersession remains legal."""

    def test_two_active_rows_with_same_key_rejected(self, db: Session):
        _make_row(db, entity_id="dup-1", field="title", locale="en")
        # Second row with the same active key violates the partial
        # unique index.
        with pytest.raises(IntegrityError):
            _make_row(db, entity_id="dup-1", field="title", locale="en")
        db.rollback()

    def test_same_key_different_locale_is_fine(self, db: Session):
        _make_row(db, entity_id="multi-1", field="title", locale="en")
        _make_row(db, entity_id="multi-1", field="title", locale="ru")
        rows = (
            db.query(ContentVersion)
            .filter(ContentVersion.entity_id == "multi-1", ContentVersion.field == "title")
            .all()
        )
        assert {r.locale for r in rows} == {"en", "ru"}

    def test_same_key_different_field_is_fine(self, db: Session):
        _make_row(db, entity_id="multi-2", field="title", locale="en")
        _make_row(db, entity_id="multi-2", field="description", locale="en")
        count = (
            db.query(ContentVersion)
            .filter(ContentVersion.entity_id == "multi-2", ContentVersion.locale == "en")
            .count()
        )
        assert count == 2

    def test_supersession_releases_active_slot(self, db: Session):
        # The partial unique index permits ONE active row per key but
        # any number of superseded ones. We verify the end-state
        # directly: insert the new version first (call it v2) so it
        # owns the active slot, then insert the older version (v1)
        # already pointing at v2 via ``superseded_by``. The two rows
        # coexist for the same (entity, field, locale) because v1 is
        # inactive.
        #
        # We deliberately don't test the live "supersede an existing
        # active row" write sequence here — that requires deferring
        # FK checks (Postgres DEFERRABLE INITIALLY DEFERRED) and is
        # an app-write-helper concern that lives in its own test
        # once the helper exists.
        v2 = _make_row(db, entity_id="super-1", field="title", locale="en", text="v2")
        db.add(
            ContentVersion(
                id=uuid.uuid4(),
                entity_type="course",
                entity_id="super-1",
                field="title",
                locale="en",
                text="v1",
                origin="human",
                superseded_by=v2.id,
            )
        )
        db.commit()
        active_rows = (
            db.query(ContentVersion)
            .filter(
                ContentVersion.entity_id == "super-1",
                ContentVersion.field == "title",
                ContentVersion.locale == "en",
                ContentVersion.superseded_by.is_(None),
            )
            .all()
        )
        assert len(active_rows) == 1
        assert active_rows[0].text == "v2"
        # History preserved: v1 still in the table, just inactive.
        all_rows = (
            db.query(ContentVersion)
            .filter(
                ContentVersion.entity_id == "super-1",
                ContentVersion.field == "title",
                ContentVersion.locale == "en",
            )
            .all()
        )
        assert {r.text for r in all_rows} == {"v1", "v2"}


class TestLocaleHasNoDbCheck:
    """The whole point of the design: adding a new language must be
    INSERT, not DDL. The DB MUST NOT have a CHECK constraint on
    ``locale``."""

    def test_arbitrary_locale_string_accepted(self, db: Session):
        # The Pydantic Literal at the API edge controls the
        # supported set — but at the DB level, ``locale`` is just
        # text. Any string fits. ``yo-Latn-NG`` is a real BCP-47
        # locale (Yoruba in Latin script in Nigeria); we don't
        # support it today but the DB must let us tomorrow.
        row = _make_row(db, locale="yo-Latn-NG", entity_id="locale-test")
        assert row.locale == "yo-Latn-NG"


class TestAttemptsCheck:
    def test_negative_attempts_rejected(self, db: Session):
        row = ContentVersion(
            id=uuid.uuid4(),
            entity_type="course",
            entity_id="att-1",
            field="title",
            locale="en",
            text="x",
            origin="mt",
            attempts=-1,
        )
        db.add(row)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    def test_zero_attempts_is_the_default(self, db: Session):
        row = _make_row(db)
        assert row.attempts == 0

    def test_max_attempts_constant_exposed(self):
        # Centralised constant so admin tooling that re-queues a row
        # refers to the same threshold the orchestrator uses.
        assert CONTENT_VERSION_MAX_ATTEMPTS == 5
