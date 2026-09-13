"""Whether a student may open a chapter — decided by the server.

``chapters.is_locked`` was a drawing. The web app dimmed the row and hid
its link, and nothing else in the system knew: ``GET
/blocks/chapter/{id}`` handed the lesson to anybody enrolled, and the
chapter itself to anybody who typed its id into the URL. A lock only the
client honours is a suggestion.

The rule, in reading order within the course:

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

from typing import TYPE_CHECKING

from app.constants import GRADABLE_CHAPTER_TYPES
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session


def _predecessor(db: Session, chapter: Chapter) -> Chapter | None:
    """The chapter a reader meets just before this one.

    Reading order is ``order_index`` across the whole course. Modules
    group chapters for display; they do not restart the count, and a
    chapter in no module is still in the order.
    """
    return (
        db.query(Chapter)
        .filter(
            Chapter.course_id == chapter.course_id,
            Chapter.deleted_at.is_(None),
            Chapter.order_index < chapter.order_index,
        )
        .order_by(Chapter.order_index.desc())
        .first()
    )


def chapter_is_open_to(db: Session, chapter: Chapter, user_id: uuid.UUID) -> bool:
    """``False`` when this reader has not earned their way in yet."""
    if not chapter.is_locked:
        return True

    previous = _predecessor(db, chapter)
    if previous is None or previous.chapter_type not in GRADABLE_CHAPTER_TYPES:
        return False

    earned = (
        db.query(ChapterProgress.chapter_id)
        .filter(
            ChapterProgress.user_id == user_id,
            ChapterProgress.chapter_id == previous.id,
            ChapterProgress.completed.is_(True),
        )
        .first()
    )
    return earned is not None
