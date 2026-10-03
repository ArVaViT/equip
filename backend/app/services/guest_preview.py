"""The first lesson, open to a guest (2026-10-03).

A visitor deciding whether a course is for them could read its
description and its list of lessons, and nothing of the lessons
themselves: every lesson sent them to sign up first. The first one
is now theirs to read — registration is asked for when they want to
keep something (mark it read, answer a test, write a note), not to
look.

Which lesson is first is the order the reader is shown — the course
page and the lesson's "1 of N": modules by their order, each module's
lessons by theirs, then the lessons in no module. (``build_spine``,
which the reports and the PDF use, can slot a loose lesson between two
modules; picking by it named a lesson the reader's screen calls the
last, and showed the visible first one a wall.) The answer is a reading
lesson the course is willing to show anyone — published, public,
released, not locked. Anything else and there is no preview.

"Anyone" includes a signed-in reader who is not enrolled: signing up
must not take away the lesson they were reading a minute ago.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.course import Chapter, Course, CourseStatus, Module
from app.services.staged_edits.visibility import chapter_awaits_first_release

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User


def preview_chapter_id(db: Session, course: Course) -> str | None:
    """The id of the lesson a guest may read, or ``None``."""
    if course.status != CourseStatus.PUBLISHED or course.access_mode != "public" or course.deleted_at is not None:
        return None
    modules = sorted(
        db.query(Module).filter(Module.course_id == course.id, Module.deleted_at.is_(None)).all(),
        key=lambda m: (m.order_index, m.id),
    )
    chapters = (
        db.query(Chapter)
        .filter(Chapter.course_id == course.id, Chapter.deleted_at.is_(None), ~chapter_awaits_first_release())
        .all()
    )
    module_ids = [m.id for m in modules]
    by_module = {
        mid: sorted((c for c in chapters if c.module_id == mid), key=lambda c: (c.order_index, c.id))
        for mid in module_ids
    }
    loose = sorted((c for c in chapters if c.module_id not in by_module), key=lambda c: (c.order_index, c.id))
    ordered = [c for mid in module_ids for c in by_module[mid]] + loose
    if not ordered:
        return None
    first = ordered[0]
    # A test or an assignment is something to hand in; there is nothing a
    # guest can do with one but be told to sign up — so no preview at all.
    if first.chapter_type != "reading" or first.is_locked:
        return None
    return str(first.id)


def reads_course_as_enrolled(db: Session, course: Course, user: User) -> bool:
    """Enrolled, the owner, or platform staff — the readers a preview is not for."""
    from app.models.enrollment import Enrollment
    from app.models.user import UserRole

    if user.role == UserRole.ADMIN.value or str(course.created_by) == str(user.id):
        return True
    return (
        db.query(Enrollment.id).filter(Enrollment.user_id == user.id, Enrollment.course_id == course.id).first()
        is not None
    )


__all__ = ["preview_chapter_id", "reads_course_as_enrolled"]
