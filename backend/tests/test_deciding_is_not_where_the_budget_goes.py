"""The plan is decided in a fixed number of queries, not one per row.

Phase one answers "what still needs asking?" — human rows are left
alone, current rows are skipped, an identical text already translated
elsewhere is reused. All of that is database work, and it used to be
two round trips per task.

That reads fine for a course with thirty fields and stops being a
detail at three thousand. When the whole catalogue became due for
re-translation at once, the worker spent its entire 180-second budget
deciding and never reached a single Gemini call: every tick ran the
full two minutes, made no progress, and reported "paused". Nine
thousand rows sat untouched while the queue looked busy.

So the reads are batched, and this test holds the line: the query count
must not scale with the number of tasks. It is the kind of property
that is obvious in review and invisible in production until a course is
large enough to matter.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import event

from app.services.translation.executor import TranslationTask, _load_twins
from app.services.translation.stores import LIVE_STORE

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _tasks(count: int) -> list[TranslationTask]:
    return [
        TranslationTask(
            entity_type="chapter_block",
            entity_id=str(uuid.uuid4()),
            field="content",
            source_locale="ru",
            target_locale="de",
            text=f"Урок номер {index}",
            content_kind="html",
            source_hash=f"hash-{index}",
        )
        for index in range(count)
    ]


@pytest.fixture
def counted(db: Session):
    """Count every statement the session sends while inside the block."""
    seen: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", before)
    yield seen
    event.remove(db.get_bind(), "before_cursor_execute", before)


class TestReadingTheWorldIsBounded:
    def test_looking_up_existing_rows_does_not_scale_with_the_plan(self, db: Session, counted: list[str]) -> None:
        keys = [(t.entity_type, t.entity_id, t.field, t.target_locale) for t in _tasks(400)]
        LIVE_STORE.active_rows(db, keys)
        # 400 keys, chunked at 500 — one statement. The old shape sent
        # 400. The assertion is deliberately loose: what matters is that
        # it is a small constant, not that it is exactly one.
        assert len(counted) <= 2, f"{len(counted)} statements for 400 keys"

    def test_looking_up_twins_does_not_scale_with_the_plan(self, db: Session, counted: list[str]) -> None:
        _load_twins(db, _tasks(400))
        assert len(counted) <= 2, f"{len(counted)} statements for 400 tasks"

    def test_ten_times_the_tasks_is_not_ten_times_the_queries(self, db: Session, counted: list[str]) -> None:
        small = [(t.entity_type, t.entity_id, t.field, t.target_locale) for t in _tasks(40)]
        LIVE_STORE.active_rows(db, small)
        after_small = len(counted)

        large = [(t.entity_type, t.entity_id, t.field, t.target_locale) for t in _tasks(400)]
        LIVE_STORE.active_rows(db, large)
        after_large = len(counted) - after_small

        assert after_large <= after_small + 1

    def test_an_empty_plan_asks_nothing(self, db: Session, counted: list[str]) -> None:
        LIVE_STORE.active_rows(db, [])
        _load_twins(db, [])
        assert counted == []
