"""A clone is the cloner's course, in the cloner's school.

Two things were wrong with ``POST /courses/{id}/clone`` until 2026-10-03:

* the copy was built without ``organization_id``. Production has no default
  on that column, so every clone failed there; the suite passed only because
  conftest fills the column on new rows;
* the route never asked whether the cloner may see the course. An
  «institute» course is its school's alone — the course page answers 404 to
  anyone else — yet a teacher of any school could copy one whole.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.models.course import Course, Module
from app.models.organization import Organization
from tests._cv_helpers import make_course_with_text
from tests.conftest import ADMIN_ID

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User

PREFIX = "/api/v1/courses"
OTHER_ORGANIZATION_ID = uuid.UUID("eeeeeeee-1111-1111-1111-eeeeeeeeeeee")


def _other_school(db: Session) -> None:
    db.add(Organization(id=OTHER_ORGANIZATION_ID, slug="another-school", public_name="Another School"))
    db.commit()


def _published(db: Session, *, access_mode: str, organization_id: uuid.UUID | None = None) -> Course:
    course = make_course_with_text(db, title="Acts", status="published", created_by=ADMIN_ID, access_mode=access_mode)
    if organization_id is not None:
        course.organization_id = organization_id
        db.commit()
    return course


def test_another_schools_closed_course_cannot_be_copied(client: TestClient, db: Session, admin: User) -> None:
    _other_school(db)
    course = _published(db, access_mode="institute", organization_id=OTHER_ORGANIZATION_ID)

    resp = client.post(f"{PREFIX}/{course.id}/clone")

    assert resp.status_code == 404
    assert db.query(Course).count() == 1


def test_the_copy_lands_in_the_cloners_school(client: TestClient, db: Session, admin: User, teacher: User) -> None:
    _other_school(db)
    course = _published(db, access_mode="public")
    teacher.organization_id = OTHER_ORGANIZATION_ID
    db.commit()

    resp = client.post(f"{PREFIX}/{course.id}/clone")

    assert resp.status_code == 201, resp.text
    clone = db.query(Course).filter(Course.id == resp.json()["id"]).one()
    assert clone.organization_id == OTHER_ORGANIZATION_ID


def test_the_copy_starts_without_last_terms_dates(client: TestClient, db: Session, admin: User) -> None:
    course = _published(db, access_mode="public")
    db.add(Module(id=str(uuid.uuid4()), course_id=course.id, order_index=0, due_date=datetime(2026, 9, 1, tzinfo=UTC)))
    db.commit()

    resp = client.post(f"{PREFIX}/{course.id}/clone")

    assert resp.status_code == 201, resp.text
    copied = db.query(Module).filter(Module.course_id == resp.json()["id"]).one()
    assert copied.due_date is None


def test_the_copy_keeps_who_may_see_it_and_its_ai_policy(client: TestClient, db: Session, admin: User) -> None:
    course = _published(db, access_mode="institute")
    course.ai_policy = "ai_forbidden"
    db.commit()

    resp = client.post(f"{PREFIX}/{course.id}/clone")

    assert resp.status_code == 201, resp.text
    clone = db.query(Course).filter(Course.id == resp.json()["id"]).one()
    assert clone.access_mode == "institute"
    assert clone.ai_policy == "ai_forbidden"


def test_the_copy_is_marked_by_the_same_rubric(client: TestClient, db: Session, admin: User) -> None:
    from app.models.assignment import Assignment
    from app.models.course import Chapter
    from app.models.rubric import AssignmentRubric, Rubric, RubricCriterion, RubricLevel
    from app.services.rubric_service import rubric_max_score

    course = _published(db, access_mode="public")
    chapter = Chapter(
        id=str(uuid.uuid4()), course_id=course.id, order_index=0, chapter_type="assignment", title="Essay"
    )
    db.add(chapter)
    db.flush()
    assignment = Assignment(id=uuid.uuid4(), chapter_id=chapter.id, max_score=7)
    rubric = Rubric(id=uuid.uuid4(), course_id=course.id, title="Essay")
    db.add_all([assignment, rubric])
    db.flush()
    for i, points in enumerate([3, 4]):
        criterion = RubricCriterion(id=uuid.uuid4(), rubric_id=rubric.id, order_index=i, title=f"Criterion {i}")
        db.add(criterion)
        db.flush()
        db.add_all(
            [
                RubricLevel(id=uuid.uuid4(), criterion_id=criterion.id, order_index=0, label="no", points=0),
                RubricLevel(id=uuid.uuid4(), criterion_id=criterion.id, order_index=1, label="yes", points=points),
            ]
        )
    db.add(AssignmentRubric(assignment_id=assignment.id, rubric_id=rubric.id))
    db.commit()

    resp = client.post(f"{PREFIX}/{course.id}/clone")

    assert resp.status_code == 201, resp.text
    copied_rubric = db.query(Rubric).filter(Rubric.course_id == resp.json()["id"]).one()
    assert copied_rubric.id != rubric.id
    assert rubric_max_score(db, copied_rubric.id) == 7
    copied_chapter = db.query(Chapter).filter(Chapter.course_id == resp.json()["id"]).one()
    copied_assignment = db.query(Assignment).filter(Assignment.chapter_id == copied_chapter.id).one()
    attached = db.query(AssignmentRubric).filter(AssignmentRubric.assignment_id == copied_assignment.id).one()
    assert attached.rubric_id == copied_rubric.id
