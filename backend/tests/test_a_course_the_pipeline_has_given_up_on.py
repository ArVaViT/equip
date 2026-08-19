"""A row that has run out of retries must stop asking for them.

``failed`` and ``failed_permanent`` are different states. The executor
retries the first and refuses the second — five attempts is where it
stops. The completeness check reported both as the reason ``"failed"``,
and the sweep queued anything that was not ``needs_review``. So a single
terminal row kept its course in the queue forever: the sweep queued it,
the worker claimed it, planned every field, skipped every one, and
reported done. Every minute, indefinitely.

The part that makes it worse than a wasted tick is what else it stops.
``sweep_courses`` and the idle Daily Challenge pool sweep both run only
when ``claim_next_job`` returns None. A course that re-queues itself
every cycle keeps the queue non-empty, so the idle branch is never
reached — one permanently-broken course switches the self-healing layer
off for the whole platform.

The sharp assertion here is the loop: sweep twice, and the second sweep
must not queue.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from pydantic import SecretStr

from app.models.content_version import ContentVersion, ContentVersionStatus
from app.models.course import Course, CourseStatus, Module
from app.models.user import User
from app.services.content_versions.write import record_human_version, record_mt_version
from app.services.translation.completeness import course_translation_completeness
from app.services.translation.hash import compute_source_hash
from app.services.translation.reconciler import sweep_courses
from app.services.translation.service import reset_translation_provider_cache

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

TEACHER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000d4")


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


def _fully_translated_course(db: Session) -> Course:
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="terminal@example.com", full_name="T", role="teacher"))
        db.commit()
    course = Course(
        id=f"course-{uuid.uuid4().hex[:8]}",
        status=CourseStatus.PUBLISHED,
        source_locale="ru",
        created_by=TEACHER_ID,
    )
    db.add(course)
    db.flush()
    module = Module(
        id=f"mod-{uuid.uuid4().hex[:8]}",
        course_id=course.id,
        title="Первый модуль",
        order_index=0,
    )
    db.add(module)
    db.commit()

    for entity_type, entity_id, field, text in (
        ("course", str(course.id), "title", "Послание к Римлянам"),
        ("course", str(course.id), "description", "Письмо апостола Павла: разбор по главам"),
        ("module", str(module.id), "title", "Первый модуль"),
        ("module", str(module.id), "description", "Здесь начинается первая часть"),
    ):
        record_human_version(db, entity_type=entity_type, entity_id=entity_id, field=field, locale="ru", text=text)
        source_hash = compute_source_hash(text, locale="ru")
        for locale in ("en", "de", "uk"):
            record_mt_version(
                db,
                entity_type=entity_type,
                entity_id=entity_id,
                field=field,
                locale=locale,
                text=f"{text} [{locale}]",
                source_locale="ru",
                source_hash=source_hash,
            )
    db.commit()
    return course


def _park_one_row(db: Session, course: Course, status: str) -> ContentVersion:
    row = (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_id == str(course.id),
            ContentVersion.origin == "mt",
            ContentVersion.superseded_by.is_(None),
        )
        .first()
    )
    assert row is not None
    row.status = status
    row.attempts = 5
    db.commit()
    return row


class TestACourseWithATerminalRow:
    def test_the_second_sweep_does_not_queue_it_again(self, db: Session) -> None:
        course = _fully_translated_course(db)
        assert sweep_courses(db, limit=5).queued == 0, "the fixture should start settled"
        _park_one_row(db, course, ContentVersionStatus.FAILED_PERMANENT)

        first = sweep_courses(db, limit=5)
        second = sweep_courses(db, limit=5)

        assert first.queued == 0
        assert second.queued == 0
        assert second.examined >= 1, "the course must still be examined, just not queued"

    def test_nothing_reaches_the_queue_behind_the_scenes(self, db: Session) -> None:
        course = _fully_translated_course(db)
        _park_one_row(db, course, ContentVersionStatus.FAILED_PERMANENT)

        with patch("app.services.translation.reconciler.enqueue_course_translation") as enqueue:
            sweep_courses(db, limit=5)
            sweep_courses(db, limit=5)

        enqueue.assert_not_called()

    def test_a_retryable_failure_is_still_queued(self, db: Session) -> None:
        # The distinction is the whole fix. ``failed`` IS retried by the
        # executor, and resetting ``attempts`` from the admin surface is
        # how an operator asks for another go — if the sweep stopped
        # queueing those too, the retry button would do nothing.
        course = _fully_translated_course(db)
        row = _park_one_row(db, course, ContentVersionStatus.FAILED)
        row.attempts = 0
        db.commit()

        assert sweep_courses(db, limit=5).queued == 1

    def test_the_course_is_still_reported_incomplete(self, db: Session) -> None:
        # Not queueing it is not the same as calling it fine. The gap is
        # real, the reader has nothing servable, and this is what keeps
        # the course out of the catalogue.
        course = _fully_translated_course(db)
        _park_one_row(db, course, ContentVersionStatus.FAILED_PERMANENT)

        completeness = course_translation_completeness(db, course)

        assert not completeness.is_complete
        assert len(completeness.by_reason("failed_permanent")) == 1
        assert completeness.by_reason("failed") == ()

    def test_it_stops_starving_the_rest_of_the_self_healing_layer(self, db: Session) -> None:
        # The reason this mattered beyond one course: the idle Daily
        # Challenge pool sweep runs only on a tick where the queue is
        # empty. A course that re-queues every cycle never lets that
        # happen.
        from app.api.v1.internal_translation_worker import _run_one_tick
        from app.services.daily_challenge.translate import SweepReport as PoolSweepReport
        from app.services.translation.orchestrator import OrchestratorReport

        course = _fully_translated_course(db)
        _park_one_row(db, course, ContentVersionStatus.FAILED_PERMANENT)

        with patch(
            "app.api.v1.internal_translation_worker.translate_pending_questions",
            return_value=PoolSweepReport(questions=0, rows=OrchestratorReport()),
        ) as pool:
            assert _run_one_tick(db).status == "idle"

        pool.assert_called_once()
