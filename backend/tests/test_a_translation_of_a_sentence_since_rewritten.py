"""Servable is not the same as current.

The executor has always compared source hashes before deciding whether
to re-ask: a translation whose source has changed is work to do. The
completeness check did not. It asked "does a servable row exist", which
is a different question, and the two disagreed in one direction only —
the gate said complete, the plan said there was work, and
``promote_if_complete`` published a course whose other three languages
carried the previous wording.

The reconciler is driven by completeness, so this was also invisible to
the sweep: the safety net written to catch exactly this kind of drift
could not see it. It self-healed only when somebody edited the course
again, or when TRANSLATOR_VERSION rose.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.course import Course, CourseStatus
from app.models.user import User
from app.services.content_versions import record_human_version, record_mt_version
from app.services.translation.completeness import course_translation_completeness
from app.services.translation.hash import compute_source_hash
from app.services.translation.reconciler import sweep_courses
from app.services.translation.service import reset_translation_provider_cache

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

TEACHER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000f2")

FIRST = "Путешествия апостола Павла"
REWRITTEN = "Миссионерские путешествия апостола Павла"
DESCRIPTION = "Введение в книгу Деяний"


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


@pytest.fixture
def translated_course(db: Session) -> Course:
    """A course translated into every language, and complete."""
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="drift@example.com", full_name="T", role="teacher"))
        db.commit()
    course = Course(
        id=f"course-{uuid.uuid4().hex[:8]}",
        status=CourseStatus.PUBLISHED,
        source_locale="ru",
        created_by=TEACHER_ID,
    )
    db.add(course)
    db.commit()

    record_human_version(db, entity_type="course", entity_id=str(course.id), field="title", locale="ru", text=FIRST)
    record_human_version(
        db,
        entity_type="course",
        entity_id=str(course.id),
        field="description",
        locale="ru",
        text=DESCRIPTION,
    )
    db.commit()

    for field, text in (("title", FIRST), ("description", DESCRIPTION)):
        source_hash = compute_source_hash(text, locale="ru")
        for locale in ("en", "de", "uk"):
            record_mt_version(
                db,
                entity_type="course",
                entity_id=str(course.id),
                field=field,
                locale=locale,
                text=f"{text} [{locale}]",
                source_locale="ru",
                source_hash=source_hash,
            )
    db.commit()
    return course


class TestAnEditTheTranslationsHaveNotCaughtUpWith:
    def test_the_course_starts_complete(self, db: Session, translated_course: Course) -> None:
        assert course_translation_completeness(db, translated_course).is_complete

    def test_rewriting_the_source_reopens_it(self, db: Session, translated_course: Course) -> None:
        record_human_version(
            db,
            entity_type="course",
            entity_id=str(translated_course.id),
            field="title",
            locale="ru",
            text=REWRITTEN,
        )
        db.commit()

        completeness = course_translation_completeness(db, translated_course)
        assert not completeness.is_complete
        assert {gap.locale for gap in completeness.gaps} == {"en", "de", "uk"}
        assert {gap.field for gap in completeness.gaps} == {"title"}, "only the field that changed"

    def test_the_sweep_can_now_see_it(self, db: Session, translated_course: Course) -> None:
        # The point of the fix: the reconciler is driven by completeness,
        # so a gap it cannot see is a gap nothing schedules.
        record_human_version(
            db,
            entity_type="course",
            entity_id=str(translated_course.id),
            field="title",
            locale="ru",
            text=REWRITTEN,
        )
        db.commit()

        assert sweep_courses(db, limit=5).queued == 1

    def test_a_human_translation_is_not_called_stale(self, db: Session, translated_course: Course) -> None:
        # A person who translated the title by hand did not do it "from"
        # a hash, and their work must not be thrown away because the
        # source moved. Only machine rows carry that promise.
        db.query(type(translated_course)).count()
        record_human_version(
            db,
            entity_type="course",
            entity_id=str(translated_course.id),
            field="title",
            locale="de",
            text="Die Reisen des Apostels Paulus",
        )
        record_human_version(
            db,
            entity_type="course",
            entity_id=str(translated_course.id),
            field="title",
            locale="ru",
            text=REWRITTEN,
        )
        db.commit()

        stale_locales = {gap.locale for gap in course_translation_completeness(db, translated_course).gaps}
        assert "de" not in stale_locales
        assert stale_locales == {"en", "uk"}
