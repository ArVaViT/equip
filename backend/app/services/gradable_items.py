"""Every gradable item in a course, with the chapter it lives in.

Its own module because three things need the same list — the student's grade
view, the certificate explainer and (next) the gate — and routing it through any
one of them makes the other two import a service they have no business
importing. The first attempt did exactly that and produced an import cycle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.constants import GRADABLE_CHAPTER_TYPES
from app.models.assignment import Assignment
from app.models.course import Chapter, Module
from app.models.quiz import Quiz

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def course_items(db: Session, course_id: str) -> tuple[list[Any], list[Any]]:
    """Every gradable item in the course, with its chapter title.

    Soft-deleted chapters and modules are excluded here for the same reason the
    calculator excludes them: work in a deleted chapter is not owed.
    """
    base = (
        db.query(Chapter.id.label("chapter_id"), Chapter.title.label("chapter_title"))
        .join(Module, Module.id == Chapter.module_id)
        .filter(
            Module.course_id == course_id,
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
            Chapter.chapter_type.in_(GRADABLE_CHAPTER_TYPES),
        )
        .subquery()
    )
    quizzes = (
        db.query(Quiz.id, base.c.chapter_id, base.c.chapter_title)
        .join(base, base.c.chapter_id == Quiz.chapter_id)
        .all()
    )
    assignments = (
        db.query(Assignment.id, base.c.chapter_id, base.c.chapter_title, Assignment.max_score)
        .join(base, base.c.chapter_id == Assignment.chapter_id)
        .all()
    )
    return quizzes, assignments
