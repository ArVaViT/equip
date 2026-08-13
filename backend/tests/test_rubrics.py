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


# ---------------------------------------------------------------------------
# The routes
# ---------------------------------------------------------------------------


def _attach(db: Session, assignment, rubric) -> None:
    db.add(AssignmentRubric(assignment_id=assignment.id, rubric_id=rubric.id, attached_by=TEACHER_ID))
    db.commit()


def test_a_rubric_arrives_whole(client, db: Session, teacher) -> None:
    """Criteria and levels in one call. A rubric that exists with two of its
    four criteria is a marking standard nobody agreed to — and it is the state
    every failed save would leave behind."""
    course, _assignment = _course_with_assignment(db, "rb-create")
    db.commit()

    response = client.post(
        "/api/v1/rubrics",
        json={
            "course_id": course.id,
            "title": "Эссе",
            "criteria": [
                {"title": "Опора на текст", "levels": [{"label": "нет", "points": 0}, {"label": "есть", "points": 10}]}
            ],
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["max_score"] == 10
    assert len(body["criteria"][0]["levels"]) == 2


def test_a_criterion_needs_more_than_one_level(client, db: Session, teacher) -> None:
    """A criterion with a single level is not a judgement, it is a label."""
    course, _assignment = _course_with_assignment(db, "rb-onelevel")
    db.commit()

    response = client.post(
        "/api/v1/rubrics",
        json={
            "course_id": course.id,
            "title": "Эссе",
            "criteria": [{"title": "Одно", "levels": [{"label": "есть", "points": 10}]}],
        },
    )

    assert response.status_code == 422


def test_a_rubric_from_another_course_cannot_be_attached(client, db: Session, teacher) -> None:
    """Otherwise one course's standard silently rewrites another's maximum."""
    _course_a, assignment = _course_with_assignment(db, "rb-mine")
    other_course, _other_assignment = _course_with_assignment(db, "rb-theirs")
    foreign, _ = _rubric(db, other_course.id, criteria=[[0, 10]])
    db.commit()

    response = client.post(f"/api/v1/rubrics/attach/{assignment.id}?rubric_id={foreign.id}")

    assert response.status_code == 400


def test_marking_every_criterion_grades_the_work(client, db: Session, teacher, student) -> None:
    course, assignment = _course_with_assignment(db, "rb-mark")
    rubric, made = _rubric(db, course.id, criteria=[[0, 5, 10], [0, 4, 8]])
    _attach(db, assignment, rubric)
    submission = _submission(db, assignment)
    db.commit()

    response = client.put(
        f"/api/v1/rubrics/submission/{submission.id}/marks",
        json={
            "marks": [
                {"criterion_id": str(made[0][0].id), "level_id": str(made[0][1][2].id)},
                {"criterion_id": str(made[1][0].id), "level_id": str(made[1][1][1].id)},
            ],
            "feedback": "Сильная работа",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["earned"] == 14
    db.refresh(submission)
    assert submission.status == "graded"
    assert submission.grade == 14
    assert submission.feedback == "Сильная работа"


def test_a_half_filled_grid_is_not_a_grade(client, db: Session, teacher, student) -> None:
    """Marking is incremental — the teacher works down the criteria and the
    queue autosaves. Publishing that as a mark tells a student they scored 40%
    when the third criterion has simply not been reached."""
    course, assignment = _course_with_assignment(db, "rb-partial-route")
    rubric, made = _rubric(db, course.id, criteria=[[0, 10], [0, 10]])
    _attach(db, assignment, rubric)
    submission = _submission(db, assignment)
    db.commit()

    response = client.put(
        f"/api/v1/rubrics/submission/{submission.id}/marks",
        json={"marks": [{"criterion_id": str(made[0][0].id), "level_id": str(made[0][1][1].id)}]},
    )

    assert response.status_code == 200, response.text
    db.refresh(submission)
    assert submission.status == "submitted", "still waiting on the teacher"
    assert submission.grade is None, "and no number has reached the student"


def test_a_level_from_another_rubric_buys_nothing(client, db: Session, teacher, student) -> None:
    """The chain — level belongs to criterion, criterion to the rubric, rubric
    to this assignment. Without it a level id from anywhere on the platform is
    an arbitrary number of points, and the result looks like an ordinary mark
    in every record afterwards."""
    course, assignment = _course_with_assignment(db, "rb-idor")
    rubric, made = _rubric(db, course.id, criteria=[[0, 10]])
    _other, other_made = _rubric(db, course.id, criteria=[[0, 1000]])
    _attach(db, assignment, rubric)
    submission = _submission(db, assignment)
    db.commit()

    response = client.put(
        f"/api/v1/rubrics/submission/{submission.id}/marks",
        json={"marks": [{"criterion_id": str(made[0][0].id), "level_id": str(other_made[0][1][1].id)}]},
    )

    assert response.status_code == 400, response.text
    db.refresh(submission)
    assert submission.grade is None


def test_a_student_reads_their_own_grid(student_client, db: Session, teacher, student) -> None:
    """A rubric shown only to the person marking is a private opinion with
    arithmetic on it."""
    course, assignment = _course_with_assignment(db, "rb-student")
    rubric, made = _rubric(db, course.id, criteria=[[0, 10]])
    _attach(db, assignment, rubric)
    submission = _submission(db, assignment)
    db.add(
        RubricMark(
            id=uuid.uuid4(),
            submission_id=submission.id,
            criterion_id=made[0][0].id,
            level_id=made[0][1][1].id,
            marked_by=TEACHER_ID,
        )
    )
    db.commit()

    body = student_client.get(f"/api/v1/rubrics/submission/{submission.id}").json()

    assert body["rubric"]["criteria"][0]["title"] == "Критерий 0"
    assert body["marks"][0]["points"] == 10


def test_a_student_cannot_read_somebody_elses(student_client, db: Session, teacher, student) -> None:
    from app.models.user import User as UserModel

    course, assignment = _course_with_assignment(db, "rb-nosy")
    rubric, _ = _rubric(db, course.id, criteria=[[0, 10]])
    _attach(db, assignment, rubric)
    other = UserModel(id=uuid.uuid4(), email="other-rb@example.com", full_name="Другой", role="student")
    db.add(other)
    db.flush()
    submission = AssignmentSubmission(
        id=uuid.uuid4(), assignment_id=assignment.id, student_id=other.id, status="submitted", content="Чужое"
    )
    db.add(submission)
    db.commit()

    assert student_client.get(f"/api/v1/rubrics/submission/{submission.id}").status_code == 403
