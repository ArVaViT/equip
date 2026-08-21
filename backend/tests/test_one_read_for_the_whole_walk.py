"""The check that spent the minute the pool needed.

Reading the author's rows for every field is what makes
``entity_field_specs`` answer from the database rather than from
whoever hydrated the entity — the fix that stopped the plan and the
check disagreeing. It also costs one round trip per entity, and
``course_translation_completeness`` walks every entity of a course on
every idle worker tick.

Measured against production on 2026-08-20: three live courses took 95.6
seconds to check, against a 180-second tick that reserves 96 for one
in-flight model call. Nothing was left over. The Daily Challenge pool
sweep runs after the course sweep on the same budget, so it could not
afford a single call, and 2,983 of its rows stayed at pipeline
generation 2 while the course tree finished at 10 — a third of the
corpus frozen by a check that had already spent the minute.

(The language detector was the other suspect and was measured out: 0.05
ms per field, 0.1 s for the whole walk. It was round trips.)

So the walk reads once. These tests hold the two things that makes true
— fewer statements, and the identical answer — plus the one it must not
break: a caller with a single entity still reads a single entity.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event

from app.services.content_versions import record_human_version
from app.services.translation.registry import (
    authored_texts_for_entities,
    entity_field_specs,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class _Counting:
    """Counts SQL statements issued while it is open."""

    def __init__(self, db: Session) -> None:
        self._bind = db.get_bind()
        self.count = 0

    def __enter__(self) -> _Counting:
        event.listen(self._bind, "before_cursor_execute", self._tick)
        return self

    def __exit__(self, *exc: object) -> None:
        event.remove(self._bind, "before_cursor_execute", self._tick)

    def _tick(self, *_args: object, **_kwargs: object) -> None:
        self.count += 1


class _Block:
    """A chapter_block, whose text column was dropped in Phase 5f — so
    its author's text can only come from a content_versions row, which
    is exactly the shape this is about."""

    def __init__(self, block_id: str) -> None:
        self.id = block_id
        self.content = None


@pytest.fixture
def authored_blocks(db: Session) -> list[_Block]:
    blocks = [_Block(str(uuid.uuid4())) for _ in range(12)]
    for index, block in enumerate(blocks):
        record_human_version(
            db,
            entity_type="chapter_block",
            entity_id=block.id,
            field="content",
            locale="ru",
            text=f"<p>Абзац номер {index}, написанный автором.</p>",
        )
    db.commit()
    return blocks


class TestTheAnswerIsUnchanged:
    def test_a_prefetched_walk_returns_exactly_what_a_per_entity_walk_returns(
        self, db: Session, authored_blocks: list[_Block]
    ) -> None:
        """The load-bearing property. An optimisation that quietly
        changes one of the two callers re-opens the loop the per-field
        read was added to close."""
        one_by_one = [entity_field_specs(db, "chapter_block", b, "ru") for b in authored_blocks]

        authored = authored_texts_for_entities(
            db,
            [("chapter_block", b.id) for b in authored_blocks],
            preferred_locale="ru",
        )
        in_bulk = [entity_field_specs(db, "chapter_block", b, "ru", authored) for b in authored_blocks]

        assert in_bulk == one_by_one
        assert all(specs for specs in in_bulk), "and it is not trivially equal because both are empty"

    def test_an_entity_the_prefetch_missed_still_gets_its_own_read(
        self, db: Session, authored_blocks: list[_Block]
    ) -> None:
        """A prefetch is a cache, not a contract. An entity the walk did
        not know about must not silently lose its author's text — that
        would be the blank-field bug again, wearing a different hat."""
        outsider = authored_blocks[0]
        authored = authored_texts_for_entities(
            db,
            [("chapter_block", b.id) for b in authored_blocks[1:]],
            preferred_locale="ru",
        )
        with_prefetch = entity_field_specs(db, "chapter_block", outsider, "ru", authored)
        assert [s.field for s in with_prefetch] == []

        without = entity_field_specs(db, "chapter_block", outsider, "ru")
        assert [s.text for s in without] == ["<p>Абзац номер 0, написанный автором.</p>"]


class TestItCostsFewerStatements:
    def test_twelve_entities_take_one_statement_instead_of_twelve(
        self, db: Session, authored_blocks: list[_Block]
    ) -> None:
        with _Counting(db) as per_entity:
            for block in authored_blocks:
                entity_field_specs(db, "chapter_block", block, "ru")

        with _Counting(db) as bulk:
            authored = authored_texts_for_entities(
                db,
                [("chapter_block", b.id) for b in authored_blocks],
                preferred_locale="ru",
            )
            for block in authored_blocks:
                entity_field_specs(db, "chapter_block", block, "ru", authored)

        assert per_entity.count == len(authored_blocks)
        assert bulk.count == 1, "one read for the whole walk"

    def test_a_single_entity_still_reads_a_single_entity(self, db: Session, authored_blocks: list[_Block]) -> None:
        """Saving one edited block must not read a whole course. The
        prefetch is opt-in for exactly this reason."""
        with _Counting(db) as counted:
            entity_field_specs(db, "chapter_block", authored_blocks[0], "ru")
        assert counted.count == 1


class TestTheBulkReadKeepsTheTieBreaks:
    def test_the_preferred_locale_wins_over_an_earlier_row(self, db: Session) -> None:
        """Two hand-written rows, two languages. Which one is the source
        must not depend on how it was read, or a field is planned from
        Russian on one tick and English on the next."""
        block = _Block(str(uuid.uuid4()))
        record_human_version(
            db,
            entity_type="chapter_block",
            entity_id=block.id,
            field="content",
            locale="en",
            text="<p>Written first, in English.</p>",
        )
        record_human_version(
            db,
            entity_type="chapter_block",
            entity_id=block.id,
            field="content",
            locale="ru",
            text="<p>Написано вторым, по-русски.</p>",
        )
        db.commit()

        authored = authored_texts_for_entities(db, [("chapter_block", block.id)], preferred_locale="ru")
        bulk = entity_field_specs(db, "chapter_block", block, "ru", authored)
        alone = entity_field_specs(db, "chapter_block", block, "ru")

        assert bulk == alone
        assert [s.source_locale for s in bulk] == ["ru"]

    def test_a_field_with_no_author_row_is_absent_either_way(self, db: Session) -> None:
        block = _Block(str(uuid.uuid4()))
        authored = authored_texts_for_entities(db, [("chapter_block", block.id)], preferred_locale="ru")
        assert entity_field_specs(db, "chapter_block", block, "ru", authored) == []
        assert entity_field_specs(db, "chapter_block", block, "ru") == []

    def test_nothing_to_read_costs_nothing(self, db: Session) -> None:
        with _Counting(db) as counted:
            assert authored_texts_for_entities(db, [], preferred_locale="ru") == {}
        assert counted.count == 0
