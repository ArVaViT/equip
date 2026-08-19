"""Switching on a fifth language must not need a person with a list.

This is the property the whole reconciler exists for, and it is worth
asserting directly rather than inferring from the parts. Turn a locale
on and every course already published is instantly incomplete in it —
with no save, no hook, and nothing to notice. The old answer, written in
`app/schemas/locale.py`, was "trigger POST /courses/{id}/translate on
every published course, or wait for the next teacher save": fine for
three courses, impossible for a thousand.

So the test adds a locale the way production would, and then checks the
three things that have to follow on their own: the gate starts demanding
it, the sweep queues the course, and a course that already has it is
left alone.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.course import Course, CourseStatus
from app.models.user import User
from app.services.content_versions import record_human_version, record_mt_version
from app.services.translation.hash import compute_source_hash
from app.services.translation.service import reset_translation_provider_cache

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

TEACHER_ID = uuid.UUID("00000000-0000-0000-0000-00000000ac05")
TITLE = "Послание к Римлянам"
LOCALES_TODAY = ("ru", "en", "de", "uk")
WITH_A_FIFTH = (*LOCALES_TODAY, "pl")


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


@pytest.fixture
def a_fully_translated_course(db: Session) -> Course:
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="fifth@example.com", full_name="T", role="teacher"))
        db.commit()
    course = Course(
        id=f"course-{uuid.uuid4().hex[:8]}",
        status=CourseStatus.PUBLISHED,
        source_locale="ru",
        created_by=TEACHER_ID,
    )
    db.add(course)
    db.commit()
    record_human_version(db, entity_type="course", entity_id=str(course.id), field="title", locale="ru", text=TITLE)
    db.commit()
    source_hash = compute_source_hash(TITLE, locale="ru")
    for locale in ("en", "de", "uk"):
        record_mt_version(
            db,
            entity_type="course",
            entity_id=str(course.id),
            field="title",
            locale=locale,
            text=f"{TITLE} [{locale}]",
            source_locale="ru",
            source_hash=source_hash,
        )
    db.commit()
    return course


def _switch_on_a_fifth_language(monkeypatch) -> None:
    """What production does in step 1 of `app/schemas/locale.py`."""
    # Every module that decides "which languages does this need" reads
    # the same tuple. Patching each import site is what production gets
    # for free by editing the tuple itself.
    for module in (
        "app.services.translation.completeness",
        "app.services.translation.orchestrator",
        "app.services.translation.reconciler",
    ):
        monkeypatch.setattr(f"{module}.LOCALE_CODES", WITH_A_FIFTH, raising=False)


class TestTurningOnALanguage:
    def test_the_course_is_whole_before(self, db: Session, a_fully_translated_course: Course) -> None:
        from app.services.translation.completeness import course_translation_completeness

        assert course_translation_completeness(db, a_fully_translated_course).is_complete

    def test_the_gate_starts_demanding_it(self, db: Session, a_fully_translated_course: Course, monkeypatch) -> None:
        from app.services.translation.completeness import course_translation_completeness

        _switch_on_a_fifth_language(monkeypatch)
        completeness = course_translation_completeness(db, a_fully_translated_course)
        assert not completeness.is_complete
        assert {gap.locale for gap in completeness.gaps} == {"pl"}

    def test_the_plan_asks_for_it(self, db: Session, a_fully_translated_course: Course, monkeypatch) -> None:
        from app.services.translation.course_pipeline import plan_course_tasks

        _switch_on_a_fifth_language(monkeypatch)
        assert "pl" in {task.target_locale for task in plan_course_tasks(db, a_fully_translated_course)}

    def test_the_sweep_queues_the_course_with_nobody_asking(
        self, db: Session, a_fully_translated_course: Course, monkeypatch
    ) -> None:
        # No save, no hook, no endpoint call, no list. This is the whole
        # claim: a config change plus a wait.
        from app.services.translation.reconciler import sweep_courses

        _switch_on_a_fifth_language(monkeypatch)
        assert sweep_courses(db, limit=5).queued == 1

    def test_a_course_that_already_has_it_is_left_alone(
        self, db: Session, a_fully_translated_course: Course, monkeypatch
    ) -> None:
        # Otherwise switching a language on would re-translate the whole
        # catalogue rather than the part that is missing.
        from app.services.translation.completeness import course_translation_completeness

        record_mt_version(
            db,
            entity_type="course",
            entity_id=str(a_fully_translated_course.id),
            field="title",
            locale="pl",
            text=f"{TITLE} [pl]",
            source_locale="ru",
            source_hash=compute_source_hash(TITLE, locale="ru"),
        )
        db.commit()

        _switch_on_a_fifth_language(monkeypatch)
        assert course_translation_completeness(db, a_fully_translated_course).is_complete
