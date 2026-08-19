"""A chapter in the bin has no readers, so it needs no translations.

Two callers walk a course tree, and they used to disagree about how big
the tree was. The worker plans through ``get_course``, whose loader
filters binned modules and chapters out. The completeness check walked a
course the sweep had fetched with a plain query, which does not.

That disagreement produced a gap nothing could close: the check demanded
translations for chapters nobody can read, the plan never produced them,
so the sweep re-queued the course on every tick for a job with nothing
to do. It cost nothing while every course was complete — and the moment
pipeline versioning made thousands of rows count as missing, it became a
permanent spin. In production, 1,794 of one course's 2,634 "gaps" were
binned chapters.

The walk now filters, so both callers get the same answer whichever way
the course arrived.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from pydantic import SecretStr

from app.models.course import Chapter, Course, CourseStatus, Module
from app.models.user import User
from app.services.course_service import get_course
from app.services.translation.completeness import course_translation_completeness
from app.services.translation.course_pipeline import plan_course_tasks
from app.services.translation.course_tree import iter_course_entities
from app.services.translation.service import reset_translation_provider_cache

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

TEACHER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000b7")


@pytest.fixture(autouse=True)
def _enable_translation(monkeypatch):
    monkeypatch.setattr(
        "app.services.translation.service.settings.GEMINI_API_KEY",
        SecretStr("fake-test-key"),
        raising=False,
    )
    reset_translation_provider_cache()


@pytest.fixture
def course_with_a_binned_chapter(db: Session) -> Course:
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="binned@example.com", full_name="T", role="teacher"))
        db.commit()
    course = Course(
        id=f"course-{uuid.uuid4().hex[:8]}",
        status=CourseStatus.PUBLISHED,
        source_locale="ru",
        created_by=TEACHER_ID,
    )
    db.add(course)
    db.flush()

    live_module = Module(id=f"mod-{uuid.uuid4().hex[:8]}", course_id=course.id, title="Живой модуль", order_index=0)
    binned_module = Module(
        id=f"mod-{uuid.uuid4().hex[:8]}",
        course_id=course.id,
        title="Модуль в корзине",
        order_index=1,
        deleted_at=datetime.now(UTC),
    )
    db.add_all([live_module, binned_module])
    db.flush()

    db.add_all(
        [
            Chapter(id=f"ch-{uuid.uuid4().hex[:8]}", module_id=live_module.id, title="Живая глава", order_index=0),
            Chapter(
                id=f"ch-{uuid.uuid4().hex[:8]}",
                module_id=live_module.id,
                title="Глава в корзине",
                order_index=1,
                deleted_at=datetime.now(UTC),
            ),
            Chapter(id=f"ch-{uuid.uuid4().hex[:8]}", module_id=binned_module.id, title="Глава удалённого модуля", order_index=0),
        ]
    )
    db.commit()
    return course


class TestTheWalkSkipsWhatNobodyCanRead:
    def test_a_binned_chapter_is_not_walked(self, db: Session, course_with_a_binned_chapter: Course) -> None:
        walked = list(iter_course_entities(db, course_with_a_binned_chapter))
        chapters = [entity for kind, entity in walked if kind == "chapter"]
        assert len(chapters) == 1
        assert all(chapter.deleted_at is None for chapter in chapters)

    def test_a_binned_module_is_not_walked(self, db: Session, course_with_a_binned_chapter: Course) -> None:
        modules = [
            entity for kind, entity in iter_course_entities(db, course_with_a_binned_chapter) if kind == "module"
        ]
        assert len(modules) == 1
        assert modules[0].deleted_at is None


class TestBothCallersAgree:
    def test_the_plan_is_the_same_however_the_course_was_loaded(
        self, db: Session, course_with_a_binned_chapter: Course
    ) -> None:
        # ``get_course`` filters binned children in its loader; a plain
        # fetch does not. The walk must not care.
        by_fetch = plan_course_tasks(db, course_with_a_binned_chapter)
        db.expire_all()
        loaded = get_course(db, str(course_with_a_binned_chapter.id))
        assert loaded is not None
        by_service = plan_course_tasks(db, loaded)
        assert {(t.entity_type, t.entity_id, t.field, t.target_locale) for t in by_fetch} == {
            (t.entity_type, t.entity_id, t.field, t.target_locale) for t in by_service
        }

    def test_completeness_never_demands_more_than_the_plan_can_make(
        self, db: Session, course_with_a_binned_chapter: Course
    ) -> None:
        # The failure this guards: a gap the plan cannot close, which the
        # sweep re-queues forever.
        planned = {
            (t.entity_type, t.entity_id, t.field, t.target_locale)
            for t in plan_course_tasks(db, course_with_a_binned_chapter)
        }
        gaps = {
            (g.entity_type, g.entity_id, g.field, g.locale)
            for g in course_translation_completeness(db, course_with_a_binned_chapter).gaps
        }
        assert gaps <= planned
