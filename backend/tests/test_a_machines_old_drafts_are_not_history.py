"""Retention for superseded machine translations.

The dangerous half of a delete on ``content_versions`` is not the row
that goes. It is the pointers left behind: ``superseded_by`` and
``source_version_id`` are both ``ON DELETE SET NULL``, and a row whose
``superseded_by`` is NULL *is* the live row. Delete carelessly and a
superseded translation is promoted back into the reader's page.

These tests pin that, the retention window, and the rule that human
history is never pruned at any age.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session  # noqa: TC002 — used by pytest fixtures at runtime

from app.models.content_version import ContentVersion
from app.services.content_versions.prune import prune_superseded_machine_translations

ENTITY = "chapter_block"
FIELD = "content"
LOCALE = "de"


@pytest.fixture(autouse=True)
def _tear_the_versions_down_leaf_first(db: Session):
    """Empty ``content_versions`` from the leaves inward after each test.

    Not tidiness — the teardown ``DROP TABLE`` fails without it. SQLite
    applies ``ON DELETE SET NULL`` row by row, so dropping a table whose
    rows point at each other momentarily leaves several rows in one group
    with ``superseded_by IS NULL``, and ``uniq_content_versions_active``
    refuses that. These tests are the only ones that build a group with
    more than one superseded row, which is why nothing needed this before.

    Deleting rows nothing points at, repeatedly, never produces that
    state. A pointer cycle has no leaves; break it by taking any row.
    """
    yield
    while True:
        rows = db.query(ContentVersion).all()
        if not rows:
            break
        pointed_at = {r.superseded_by for r in rows} | {r.source_version_id for r in rows}
        leaves = [r for r in rows if r.id not in pointed_at] or [rows[0]]
        for row in leaves:
            db.delete(row)
        db.commit()


def _version(
    db: Session,
    *,
    entity_id: str,
    text: str,
    origin: str = "mt",
    age_days: int = 90,
    superseded_by: uuid.UUID | None = None,
    source_version_id: uuid.UUID | None = None,
    locale: str = LOCALE,
    status: str = "ok",
) -> ContentVersion:
    when = datetime.now(UTC) - timedelta(days=age_days)
    row = ContentVersion(
        id=uuid.uuid4(),
        entity_type=ENTITY,
        entity_id=entity_id,
        field=FIELD,
        locale=locale,
        text=text,
        origin=origin,
        status=status,
        source_locale="ru",
        source_version_id=source_version_id,
        superseded_by=superseded_by,
        created_at=when,
        updated_at=when,
    )
    db.add(row)
    db.commit()
    return row


def _chain(db: Session, entity_id: str, *, drafts: int = 2, age_days: int = 90) -> ContentVersion:
    """``drafts`` superseded machine rows behind one live machine row."""
    live = _version(db, entity_id=entity_id, text="live", age_days=age_days)
    for n in range(drafts):
        _version(db, entity_id=entity_id, text=f"draft {n}", age_days=age_days, superseded_by=live.id)
    return live


def _ids(db: Session, entity_id: str) -> set[uuid.UUID]:
    return {row.id for row in db.query(ContentVersion).filter(ContentVersion.entity_id == entity_id).all()}


class TestWhatGoes:
    def test_superseded_machine_drafts_past_the_window_are_deleted(self, db: Session):
        entity = str(uuid.uuid4())
        live = _chain(db, entity, drafts=3)

        report = prune_superseded_machine_translations(db, older_than_days=30, max_groups=10)

        assert report.rows == 3
        assert report.groups == 1
        assert _ids(db, entity) == {live.id}

    def test_the_live_row_is_never_touched(self, db: Session):
        entity = str(uuid.uuid4())
        live = _chain(db, entity, drafts=1)

        prune_superseded_machine_translations(db, older_than_days=30, max_groups=10)

        survivor = db.query(ContentVersion).filter(ContentVersion.entity_id == entity).one()
        assert survivor.id == live.id
        assert survivor.superseded_by is None
        assert survivor.text == "live"


class TestWhatStays:
    def test_inside_the_retention_window_nothing_goes(self, db: Session):
        entity = str(uuid.uuid4())
        _chain(db, entity, drafts=2, age_days=3)

        report = prune_superseded_machine_translations(db, older_than_days=30, max_groups=10)

        assert report.rows == 0
        assert len(_ids(db, entity)) == 3

    def test_human_history_is_kept_at_any_age(self, db: Session):
        """93 rows on production, 65 kB, and the one thing in this table
        that no pipeline can reproduce."""
        entity = str(uuid.uuid4())
        live = _version(db, entity_id=entity, text="live", origin="human", age_days=900)
        old = _version(
            db, entity_id=entity, text="what they wrote first", origin="human", age_days=900, superseded_by=live.id
        )

        report = prune_superseded_machine_translations(db, older_than_days=30, max_groups=10)

        assert report.rows == 0
        assert _ids(db, entity) == {live.id, old.id}

    def test_a_group_with_no_live_row_is_left_alone(self, db: Session):
        """Deleting here would promote the tail of the chain to live —
        the ``ON DELETE SET NULL`` turning a superseded text into the
        served one."""
        entity = str(uuid.uuid4())
        head = _version(db, entity_id=entity, text="head", age_days=90)
        tail = _version(db, entity_id=entity, text="tail", age_days=90, superseded_by=head.id)
        # Make the head superseded too, pointing at nothing live.
        head.superseded_by = tail.id
        db.commit()

        report = prune_superseded_machine_translations(db, older_than_days=30, max_groups=10)

        assert report.rows == 0
        assert _ids(db, entity) == {head.id, tail.id}


class TestWhatPointsAtIt:
    def test_a_surviving_row_that_points_at_a_draft_pins_its_whole_group(self, db: Session):
        """``source_version_id`` — production has 162 rows translated
        from a machine row rather than a human one. Cutting the row out
        from under one would leave a translation whose source is NULL."""
        entity = str(uuid.uuid4())
        live = _chain(db, entity, drafts=2)
        draft = (
            db.query(ContentVersion)
            .filter(ContentVersion.entity_id == entity, ContentVersion.superseded_by == live.id)
            .first()
        )
        assert draft is not None
        _version(
            db,
            entity_id=str(uuid.uuid4()),
            text="translated from that draft",
            age_days=1,
            locale="uk",
            source_version_id=draft.id,
        )

        report = prune_superseded_machine_translations(db, older_than_days=30, max_groups=10)

        assert report.rows == 0
        assert report.skipped == 1
        assert len(_ids(db, entity)) == 3

    def test_a_human_row_superseded_by_a_machine_draft_pins_the_group(self, db: Session):
        """Nothing writes this shape today (production: zero human→mt
        successions), but the delete must not be the thing that finds
        out. Cutting the draft would set the human row's
        ``superseded_by`` to NULL and give the group two live rows —
        which the partial unique index then refuses to write past."""
        entity = str(uuid.uuid4())
        live = _version(db, entity_id=entity, text="live", age_days=90)
        draft = _version(db, entity_id=entity, text="draft", age_days=90, superseded_by=live.id)
        _version(
            db,
            entity_id=entity,
            text="what a person wrote",
            origin="human",
            age_days=900,
            superseded_by=draft.id,
        )

        report = prune_superseded_machine_translations(db, older_than_days=30, max_groups=10)

        assert report.rows == 0
        assert report.skipped == 1
        assert len(_ids(db, entity)) == 3


class TestBudget:
    def test_groups_are_taken_whole_and_capped_per_call(self, db: Session):
        """A budget that cut a group in half would leave the dangling
        pointer this module exists to avoid, so the cap counts groups."""
        entities = [str(uuid.uuid4()) for _ in range(4)]
        for entity in entities:
            _chain(db, entity, drafts=2)

        first = prune_superseded_machine_translations(db, older_than_days=30, max_groups=2)
        assert first.groups == 2
        assert first.rows == 4

        second = prune_superseded_machine_translations(db, older_than_days=30, max_groups=10)
        assert second.groups == 2
        assert second.rows == 4

        assert prune_superseded_machine_translations(db, older_than_days=30, max_groups=10).rows == 0

    def test_nothing_to_do_is_not_an_error(self, db: Session):
        report = prune_superseded_machine_translations(db, older_than_days=30, max_groups=10)
        assert report.rows == 0
        assert report.did_work is False
