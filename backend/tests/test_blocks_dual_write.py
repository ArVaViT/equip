# ruff: noqa: RUF001
"""Phase 1d integration tests: chapter_block create/update dual-writes
into ``content_versions``.

Block content is HTML — the language detector ignores tag chars by
construction, so per-field detection works directly on the stored
markup without a pre-strip step. Pins the same supersession +
idempotency contract as courses / modules / chapters.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.models.chapter_block import ChapterBlock
from app.models.content_version import ContentVersion
from app.models.course import Chapter, Course, Module
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session


def _seed_chapter(db: Session, *, course_locale: str = "ru") -> str:
    """Course → module → chapter; return chapter id."""
    course = Course(
        id="course-blocks-dw",
        title="Учебник" if course_locale == "ru" else "Textbook",
        created_by=TEACHER_ID,
        status="draft",
        source_locale=course_locale,
    )
    module = Module(id="mod-blocks-dw", course_id=course.id, title="Раздел", order_index=0)
    chapter = Chapter(
        id="ch-blocks-dw",
        module_id=module.id,
        title="Глава",
        order_index=0,
        chapter_type="text",
    )
    db.add_all([course, module, chapter])
    db.commit()
    return chapter.id


def _active_rows(db: Session, block_id: str) -> list[ContentVersion]:
    return (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_type == "chapter_block",
            ContentVersion.entity_id == block_id,
            ContentVersion.superseded_by.is_(None),
        )
        .all()
    )


class TestCreateBlockDualWrite:
    def test_text_block_writes_content_row(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        resp = client.post(
            f"/api/v1/blocks/chapter/{chapter_id}",
            json={
                "block_type": "text",
                "order_index": 0,
                "content": "<p>Урок о первой главе книги Бытия.</p>",
            },
        )
        assert resp.status_code == 201, resp.text
        block_id = resp.json()["id"]
        rows = _active_rows(db, block_id)
        assert len(rows) == 1
        row = rows[0]
        assert row.field == "content"
        assert "Урок о первой главе" in row.text
        assert row.locale == "ru"
        assert row.origin == "human"
        assert row.authored_by == TEACHER_ID

    def test_quiz_block_with_no_content_skips_dual_write(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        # Quiz blocks reference a quiz_id and have NULL content; nothing
        # to write into content_versions.
        resp = client.post(
            f"/api/v1/blocks/chapter/{chapter_id}",
            json={"block_type": "file", "order_index": 0, "file_name": "syllabus.pdf"},
        )
        assert resp.status_code == 201, resp.text
        block_id = resp.json()["id"]
        assert _active_rows(db, block_id) == []

    def test_html_only_falls_back_to_course_source_locale(self, client: TestClient, db: Session):
        # ASCII non-letter content — detector returns None; falls back
        # to the parent course's source_locale (en here).
        chapter_id = _seed_chapter(db, course_locale="en")
        resp = client.post(
            f"/api/v1/blocks/chapter/{chapter_id}",
            json={"block_type": "text", "order_index": 0, "content": "<p>12345</p>"},
        )
        assert resp.status_code == 201, resp.text
        block_id = resp.json()["id"]
        rows = _active_rows(db, block_id)
        assert len(rows) == 1
        assert rows[0].locale == "en"


class TestUpdateBlockDualWrite:
    def test_content_change_supersedes_old_row(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        resp = client.post(
            f"/api/v1/blocks/chapter/{chapter_id}",
            json={
                "block_type": "text",
                "order_index": 0,
                "content": "<p>Первый вариант текста урока.</p>",
            },
        )
        block_id = resp.json()["id"]
        original = _active_rows(db, block_id)[0]
        resp = client.put(
            f"/api/v1/blocks/{block_id}",
            json={"content": "<p>Второй вариант текста урока.</p>"},
        )
        assert resp.status_code == 200, resp.text
        active = _active_rows(db, block_id)
        assert len(active) == 1
        assert "Второй вариант" in active[0].text
        db.refresh(original)
        assert original.superseded_by == active[0].id

    def test_non_content_patch_does_not_touch_content_versions(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        resp = client.post(
            f"/api/v1/blocks/chapter/{chapter_id}",
            json={
                "block_type": "text",
                "order_index": 0,
                "content": "<p>Стабильный текст.</p>",
            },
        )
        block_id = resp.json()["id"]
        ids_before = {r.id for r in _active_rows(db, block_id)}
        # PATCH that only flips order_index — content_versions stays put.
        resp = client.put(f"/api/v1/blocks/{block_id}", json={"order_index": 5})
        assert resp.status_code == 200, resp.text
        ids_after = {r.id for r in _active_rows(db, block_id)}
        assert ids_before == ids_after

    def test_identical_content_patch_is_idempotent(self, client: TestClient, db: Session):
        chapter_id = _seed_chapter(db)
        resp = client.post(
            f"/api/v1/blocks/chapter/{chapter_id}",
            json={
                "block_type": "text",
                "order_index": 0,
                "content": "<p>Текст урока.</p>",
            },
        )
        block_id = resp.json()["id"]
        original_id = _active_rows(db, block_id)[0].id
        # Re-PUT identical content — no version churn.
        resp = client.put(
            f"/api/v1/blocks/{block_id}",
            json={"content": "<p>Текст урока.</p>"},
        )
        assert resp.status_code == 200, resp.text
        current = _active_rows(db, block_id)
        assert len(current) == 1
        assert current[0].id == original_id


@pytest.fixture(autouse=True)
def _isolate(db: Session):
    """Make each test see a fresh ``content_versions`` slate for
    the seeded chapter so tests don't bleed assertions into each
    other when the same module/chapter ids reappear via the seed
    helper."""
    yield
    db.query(ContentVersion).filter(ContentVersion.entity_type == "chapter_block").delete()
    db.query(ChapterBlock).delete()
    db.commit()
