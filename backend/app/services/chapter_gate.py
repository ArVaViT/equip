"""Whether a student may open a chapter — decided by the server.

``chapters.is_locked`` was a drawing. The web app dimmed the row and hid
its link, and nothing else in the system knew: ``GET
/blocks/chapter/{id}`` handed the lesson to anybody enrolled, and the
chapter itself to anybody who typed its id into the URL. A lock only the
client honours is a suggestion.

The rule, in reading order within the course (``course_structure``):

* A chapter without ``is_locked`` is open. Most are.
* A locked chapter opens once the reader has completed the chapter
  before it — but only when that one is something a person *can*
  complete. Readings carry no completion of their own.
* A locked chapter whose predecessor cannot be completed — or that has
  no predecessor at all — stays shut. There is nothing to earn, so this
  is the teacher's own lock: the lesson is not ready, or not yet
  theirs to read. Until 2026-09-12 this case silently unlocked, which
  is how three unwritten lessons of a live course stood open.

Owners and admins are not gated; the caller settles that before asking.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from app.constants import GRADABLE_CHAPTER_TYPES
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Module
from app.services.course_structure import build_spine
from app.services.staged_edits.visibility import chapter_awaits_first_release

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session


def _predecessors(db: Session, chapters: list[Chapter]) -> dict[str, Chapter | None]:
    """The chapter a reader meets just before each of these.

    Reading order is the course's one sequence (``course_structure``):
    modules and the lessons outside them in the places the teacher gave
    them, a module's lessons consecutive under it. It used to be the
    lesson numbers alone, which only agreed with what the student sees
    while nobody had moved anything.

    A chapter held for its first release is not in the reader's order
    yet: a quiz nobody can open cannot be the thing a locked lesson waits
    on (2026-10-03).

    One course's order is built once for all of its chapters asked about:
    the calendar asks about every locked lesson of every course a reader
    is in, on every load and every iCal poll.
    """
    by_course: dict[str, list[Chapter]] = defaultdict(list)
    for chapter in chapters:
        by_course[chapter.course_id].append(chapter)
    out: dict[str, Chapter | None] = {}
    for course_id, asked in by_course.items():
        modules = db.query(Module).filter(Module.course_id == course_id, Module.deleted_at.is_(None)).all()
        order = (
            db.query(Chapter)
            .filter(
                Chapter.course_id == course_id,
                Chapter.deleted_at.is_(None),
                ~chapter_awaits_first_release(),
            )
            .all()
        )
        present = {c.id for c in order}
        order.extend(c for c in asked if c.id not in present)
        spine = build_spine(modules, order)
        for chapter in asked:
            out[str(chapter.id)] = spine.predecessor_of(chapter.id)
    return out


def chapters_closed_to(db: Session, chapters: list[Chapter], user_id: uuid.UUID) -> set[str]:
    """Ids of the chapters among ``chapters`` this reader may not open yet.

    The rule of the module docstring, asked of many chapters at once: one
    reading order per course and one progress query for all of them.
    """
    locked = [c for c in chapters if c.is_locked]
    if not locked:
        return set()
    previous = _predecessors(db, locked)
    earnable = {
        chapter_id: prev.id
        for chapter_id, prev in previous.items()
        if prev is not None and prev.chapter_type in GRADABLE_CHAPTER_TYPES
    }
    earned: set[str] = set()
    if earnable:
        earned = {
            str(chapter_id)
            for (chapter_id,) in db.query(ChapterProgress.chapter_id).filter(
                ChapterProgress.user_id == user_id,
                ChapterProgress.chapter_id.in_(set(earnable.values())),
                ChapterProgress.completed.is_(True),
            )
        }
    return {chapter_id for chapter_id in previous if str(earnable.get(chapter_id)) not in earned}


def chapter_is_open_to(db: Session, chapter: Chapter, user_id: uuid.UUID) -> bool:
    """``False`` when this reader has not earned their way in yet."""
    return str(chapter.id) not in chapters_closed_to(db, [chapter], user_id)
