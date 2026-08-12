"""Marking against a rubric.

A grade that is one person's impression cannot be discussed. A grade that is
four named criteria with a level chosen on each can be — by the student who
disagrees, by the director who signs the ведомость, and by the teacher
themselves on the twentieth essay of an evening.

The rules under test are the two that decide where the truth lives: the
decision recorded is the level rather than the number, and the rubric's total
is the assignment's maximum rather than a second number kept in step by hand.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.assignment import Assignment, AssignmentSubmission
from app.models.course import Chapter, Course, Module
from app.models.rubric import AssignmentRubric, Rubric, RubricCriterion, RubricLevel, RubricMark
from app.services import rubric_service

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

from .conftest import STUDENT_ID, TEACHER_ID


def _course_with_assignment(db: Session, course_id: str):
    course = Course(id=course_id, status="published", created_by=TEACHER_ID, grading_scheme="letter")
    db.add(course)
    module = Module(id=f"{course_id}-m", course_id=course_id, order_index=0, title="M")
    db.add(module)
    db.flush()
    chapter = Chapter(id=f"{course_id}-a", module_id=module.id, order_index=0, chapter_type="assignment", title="Эссе")
    db.add(chapter)
    db.flush()
    assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=100)
    db.add(assignment)
    db.flush()
    return course, assignment


def _rubric(db: Session, course_id: str, *, criteria: list[list[int]], reversed_levels: bool = False):
    """`criteria` is a list of point values per criterion, best last by default."""
    rubric = Rubric(id=uuid.uuid4(), course_id=course_id, title="Эссе", created_by=TEACHER_ID)
    db.add(rubric)
    db.flush()
    made = []
    for i, points in enumerate(criteria):
        criterion = RubricCriterion(id=uuid.uuid4(), rubric_id=rubric.id, order_index=i, title=f"Критерий {i}")
        db.add(criterion)
        db.flush()
        levels = []
        ordered = list(reversed(points)) if reversed_levels else points
        for j, value in enumerate(ordered):
            level = RubricLevel(id=uuid.uuid4(), criterion_id=criterion.id, order_index=j, label=f"L{j}", points=value)
            db.add(level)
            levels.append(level)
        db.flush()
        made.append((criterion, levels))
    return rubric, made


def _submission(db: Session, assignment):
    submission = AssignmentSubmission(
        id=uuid.uuid4(),
        assignment_id=assignment.id,
        student_id=STUDENT_ID,
        status="submitted",
        content="Работа",
    )
    db.add(submission)
    db.flush()
    return submission


def test_the_maximum_is_the_best_level_of_every_criterion(db: Session, teacher) -> None:
    course, _assignment = _course_with_assignment(db, "rb-max")
    rubric, _ = _rubric(db, course.id, criteria=[[0, 5, 10], [0, 4, 8]])
    db.commit()

    assert rubric_service.rubric_max_score(db, rubric.id) == 18


def test_the_maximum_does_not_depend_on_how_the_levels_are_arranged(db: Session, teacher) -> None:
    """A rubric written best-first is as legitimate as one written worst-first.
    Reading the maximum off the last level would quietly halve one school's
    marks and look perfectly correct doing it."""
    course, _assignment = _course_with_assignment(db, "rb-order")
    rubric, _ = _rubric(db, course.id, criteria=[[0, 5, 10]], reversed_levels=True)
    db.commit()

    assert rubric_service.rubric_max_score(db, rubric.id) == 10


def test_the_score_is_read_through_the_level(db: Session, teacher, student) -> None:
    course, assignment = _course_with_assignment(db, "rb-score")
    _unused_rubric, made = _rubric(db, course.id, criteria=[[0, 5, 10], [0, 4, 8]])
    submission = _submission(db, assignment)
    for criterion, levels in made:
        db.add(
            RubricMark(
                id=uuid.uuid4(),
                submission_id=submission.id,
                criterion_id=criterion.id,
                level_id=levels[1].id,
                marked_by=TEACHER_ID,
            )
        )
    db.commit()

    assert rubric_service.score_from_marks(db, submission.id) == (9, 18)


def test_editing_a_level_moves_every_mark_that_rests_on_it(db: Session, teacher, student) -> None:
    """Gradescope's best idea, and the reason nothing stores the number: a
    school deciding a level is worth eight rather than seven edits it once instead of
    a teacher reopening finished essays by hand."""
    course, assignment = _course_with_assignment(db, "rb-retro")
    _unused_rubric, made = _rubric(db, course.id, criteria=[[0, 5, 10]])
    submission = _submission(db, assignment)
    criterion, levels = made[0]
    db.add(
        RubricMark(
            id=uuid.uuid4(),
            submission_id=submission.id,
            criterion_id=criterion.id,
            level_id=levels[1].id,
            marked_by=TEACHER_ID,
        )
    )
    db.commit()
    assert rubric_service.score_from_marks(db, submission.id) == (5, 10)

    levels[1].points = 8
    db.commit()

    assert rubric_service.score_from_marks(db, submission.id) == (8, 10)


def test_a_half_marked_essay_does_not_read_as_full_marks(db: Session, teacher, student) -> None:
    """`out_of` comes from the rubric, not from the marks made so far. Reading
    it off the marks would show a teacher who has done one criterion of four a
    student sitting at 100%."""
    course, assignment = _course_with_assignment(db, "rb-partial")
    _unused_rubric, made = _rubric(db, course.id, criteria=[[0, 10], [0, 10]])
    submission = _submission(db, assignment)
    criterion, levels = made[0]
    db.add(
        RubricMark(
            id=uuid.uuid4(),
            submission_id=submission.id,
            criterion_id=criterion.id,
            level_id=levels[1].id,
            marked_by=TEACHER_ID,
        )
    )
    db.commit()

    assert rubric_service.score_from_marks(db, submission.id) == (10, 20)


def test_attaching_a_rubric_makes_its_total_the_assignments_maximum(db: Session, teacher) -> None:
    """An assignment marked out of 100 with a rubric adding up to 40 gives
    every student 40% of what they earned, and the arithmetic looks correct the
    whole way down."""
    course, assignment = _course_with_assignment(db, "rb-sync")
    rubric, _ = _rubric(db, course.id, criteria=[[0, 20], [0, 20]])
    db.add(AssignmentRubric(assignment_id=assignment.id, rubric_id=rubric.id, attached_by=TEACHER_ID))
    db.commit()

    rubric_service.sync_assignment_max_score(db, assignment.id, rubric.id)
    db.commit()

    assert assignment.max_score == 40


def test_an_empty_rubric_does_not_zero_the_assignment(db: Session, teacher) -> None:
    """A rubric being written has no levels yet. Setting `max_score = 0` at
    that moment makes every mark on it a division by zero somewhere downstream."""
    course, assignment = _course_with_assignment(db, "rb-empty")
    rubric = Rubric(id=uuid.uuid4(), course_id=course.id, title="Пустая", created_by=TEACHER_ID)
    db.add(rubric)
    db.commit()

    rubric_service.sync_assignment_max_score(db, assignment.id, rubric.id)
    db.commit()

    assert assignment.max_score == 100


def test_an_archived_criterion_leaves_the_grid_but_not_the_record(db: Session, teacher, student) -> None:
    """It stops being offered and stays readable through the marks that
    reference it — which is the whole reason it is archived rather than
    deleted."""
    from datetime import UTC, datetime

    course, _assignment = _course_with_assignment(db, "rb-archived")
    rubric, made = _rubric(db, course.id, criteria=[[0, 10], [0, 10]])
    made[0][0].archived_at = datetime.now(UTC)
    db.commit()

    payload = rubric_service.rubric_payload(db, rubric)

    assert len(payload["criteria"]) == 1
    assert payload["max_score"] == 10, "and the maximum follows, so a partial grid is not marked out of the old total"


def test_the_student_sees_the_same_grid_as_the_teacher(db: Session, teacher, student) -> None:
    """A rubric shown only to the person marking is a private opinion with
    arithmetic on it."""
    course, _assignment = _course_with_assignment(db, "rb-shared")
    rubric, _ = _rubric(db, course.id, criteria=[[0, 5, 10]])
    db.commit()

    payload = rubric_service.rubric_payload(db, rubric)

    assert [lvl["points"] for lvl in payload["criteria"][0]["levels"]] == [0, 5, 10]
    assert payload["criteria"][0]["title"] == "Критерий 0"
