"""The first lesson, open to a guest (2026-10-03).

A visitor deciding whether a course is for them could read its
description and its list of lessons, and nothing of the lessons
themselves: every lesson sent them to sign up first. The first one
is now theirs to read — registration is asked for when they want to
keep something (mark it read, answer a test, write a note), not to
look.

Which lesson is first is the server's question, not the browser's:
``build_spine`` is the one reading order the reports and the PDF
already use, and a loose lesson can sit between two modules there. The
answer is a reading lesson the course is willing to show anyone —
published, public, released, not locked. Anything else and there is no
preview: a guest is sent to sign up, as before.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.course import Chapter, Course, CourseStatus, Module
from app.services.course_structure import build_spine
from app.services.staged_edits.visibility import chapter_awaits_first_release

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def preview_chapter_id(db: Session, course: Course) -> str | None:
    """The id of the lesson a guest may read, or ``None``."""
    if course.status != CourseStatus.PUBLISHED or course.access_mode != "public" or course.deleted_at is not None:
        return None
    modules = db.query(Module).filter(Module.course_id == course.id, Module.deleted_at.is_(None)).all()
    chapters = (
        db.query(Chapter)
        .filter(Chapter.course_id == course.id, Chapter.deleted_at.is_(None), ~chapter_awaits_first_release())
        .all()
    )
    spine = build_spine(modules, chapters)
    if not spine.chapters:
        return None
    first = spine.chapters[0]
    # A test or an assignment is something to hand in; there is nothing a
    # guest can do with one but be told to sign up — so no preview at all.
    if first.chapter_type != "reading" or first.is_locked:
        return None
    return str(first.id)


__all__ = ["preview_chapter_id"]
