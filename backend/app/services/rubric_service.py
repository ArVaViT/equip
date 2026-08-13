"""Marking against a rubric.

Design: `assessment-integrity-and-the-graders-day.md` §6.3.

Two rules carry this module, and both are about where the truth lives.

**The decision is the level; the number is read from it.** Nothing stores the
points a teacher "gave" — it stores which rung they chose. So a school that
decides a level is worth eight points rather than seven edits it once, and every mark resting
on it follows, instead of a teacher reopening finished essays by hand.

**The rubric's total is the assignment's maximum.** Not a second number kept in
step by hand: an assignment marked out of 100 with a rubric that adds up to 40
produces a mark that is arithmetically fine and means nothing. Attaching a
rubric sets `max_score`, and editing the rubric moves it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.models.assignment import Assignment
from app.models.rubric import (
    AssignmentRubric,
    Rubric,
    RubricCriterion,
    RubricLevel,
    RubricMark,
)

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session


def rubric_for_assignment(db: Session, assignment_id: UUID) -> Rubric | None:
    """The rubric this assignment is marked by, or ``None`` if it has none."""
    return (
        db.query(Rubric)
        .join(AssignmentRubric, AssignmentRubric.rubric_id == Rubric.id)
        .filter(AssignmentRubric.assignment_id == assignment_id, Rubric.archived_at.is_(None))
        .first()
    )


def live_criteria(db: Session, rubric_id: UUID) -> list[RubricCriterion]:
    """Criteria still in force, in the order the teacher arranged them.

    Archived criteria are excluded here and remain readable through the marks
    that reference them — which is the whole reason they are archived rather
    than deleted.
    """
    return (
        db.query(RubricCriterion)
        .filter(RubricCriterion.rubric_id == rubric_id, RubricCriterion.archived_at.is_(None))
        .order_by(RubricCriterion.order_index, RubricCriterion.title)
        .all()
    )


def live_levels(db: Session, criterion_ids: list[UUID]) -> dict[UUID, list[RubricLevel]]:
    """``{criterion_id: [levels]}``, one query rather than one per criterion."""
    if not criterion_ids:
        return {}
    rows = (
        db.query(RubricLevel)
        .filter(RubricLevel.criterion_id.in_(criterion_ids), RubricLevel.archived_at.is_(None))
        .order_by(RubricLevel.order_index, RubricLevel.label)
        .all()
    )
    out: dict[UUID, list[RubricLevel]] = {}
    for level in rows:
        out.setdefault(level.criterion_id, []).append(level)
    return out


def rubric_max_score(db: Session, rubric_id: UUID) -> int:
    """What a perfect piece of work is worth: the top level of each criterion.

    The top level, not the last one — a rubric whose levels are arranged worst
    to best is as legitimate as one arranged best to worst, and reading the
    maximum off the order would quietly halve one school's marks.
    """
    criteria = live_criteria(db, rubric_id)
    levels = live_levels(db, [c.id for c in criteria])
    return sum(max((lvl.points for lvl in levels.get(c.id, [])), default=0) for c in criteria)


def score_from_marks(db: Session, submission_id: UUID) -> tuple[int, int]:
    """``(earned, out_of)`` for one submission, read through the levels.

    ``out_of`` comes from the rubric rather than from the marks, so a criterion
    the teacher has not reached yet still counts against the total — a
    half-marked essay must not read as full marks.
    """
    marks = db.query(RubricMark).filter(RubricMark.submission_id == submission_id).all()
    if not marks:
        return 0, 0
    level_ids = [m.level_id for m in marks]
    points: dict[Any, int] = {
        row[0]: int(row[1])
        for row in db.query(RubricLevel.id, RubricLevel.points).filter(RubricLevel.id.in_(level_ids)).all()
    }
    earned = sum(points.get(m.level_id, 0) for m in marks)

    criterion = db.query(RubricCriterion).filter(RubricCriterion.id == marks[0].criterion_id).first()
    out_of = rubric_max_score(db, criterion.rubric_id) if criterion else 0
    return earned, out_of


def sync_assignment_max_score(db: Session, assignment_id: UUID, rubric_id: UUID) -> None:
    """Make the assignment's maximum the rubric's total.

    One number, one place. An assignment marked out of 100 with a rubric adding
    up to 40 gives every student 40% of what they earned, and the arithmetic
    looks correct the whole way down.
    """
    total = rubric_max_score(db, rubric_id)
    if total <= 0:
        return
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if assignment is not None:
        assignment.max_score = total


def rubric_payload(db: Session, rubric: Rubric) -> dict[str, Any]:
    """The rubric as both sides see it — the same grid for teacher and student.

    A rubric shown only to the person marking is a private opinion with
    arithmetic on it (§6.3).
    """
    criteria = live_criteria(db, rubric.id)
    levels = live_levels(db, [c.id for c in criteria])
    return {
        "id": rubric.id,
        "course_id": rubric.course_id,
        "title": rubric.title,
        "max_score": rubric_max_score(db, rubric.id),
        "criteria": [
            {
                "id": c.id,
                "title": c.title,
                "description": c.description,
                "order_index": c.order_index,
                "levels": [
                    {
                        "id": lvl.id,
                        "label": lvl.label,
                        "points": lvl.points,
                        "description": lvl.description,
                        "order_index": lvl.order_index,
                    }
                    for lvl in levels.get(c.id, [])
                ],
            }
            for c in criteria
        ],
    }


def marks_payload(db: Session, submission_id: UUID) -> list[dict[str, Any]]:
    """What was chosen on each criterion for this piece of work."""
    marks = (
        db.query(RubricMark, RubricLevel.points)
        .join(RubricLevel, RubricLevel.id == RubricMark.level_id)
        .filter(RubricMark.submission_id == submission_id)
        .all()
    )
    return [
        {
            "criterion_id": mark.criterion_id,
            "level_id": mark.level_id,
            "points": int(points),
            "comment": mark.comment,
        }
        for mark, points in marks
    ]
