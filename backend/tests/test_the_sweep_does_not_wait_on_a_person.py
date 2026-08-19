"""The sweep queues work the pipeline can do, and nothing else.

A translation parked at ``needs_review`` is a gap — the reader has
nothing servable in that language — and it is not a gap the pipeline can
close. Sampling runs at temperature 0, so asking again returns the same
text and the same verdict. Those rows move when a person accepts or
retries them.

Queueing them anyway is how production spent an hour running the worker
once a minute, planning a thousand fields, skipping every one and
reporting success. Two rows out of 1,011 kept an entire course in the
queue forever.

The course stays incomplete, which is true and is what keeps it out of
the catalogue. It just stops being re-queued for a job with nothing
to do.
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
from app.services.translation.hash import compute_source_hash
from app.services.translation.reconciler import sweep_courses
from app.services.translation.service import reset_translation_provider_cache

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

TEACHER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000c3")


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


def _course_with_one_translated_module(db: Session) -> Course:
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="sweep@example.com", full_name="T", role="teacher"))
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


class TestASweepThatFindsOnlyReviewWork:
    def test_a_whole_course_is_not_queued(self, db: Session) -> None:
        course = _course_with_one_translated_module(db)
        assert sweep_courses(db, limit=5).queued == 0, "the fixture should start settled"

        # One row of the thousand goes to a person.
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
        row.status = ContentVersionStatus.NEEDS_REVIEW
        row.review_reason = "[markup_mismatch] tags changed"
        db.commit()

        report = sweep_courses(db, limit=5)
        assert report.queued == 0
        assert report.examined >= 1

    def test_but_a_missing_language_still_is(self, db: Session) -> None:
        course = _course_with_one_translated_module(db)
        db.query(ContentVersion).filter(
            ContentVersion.entity_id == str(course.id),
            ContentVersion.locale == "de",
            ContentVersion.origin == "mt",
        ).delete()
        db.commit()

        assert sweep_courses(db, limit=5).queued == 1

    def test_a_course_waiting_on_a_person_is_still_timestamped(self, db: Session) -> None:
        # Otherwise it sorts first forever and starves the others.
        course = _course_with_one_translated_module(db)
        row = (
            db.query(ContentVersion)
            .filter(
                ContentVersion.entity_id == str(course.id),
                ContentVersion.origin == "mt",
                ContentVersion.superseded_by.is_(None),
            )
            .first()
        )
        row.status = ContentVersionStatus.NEEDS_REVIEW
        db.commit()

        sweep_courses(db, limit=5)
        db.refresh(course)
        assert course.translations_checked_at is not None

    def test_nothing_is_enqueued_behind_the_scenes(self, db: Session) -> None:
        course = _course_with_one_translated_module(db)
        row = (
            db.query(ContentVersion)
            .filter(
                ContentVersion.entity_id == str(course.id),
                ContentVersion.origin == "mt",
                ContentVersion.superseded_by.is_(None),
            )
            .first()
        )
        row.status = ContentVersionStatus.NEEDS_REVIEW
        db.commit()

        with patch("app.services.translation.reconciler.enqueue_course_translation") as enqueue:
            sweep_courses(db, limit=5)
        enqueue.assert_not_called()
