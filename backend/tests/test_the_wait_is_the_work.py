"""The pipeline spends its life waiting, so it waits in parallel.

Measured with an instant fake provider, so the only thing being timed
was our own code: a 180-call pass costs about **1 ms per call** in tree
walking, detection, skip decisions, validation and writes. The other
420 ms is a socket. One call at a time, a real 2,610-call course was
some forty minutes of almost entirely idle waiting.

These tests hold the two properties that make the concurrent path safe
to keep: it is genuinely concurrent, and it is concurrent across the
whole course rather than within one entity — which is the difference
between batches of three and batches of eight.
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.chapter_block import ChapterBlock
from app.models.course import Chapter, Course, Module
from app.models.user import User
from app.services.content_versions.write import record_human_version
from app.services.translation.course_pipeline import plan_course_tasks, translate_course_content
from app.services.translation.executor import DEFAULT_MAX_WORKERS
from app.services.translation.protocol import TranslationResult
from app.services.translation.service import reset_translation_provider_cache
from tests._fake_translation import fake_translate
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


class _SlowProvider:
    """Stands in for the network: each call costs real wall time, and
    the class records how many were ever in flight at once."""

    name = "slow"

    def __init__(self, seconds: float = 0.05) -> None:
        self.seconds = seconds
        self.calls = 0
        self.in_flight = 0
        self.peak_in_flight = 0

    def translate(self, request):
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        self.calls += 1
        try:
            time.sleep(self.seconds)
            return TranslationResult(
                text=fake_translate(request.text, target_locale=request.target_locale),
                model="fake",
            )
        finally:
            self.in_flight -= 1


def _course_with_blocks(db: Session, blocks: int) -> Course:
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="t@example.com", role="teacher"))
        db.commit()
    course = Course(
        id=f"speed-{uuid.uuid4().hex[:8]}",
        status="published",
        source_locale="ru",
        created_by=TEACHER_ID,
    )
    db.add(course)
    db.commit()
    module = Module(id=f"m-{uuid.uuid4().hex[:8]}", course_id=course.id, title="Модуль", order_index=0)
    db.add(module)
    db.commit()
    chapter = Chapter(
        id=f"ch-{uuid.uuid4().hex[:8]}",
        module_id=module.id,
        title="Урок",
        order_index=0,
        chapter_type="reading",
    )
    db.add(chapter)
    db.commit()
    for i in range(blocks):
        block = ChapterBlock(chapter_id=chapter.id, block_type="text", order_index=i)
        db.add(block)
        db.flush()
        record_human_version(
            db,
            entity_type="chapter_block",
            entity_id=str(block.id),
            field="content",
            locale="ru",
            text=f"<p>Абзац {i}: Павел пишет церкви про единство.</p>",
        )
    db.commit()
    return course


def test_the_course_is_planned_as_one_list_not_one_entity_at_a_time(db: Session):
    """Ten blocks are thirty tasks, planned together.

    Planning per entity capped the width at a single field's three
    languages no matter how many workers were free — the reason the
    first concurrent version only ran 2.4x faster instead of 6x.
    """
    course = _course_with_blocks(db, blocks=10)

    tasks = plan_course_tasks(db, course)

    block_tasks = [t for t in tasks if t.entity_type == "chapter_block"]
    assert len(block_tasks) == 30, "ten blocks into three other languages"
    assert len({t.entity_id for t in block_tasks}) == 10, "all ten entities in one plan"


def test_calls_actually_overlap(db: Session):
    """The point of the exercise. If nothing ever overlapped, the peak
    in flight would be one and the pass would be as slow as before."""
    course = _course_with_blocks(db, blocks=10)
    provider = _SlowProvider()

    translate_course_content(db, course, provider=provider)

    assert provider.calls > 0
    assert provider.peak_in_flight > 1, "calls never overlapped — the pass is still serial"
    assert provider.peak_in_flight <= DEFAULT_MAX_WORKERS, "more in flight than the configured width"


def test_a_pass_beats_doing_the_same_work_in_series(db: Session):
    """Wall clock, measured rather than asserted from the design: the
    same calls at the same cost, done concurrently, must take
    materially less time than adding them up."""
    course = _course_with_blocks(db, blocks=8)
    provider = _SlowProvider(seconds=0.05)

    started = time.monotonic()
    translate_course_content(db, course, provider=provider)
    elapsed = time.monotonic() - started

    serial = provider.calls * provider.seconds
    assert elapsed < serial / 2, f"concurrent pass took {elapsed:.2f}s against {serial:.2f}s in series"
