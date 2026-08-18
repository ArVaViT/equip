"""Improving the rules has to reach the translations already stored.

A machine row is skipped whenever its source hash still matches: same
source, same translation, nothing to do. That answers "has the author
changed this?" correctly and quietly answers "is this still the best we
know how to make?" wrongly.

Every quality change made — a glossary that settles a term, rules naming
each language's calques, a correcting pass, Scripture that resolves to
canon — improved only what came next. Several thousand stored rows kept
the quality of the day they were made, and the remedy was a person with
a list.

So a row carries the generation of the pipeline that produced it, and a
row from an older generation counts as a gap. The sweep finds it, the
queue takes it, and the catalogue re-translates itself. Raising the
number is the whole of the work.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.content_version import ContentVersion
from app.models.course import Course, CourseStatus
from app.models.user import User
from app.services.content_versions.write import record_human_version, record_mt_version
from app.services.translation.completeness import course_translation_completeness
from app.services.translation.hash import compute_source_hash
from app.services.translation.service import reset_translation_provider_cache
from app.services.translation.version import TRANSLATOR_VERSION

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

TEACHER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a1")


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    # Completeness is a no-op without a provider — nothing would ever be
    # required, and every assertion below would pass vacuously.
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


@pytest.fixture
def course_with_one_translated_title(db: Session) -> Course:
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
    text = "Первое послание к Коринфянам"
    record_human_version(
        db,
        entity_type="course",
        entity_id=str(course.id),
        field="title",
        locale="ru",
        text=text,
    )
    source_hash = compute_source_hash(text, locale="ru")
    for locale in ("en", "de", "uk"):
        record_mt_version(
            db,
            entity_type="course",
            entity_id=str(course.id),
            field="title",
            locale=locale,
            text=f"First Corinthians ({locale})",
            source_locale="ru",
            source_hash=source_hash,
        )
    db.commit()
    return course


def _mt_rows(db: Session, course: Course) -> list[ContentVersion]:
    return (
        db.query(ContentVersion)
        .filter(
            ContentVersion.entity_id == str(course.id),
            ContentVersion.origin == "mt",
            ContentVersion.superseded_by.is_(None),
        )
        .all()
    )


class TestARowRemembersWhoMadeIt:
    def test_a_fresh_translation_carries_the_current_generation(
        self, db: Session, course_with_one_translated_title: Course
    ) -> None:
        rows = _mt_rows(db, course_with_one_translated_title)
        assert rows
        assert all(row.translator_version == TRANSLATOR_VERSION for row in rows)

    def test_a_human_row_is_left_at_zero(self, db: Session, course_with_one_translated_title: Course) -> None:
        # Human translations are never re-translated, so the number has
        # nothing to say about them.
        human = (
            db.query(ContentVersion)
            .filter(
                ContentVersion.entity_id == str(course_with_one_translated_title.id),
                ContentVersion.origin == "human",
                ContentVersion.superseded_by.is_(None),
            )
            .one()
        )
        assert human.translator_version == 0


class TestAnOlderGenerationCountsAsAGap:
    def test_a_complete_course_stops_being_complete(
        self, db: Session, course_with_one_translated_title: Course
    ) -> None:
        before = course_translation_completeness(db, course_with_one_translated_title)
        assert before.is_complete, "the fixture should start whole"

        for row in _mt_rows(db, course_with_one_translated_title):
            row.translator_version = TRANSLATOR_VERSION - 1
        db.commit()

        after = course_translation_completeness(db, course_with_one_translated_title)
        assert not after.is_complete
        assert {gap.reason for gap in after.gaps} == {"stale"}

    def test_the_gap_names_every_language_it_affects(
        self, db: Session, course_with_one_translated_title: Course
    ) -> None:
        for row in _mt_rows(db, course_with_one_translated_title):
            row.translator_version = TRANSLATOR_VERSION - 1
        db.commit()
        gaps = course_translation_completeness(db, course_with_one_translated_title)
        assert {gap.locale for gap in gaps.gaps} == {"en", "de", "uk"}

    def test_re_recording_the_same_words_settles_the_row(
        self, db: Session, course_with_one_translated_title: Course
    ) -> None:
        # A newer pipeline that arrives at the same wording has confirmed
        # it. Leaving the old number would make the sweep pay for the
        # same answer on every cycle, forever.
        rows = _mt_rows(db, course_with_one_translated_title)
        for row in rows:
            row.translator_version = TRANSLATOR_VERSION - 1
        db.commit()
        sample = rows[0]
        record_mt_version(
            db,
            entity_type=sample.entity_type,
            entity_id=sample.entity_id,
            field=sample.field,
            locale=sample.locale,
            text=sample.text,
            source_locale=sample.source_locale or "ru",
            source_hash=sample.source_hash or "",
        )
        db.commit()
        assert course_translation_completeness(db, course_with_one_translated_title).by_locale() != {}
        refreshed = (
            db.query(ContentVersion)
            .filter(
                ContentVersion.entity_id == sample.entity_id,
                ContentVersion.locale == sample.locale,
                ContentVersion.superseded_by.is_(None),
            )
            .one()
        )
        assert refreshed.translator_version == TRANSLATOR_VERSION
