# ruff: noqa: RUF001
"""A held edit whose translation failed for a moment is picked up again.

On 2026-10-24 an edit to three lessons of a live Russian course was held
for its translations. The Bible service did not answer for one verse in
Ukrainian and German for a minute, so those two rows were left
``failed`` "for the next tick" — and the job closed ``done``. The next
tick only ever comes from a queued job, and the sweep, which exists to
queue what events miss, judges a course by its live text: whole. The
edit stayed out of sight of seventeen students for more than a day.

The sweep now asks the staging table too. What a person has to move
(``needs_review``, ``failed_permanent``) it still leaves alone.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.content_version import ContentVersionStatus
from app.models.course import Course, CourseStatus
from app.models.staged_content_version import StagedContentVersion
from app.models.translation_job import TranslationJob
from app.models.user import User
from app.services.content_versions.write import record_human_version, record_mt_version
from app.services.staged_edits import stage_human_edit
from app.services.translation.hash import compute_source_hash
from app.services.translation.reconciler import sweep_courses
from app.services.translation.service import reset_translation_provider_cache
from tests.conftest import TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

EDIT = "Решение Иерусалимского собора (Деян. 15:28)"


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


def _course_with_a_held_edit(db: Session) -> Course:
    """A live Russian course, whole in every language, with one edit held."""
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
    live = "Деяния апостолов"
    record_human_version(db, entity_type="course", entity_id=str(course.id), field="title", locale="ru", text=live)
    for locale in ("en", "de", "uk"):
        record_mt_version(
            db,
            entity_type="course",
            entity_id=str(course.id),
            field="title",
            locale=locale,
            text=f"[{locale}] Acts",
            source_locale="ru",
            source_hash=compute_source_hash(live, locale="ru"),
        )
    db.commit()
    stage_human_edit(
        db,
        entity_type="course",
        entity_id=str(course.id),
        course_id=str(course.id),
        field="title",
        locale="ru",
        text=EDIT,
    )
    db.commit()
    return course


def _translation(db: Session, course: Course, locale: str, status: str) -> None:
    db.add(
        StagedContentVersion(
            entity_type="course",
            entity_id=str(course.id),
            course_id=str(course.id),
            field="title",
            locale=locale,
            text="" if status != ContentVersionStatus.OK else f"[{locale}] {EDIT}",
            origin="mt",
            status=status,
            source_locale="ru",
            source_hash=compute_source_hash(EDIT, locale="ru"),
        )
    )
    db.commit()


def _settled(db: Session, course: Course) -> None:
    """The job that translated it has run and closed; the course was last
    looked at an hour ago."""
    db.query(TranslationJob).delete()
    course.translations_checked_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()


def _queued(db: Session, course: Course) -> int:
    return db.query(TranslationJob).filter(TranslationJob.course_id == str(course.id)).count()


def test_a_translation_that_failed_for_a_moment_is_queued_again(db: Session) -> None:
    course = _course_with_a_held_edit(db)
    _translation(db, course, "en", ContentVersionStatus.OK)
    _translation(db, course, "de", ContentVersionStatus.FAILED)
    _translation(db, course, "uk", ContentVersionStatus.FAILED)
    _settled(db, course)

    report = sweep_courses(db, limit=5)

    assert report.queued == 1
    assert _queued(db, course) == 1


def test_an_edit_waiting_on_a_person_is_not_queued(db: Session) -> None:
    course = _course_with_a_held_edit(db)
    _translation(db, course, "en", ContentVersionStatus.OK)
    _translation(db, course, "de", ContentVersionStatus.NEEDS_REVIEW)
    _translation(db, course, "uk", ContentVersionStatus.FAILED_PERMANENT)
    _settled(db, course)

    report = sweep_courses(db, limit=5)

    assert report.queued == 0
    assert _queued(db, course) == 0


def test_an_edit_with_every_language_in_is_not_queued(db: Session) -> None:
    course = _course_with_a_held_edit(db)
    for locale in ("en", "de", "uk"):
        _translation(db, course, locale, ContentVersionStatus.OK)
    _settled(db, course)

    assert sweep_courses(db, limit=5).queued == 0
