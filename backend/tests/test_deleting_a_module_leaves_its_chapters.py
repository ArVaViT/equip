"""Deleting a module deletes the grouping; the lessons stay on the course.

The first teacher to build a course here had four lessons and no use for
modules. The model made them mandatory, so they invented some, recut the
tree twice, and then deleted a module — which took the lessons inside it.
They stopped.

The module is optional from this step on: a chapter belongs to its
course and only *names* a module. So binning a module detaches its live
chapters (``module_id = NULL``) and leaves them where they live, and the
database says the same thing through ``ON DELETE SET NULL`` on
``chapters.module_id`` — the physical delete no longer takes the chapter
either.

What still cascades is the course. A course is the thing a chapter
belongs to, so binning one bins its chapters, ungrouped ones included,
and restoring it brings them back.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.course import Chapter, CourseStatus, Module
from app.models.user import User, UserRole
from app.services.course_service import delete_course, delete_module, restore_course

from ._cv_helpers import make_course_with_text, make_module_with_text
from .conftest import TEACHER_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _course(db: Session, course_id: str):
    if db.get(User, TEACHER_ID) is None:
        db.add(User(id=TEACHER_ID, email="t@e.com", full_name="t@e.com", role=UserRole.TEACHER.value))
        db.commit()
    return make_course_with_text(
        db,
        course_id=course_id,
        title="C",
        status=CourseStatus.PUBLISHED,
        source_locale="ru",
        created_by=TEACHER_ID,
    )


def _chapter(db: Session, chapter_id: str, *, course_id: str, module_id: str | None, order_index: int = 0) -> Chapter:
    chapter = Chapter(
        id=chapter_id,
        module_id=module_id,
        course_id=course_id,
        title=chapter_id,
        order_index=order_index,
        chapter_type="reading",
    )
    db.add(chapter)
    db.commit()
    return chapter


# ---------------------------------------------------------------------------
# The soft delete: the route a teacher actually presses
# ---------------------------------------------------------------------------


class TestDeleteModuleKeepsTheChapters:
    def test_the_chapters_stay_live_and_keep_their_course(self, db: Session) -> None:
        course = _course(db, "dm-1")
        module = make_module_with_text(db, module_id="dm-1-mod", course_id=course.id, title="M")
        _chapter(db, "dm-1-a", course_id=course.id, module_id=module.id, order_index=0)
        _chapter(db, "dm-1-b", course_id=course.id, module_id=module.id, order_index=1)

        delete_module(db, module)

        chapters = db.query(Chapter).filter(Chapter.course_id == course.id).order_by(Chapter.order_index).all()
        assert [c.id for c in chapters] == ["dm-1-a", "dm-1-b"]
        # Live: the point of the change. Not binned, not orphaned.
        assert all(c.deleted_at is None for c in chapters)
        # Ungrouped: the heading is what went away.
        assert all(c.module_id is None for c in chapters)
        assert all(c.course_id == course.id for c in chapters)

    def test_the_module_itself_is_binned(self, db: Session) -> None:
        """The grouping does go — this is a delete, not a no-op."""
        course = _course(db, "dm-2")
        module = make_module_with_text(db, module_id="dm-2-mod", course_id=course.id, title="M")
        _chapter(db, "dm-2-a", course_id=course.id, module_id=module.id)

        delete_module(db, module)

        binned = db.query(Module).filter(Module.id == "dm-2-mod").one()
        assert binned.deleted_at is not None

    def test_another_modules_chapters_are_untouched(self, db: Session) -> None:
        course = _course(db, "dm-3")
        doomed = make_module_with_text(db, module_id="dm-3-doomed", course_id=course.id, title="D")
        kept = make_module_with_text(db, module_id="dm-3-kept", course_id=course.id, title="K")
        _chapter(db, "dm-3-a", course_id=course.id, module_id=doomed.id)
        _chapter(db, "dm-3-b", course_id=course.id, module_id=kept.id)

        delete_module(db, doomed)

        assert db.query(Chapter).filter(Chapter.id == "dm-3-a").one().module_id is None
        assert db.query(Chapter).filter(Chapter.id == "dm-3-b").one().module_id == kept.id

    def test_a_chapter_already_in_the_bin_keeps_its_module(self, db: Session) -> None:
        """Only live chapters are detached.

        A chapter the teacher binned on its own is history; the module it
        was binned under is part of that history, and nothing reads a
        binned chapter's module. Detaching it would rewrite the record
        for no reader's benefit.
        """
        course = _course(db, "dm-4")
        module = make_module_with_text(db, module_id="dm-4-mod", course_id=course.id, title="M")
        _chapter(db, "dm-4-a", course_id=course.id, module_id=module.id)
        db.query(Chapter).filter(Chapter.id == "dm-4-a").update({"deleted_at": datetime.now(UTC)})
        db.commit()

        delete_module(db, module)

        binned_chapter = db.query(Chapter).filter(Chapter.id == "dm-4-a").one()
        assert binned_chapter.module_id == "dm-4-mod"
        assert binned_chapter.deleted_at is not None


# ---------------------------------------------------------------------------
# The course cascade still owns the chapter, module or no module
# ---------------------------------------------------------------------------


class TestAChapterWithNoModuleFollowsItsCourse:
    def test_it_is_binned_with_the_course_and_comes_back_with_it(self, db: Session) -> None:
        course = _course(db, "dm-5")
        _chapter(db, "dm-5-loose", course_id=course.id, module_id=None)

        delete_course(db, course)
        assert db.query(Chapter).filter(Chapter.id == "dm-5-loose").one().deleted_at is not None

        restore_course(db, course)
        restored = db.query(Chapter).filter(Chapter.id == "dm-5-loose").one()
        assert restored.deleted_at is None
        assert restored.module_id is None
        assert restored.course_id == course.id

    def test_a_chapter_detached_by_a_module_delete_survives_the_round_trip(self, db: Session) -> None:
        """The two rules composed: delete the module, then bin and restore
        the whole course. The lesson comes back, still ungrouped.

        Under the old cascade this chapter would already have been binned
        by ``delete_module``, so the course restore — which only revives
        rows carrying the course's own tombstone — would have left it in
        the bin for good.
        """
        course = _course(db, "dm-6")
        module = make_module_with_text(db, module_id="dm-6-mod", course_id=course.id, title="M")
        _chapter(db, "dm-6-a", course_id=course.id, module_id=module.id)

        delete_module(db, module)
        delete_course(db, course)
        restore_course(db, course)

        chapter = db.query(Chapter).filter(Chapter.id == "dm-6-a").one()
        assert chapter.deleted_at is None
        assert chapter.module_id is None


# ---------------------------------------------------------------------------
# The database says it too
# ---------------------------------------------------------------------------


def test_physically_deleting_a_module_does_not_take_the_chapter(db: Session) -> None:
    """``chapters_module_id_fkey`` is ``ON DELETE SET NULL``.

    It was ``ON DELETE CASCADE``, which was coherent only while a chapter
    could not exist without a module. A hard delete of the row now
    detaches the chapter exactly as ``delete_module`` does, so the two
    paths cannot disagree.
    """
    course = _course(db, "dm-7")
    module = make_module_with_text(db, module_id="dm-7-mod", course_id=course.id, title="M")
    _chapter(db, "dm-7-a", course_id=course.id, module_id=module.id)

    db.query(Module).filter(Module.id == "dm-7-mod").delete()
    db.commit()
    db.expire_all()

    chapter = db.query(Chapter).filter(Chapter.id == "dm-7-a").one()
    assert chapter.module_id is None
    assert chapter.course_id == course.id
    assert chapter.deleted_at is None


def test_physically_deleting_the_course_still_takes_the_chapter(db: Session) -> None:
    """The other FK is unchanged and must stay that way: the course is what
    a chapter belongs to, so purging one purges its chapters."""
    course = _course(db, "dm-8")
    _chapter(db, "dm-8-a", course_id=course.id, module_id=None)

    db.query(type(course)).filter_by(id=course.id).delete()
    db.commit()
    db.expire_all()

    assert db.query(Chapter).filter(Chapter.id == "dm-8-a").first() is None


def test_a_chapter_with_no_module_can_be_stored(db: Session) -> None:
    """``chapters.module_id`` is nullable from this step on — the thing the
    migration makes legal, asserted against the schema the tests build."""
    course = _course(db, "dm-9")
    _chapter(db, "dm-9-a", course_id=course.id, module_id=None)
    assert db.query(Chapter).filter(Chapter.id == "dm-9-a").one().module_id is None
