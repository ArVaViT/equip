"""The staged store asks which source an edit replaces once, not per field.

``StagedStore.active_rows`` keeps a live hand translation out of the
machine's reach — except the row a held edit in another language is
about to replace. Finding that row went field by field: two or three
round trips for each field with a live human row, and every field has
one (its source). On a course with a few hundred blocks the worker paid
that on every tick.

These tests hold the read count flat as the course grows, and the answer
unchanged: the replaced source is still not reported, a hand translation
in a third language still is.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import event

from app.models.course import Course, CourseStatus
from app.models.staged_content_version import StagedContentVersion
from app.models.user import User
from app.services.content_versions.write import record_human_version
from app.services.translation.stores import StagedStore
from tests.conftest import TEACHER_ID

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


def _course(db: Session) -> str:
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="teacher@example.com", full_name="T", role="teacher"))
        db.commit()
    course = Course(
        id=f"course-{uuid.uuid4().hex[:8]}",
        status=CourseStatus.PUBLISHED,
        source_locale="ru",
        created_by=TEACHER_ID,
    )
    db.add(course)
    db.commit()
    return str(course.id)


def _block_edited_in_english(db: Session, course_id: str, *, hand_de: bool = False) -> str:
    """A block whose Russian source a held English edit will replace."""
    block_id = str(uuid.uuid4())
    record_human_version(
        db, entity_type="chapter_block", entity_id=block_id, field="content", locale="ru", text="Первое послание"
    )
    if hand_de:
        record_human_version(
            db, entity_type="chapter_block", entity_id=block_id, field="content", locale="de", text="Der erste Brief"
        )
    db.add(
        StagedContentVersion(
            entity_type="chapter_block",
            entity_id=block_id,
            field="content",
            locale="en",
            course_id=course_id,
            text="The first letter, read slowly",
            origin="human",
            status="ok",
            source_locale="en",
        )
    )
    db.commit()
    return block_id


def _keys(block_ids: list[str]) -> list[tuple[str, str, str, str]]:
    return [("chapter_block", b, "content", locale) for b in block_ids for locale in ("ru", "de", "uk")]


def _reads(db: Session, course_id: str, block_ids: list[str]) -> int:
    store = StagedStore(course_id)
    with _Counting(db) as counter:
        store.active_rows(db, _keys(block_ids))
    return counter.count


def test_the_reads_do_not_grow_with_the_course(db: Session) -> None:
    course_id = _course(db)
    small = [_block_edited_in_english(db, course_id) for _ in range(2)]
    large = small + [_block_edited_in_english(db, course_id) for _ in range(20)]

    # Before: 7 reads for two fields, 47 for twenty-two.
    assert _reads(db, course_id, large) == _reads(db, course_id, small)


def test_the_replaced_source_is_not_a_hand_translation_but_a_third_language_is(db: Session) -> None:
    course_id = _course(db)
    plain = _block_edited_in_english(db, course_id)
    with_de = _block_edited_in_english(db, course_id, hand_de=True)

    found = StagedStore(course_id).active_rows(db, _keys([plain, with_de]))

    assert set(found) == {("chapter_block", with_de, "content", "de")}
    assert found[("chapter_block", with_de, "content", "de")].text == "Der erste Brief"


def test_a_single_field_answers_as_it_did(db: Session) -> None:
    course_id = _course(db)
    block_id = _block_edited_in_english(db, course_id, hand_de=True)
    store = StagedStore(course_id)

    ru = store.active_row(db, entity_type="chapter_block", entity_id=block_id, field="content", locale="ru")
    de = store.active_row(db, entity_type="chapter_block", entity_id=block_id, field="content", locale="de")

    assert ru is None
    assert de is not None and de.origin == "human"
