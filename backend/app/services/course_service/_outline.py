"""The course's outline as one sequence: read it, and write it in one go.

``course_structure`` says how a course reads; this is the database half —
the live rows of one course, the next free place at its tail, and the
write a teacher's reorder turns into. See ``course_structure`` for the
rule itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func

from app.models.course import Chapter, Module
from app.services.course_structure import CourseSpine, build_spine, number_outline

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session


class OutlineMismatchError(ValueError):
    """The outline sent does not name exactly the course's live modules
    and lessons — a stale screen, or ids from another course."""


def next_outline_order(db: Session, course_id: str) -> int:
    """The number of the place after everything the course holds.

    Modules and loose lessons share one sequence, so the tail is past the
    highest number either table holds. Used for a new module, a new
    lesson (at the course's tail, or at its module's tail — inside a
    module the number only has to be the largest there, and this is),
    and a lesson re-filed with no place given.
    """
    chapter_max = (
        db.query(func.max(Chapter.order_index))
        .filter(Chapter.course_id == course_id, Chapter.deleted_at.is_(None))
        .scalar()
    )
    module_max = (
        db.query(func.max(Module.order_index))
        .filter(Module.course_id == course_id, Module.deleted_at.is_(None))
        .scalar()
    )
    highest = max((n for n in (chapter_max, module_max) if n is not None), default=None)
    return 0 if highest is None else highest + 1


def live_spine(db: Session, course_id: str) -> CourseSpine:
    """The course as it reads now, from its live rows."""
    modules = db.query(Module).filter(Module.course_id == course_id, Module.deleted_at.is_(None)).all()
    chapters = db.query(Chapter).filter(Chapter.course_id == course_id, Chapter.deleted_at.is_(None)).all()
    return build_spine(modules, chapters)


def write_outline(db: Session, course_id: str, places: Sequence[tuple[str | None, Sequence[str]]]) -> None:
    """Renumber the course to read as ``places``. Flushes, does not commit.

    Every live module of the course must appear exactly once, and every
    live lesson exactly once — a partial outline would leave the rows it
    does not name holding numbers from the old sequence, which is how a
    lesson ends up somewhere nobody put it. Anything else raises
    :class:`OutlineMismatchError` and writes nothing.

    Only rows whose number or module actually changes are touched.
    """
    modules = {
        m.id: m for m in db.query(Module).filter(Module.course_id == course_id, Module.deleted_at.is_(None)).all()
    }
    chapters = {
        c.id: c for c in db.query(Chapter).filter(Chapter.course_id == course_id, Chapter.deleted_at.is_(None)).all()
    }

    named_modules = [module_id for module_id, _ in places if module_id is not None]
    named_chapters = [chapter_id for _, ids in places for chapter_id in ids]
    if (
        len(named_modules) != len(set(named_modules))
        or set(named_modules) != set(modules)
        or len(named_chapters) != len(set(named_chapters))
        or set(named_chapters) != set(chapters)
    ):
        raise OutlineMismatchError("The outline must name every live module and lesson of the course exactly once")
    if any(module_id is None and len(ids) == 0 for module_id, ids in places):
        raise OutlineMismatchError("A place outside any module must hold a lesson")

    numbers = number_outline(places)
    for module_id, order in numbers.modules.items():
        module = modules[module_id]
        if module.order_index != order:
            module.order_index = order
    for chapter_id, (order, home) in numbers.chapters.items():
        chapter = chapters[chapter_id]
        if chapter.order_index != order:
            chapter.order_index = order
        if chapter.module_id != home:
            chapter.module_id = home
    db.flush()
