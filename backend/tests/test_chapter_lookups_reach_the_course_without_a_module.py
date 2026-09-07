"""The chapter-scoped lookups read ``chapters.course_id``.

``get_chapter`` (the module-scoped chapter routes) and
``course_source_locale_for_chapter`` (the dual-write fallback in the
blocks, assignments and quiz editors) used to reach the course through
``chapters.module_id -> modules.course_id``. They now take the chapter's
own ``course_id``, so a chapter that names no module still finds its
course — while, for every chapter that does name one, the answers are
the ones they were.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.api.v1 import assignments, blocks
from app.api.v1.quizzes import _deps as quiz_deps
from app.models.course import Chapter, CourseStatus, Module
from app.models.user import User, UserRole
from app.services import domain_access
from app.services.course_readiness import _open_chapter_action
from app.services.course_service import get_chapter

from ._cv_helpers import make_course_with_text, make_module_with_text
from .conftest import TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _course(db: Session, course_id: str, *, source_locale: str = "en"):
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="t@e.com", full_name="t@e.com", role=UserRole.TEACHER.value))
        db.commit()
    return make_course_with_text(
        db,
        course_id=course_id,
        title="C",
        status=CourseStatus.PUBLISHED,
        source_locale=source_locale,
        created_by=TEACHER_ID,
    )


def _chapter(db: Session, chapter_id: str, *, course_id: str, module_id: str | None) -> Chapter:
    chapter = Chapter(
        id=chapter_id,
        module_id=module_id,
        course_id=course_id,
        title="Ch",
        order_index=0,
        chapter_type="reading",
    )
    db.add(chapter)
    db.commit()
    return chapter


def _seed_with_module(db: Session, course_id: str) -> tuple[str, str]:
    course = _course(db, course_id)
    module = make_module_with_text(db, module_id=f"{course_id}-mod", course_id=course.id, title="M")
    _chapter(db, f"{course_id}-ch", course_id=course.id, module_id=module.id)
    return module.id, f"{course_id}-ch"


class TestGetChapter:
    def test_found_under_its_module(self, db: Session) -> None:
        module_id, chapter_id = _seed_with_module(db, "gc-1")
        found = get_chapter(db, "gc-1", chapter_id, module_id=module_id)
        assert found is not None and found.id == chapter_id

    def test_another_modules_url_does_not_reach_it(self, db: Session) -> None:
        """The module in the path still narrows the lookup: the route
        guard that a chapter cannot be edited under a foreign module."""
        _module_id, chapter_id = _seed_with_module(db, "gc-2")
        other = make_module_with_text(db, module_id="gc-2-other", course_id="gc-2", title="O")
        assert get_chapter(db, "gc-2", chapter_id, module_id=other.id) is None

    def test_found_by_course_alone(self, db: Session) -> None:
        _module_id, chapter_id = _seed_with_module(db, "gc-3")
        found = get_chapter(db, "gc-3", chapter_id)
        assert found is not None and found.id == chapter_id

    def test_another_course_does_not_reach_it(self, db: Session) -> None:
        _module_id, chapter_id = _seed_with_module(db, "gc-4")
        _course(db, "gc-4-other")
        assert get_chapter(db, "gc-4-other", chapter_id) is None

    def test_chapter_without_module_is_found_by_its_course(self, db: Session) -> None:
        course = _course(db, "gc-5")
        _chapter(db, "gc-5-ch", course_id=course.id, module_id=None)
        found = get_chapter(db, "gc-5", "gc-5-ch")
        assert found is not None and found.module_id is None

    def test_chapter_without_module_is_not_found_under_a_module(self, db: Session) -> None:
        course = _course(db, "gc-6")
        module = make_module_with_text(db, module_id="gc-6-mod", course_id=course.id, title="M")
        _chapter(db, "gc-6-ch", course_id=course.id, module_id=None)
        assert get_chapter(db, "gc-6", "gc-6-ch", module_id=module.id) is None

    def test_soft_deleted_module_hides_chapter(self, db: Session) -> None:
        """Kept from the inner-join days: a binned module takes its
        chapters with it, whether or not the caller names the module."""
        module_id, chapter_id = _seed_with_module(db, "gc-7")
        db.query(Module).filter(Module.id == module_id).update({"deleted_at": datetime.now(UTC)})
        db.commit()
        assert get_chapter(db, "gc-7", chapter_id, module_id=module_id) is None
        assert get_chapter(db, "gc-7", chapter_id) is None

    def test_soft_deleted_chapter_is_hidden(self, db: Session) -> None:
        module_id, chapter_id = _seed_with_module(db, "gc-8")
        db.query(Chapter).filter(Chapter.id == chapter_id).update({"deleted_at": datetime.now(UTC)})
        db.commit()
        assert get_chapter(db, "gc-8", chapter_id, module_id=module_id) is None


class TestCourseSourceLocaleForChapter:
    def test_chapter_with_module_answers_its_course_locale(self, db: Session) -> None:
        course = _course(db, "loc-1", source_locale="ru")
        module = make_module_with_text(db, module_id="loc-1-mod", course_id=course.id, title="M")
        _chapter(db, "loc-1-ch", course_id=course.id, module_id=module.id)
        assert domain_access.course_source_locale_for_chapter(db, "loc-1-ch") == "ru"

    def test_chapter_without_module_answers_its_course_locale(self, db: Session) -> None:
        course = _course(db, "loc-2", source_locale="de")
        _chapter(db, "loc-2-ch", course_id=course.id, module_id=None)
        assert domain_access.course_source_locale_for_chapter(db, "loc-2-ch") == "de"

    def test_unknown_chapter_answers_none(self, db: Session) -> None:
        assert domain_access.course_source_locale_for_chapter(db, "nope") is None

    def test_the_three_editors_share_the_one_lookup(self) -> None:
        """Blocks, assignments and quizzes each carried a copy of the walk;
        the copies are gone and the names they exported point at the one
        function, so ``rubrics`` and the quiz routes import as before."""
        assert blocks._course_source_locale_for_chapter is domain_access.course_source_locale_for_chapter
        assert assignments._course_source_locale_for_chapter is domain_access.course_source_locale_for_chapter
        assert quiz_deps.course_source_locale_for_chapter is domain_access.course_source_locale_for_chapter


class TestReadinessDeepLink:
    def test_chapter_with_module_links_through_it(self, db: Session) -> None:
        module_id, chapter_id = _seed_with_module(db, "rd-1")
        chapter = db.get(Chapter, chapter_id)
        assert chapter is not None
        assert _open_chapter_action(chapter).params == {"module_id": module_id, "chapter_id": chapter_id}

    def test_chapter_without_module_links_by_chapter_alone(self, db: Session) -> None:
        course = _course(db, "rd-2")
        chapter = _chapter(db, "rd-2-ch", course_id=course.id, module_id=None)
        assert _open_chapter_action(chapter).params == {"chapter_id": "rd-2-ch"}
