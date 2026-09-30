"""A director works inside one organization; cohorts are how they enrol people.

Two cohort routes did not check the organization (2026-09-30 audit):
adding a student fetched the cohort without scoping it, so a director could
enrol anyone in another school's cohort (and learn whether an email is
registered); attaching a course took any course, so an institute course of
another school could be attached and its invitations stepped round.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_optional_user
from app.core.database import get_db
from app.main import app
from app.models.cohort import Cohort
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.organization import Organization
from app.models.user import User, UserRole

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _org(db: Session, slug: str) -> Organization:
    org = Organization(slug=slug, public_name=slug.title())
    db.add(org)
    db.flush()
    return org


def _cohort(db: Session, org: Organization) -> Cohort:
    c = Cohort(
        organization_id=org.id,
        start_date=datetime(2026, 10, 1, tzinfo=UTC),
        end_date=datetime(2026, 12, 1, tzinfo=UTC),
    )
    db.add(c)
    db.flush()
    return c


@pytest.fixture()
def world(db: Session):
    a, b = _org(db, "school-a"), _org(db, "school-b")
    director = User(id=uuid.uuid4(), email="dir-a@example.com", role=UserRole.DIRECTOR.value, organization_id=a.id)
    student = User(id=uuid.uuid4(), email="pupil@example.com", role=UserRole.STUDENT.value)
    db.add_all([director, student])
    db.flush()
    cohort_a, cohort_b = _cohort(db, a), _cohort(db, b)
    own_institute = Course(id="c-own-inst", status="published", access_mode="institute", organization_id=a.id)
    other_institute = Course(id="c-other-inst", status="published", access_mode="institute", organization_id=b.id)
    other_public = Course(id="c-other-pub", status="published", access_mode="public", organization_id=b.id)
    db.add_all([own_institute, other_institute, other_public])
    db.commit()
    return {"director": director, "student": student, "cohort_a": cohort_a, "cohort_b": cohort_b}


@pytest.fixture()
def as_director(db: Session, world):
    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: world["director"]
    app.dependency_overrides[get_optional_user] = lambda: world["director"]
    with TestClient(app, raise_server_exceptions=True) as tc:
        yield tc
    app.dependency_overrides.clear()


def test_a_director_cannot_add_anyone_to_another_schools_cohort(as_director: TestClient, world, db: Session) -> None:
    r = as_director.post(f"/api/v1/cohorts/{world['cohort_b'].id}/students", json={"email": "pupil@example.com"})
    assert r.status_code == 404
    assert db.query(Enrollment).filter(Enrollment.user_id == world["student"].id).count() == 0


def test_a_director_can_add_to_their_own_cohort(as_director: TestClient, world) -> None:
    r = as_director.post(f"/api/v1/cohorts/{world['cohort_a'].id}/students", json={"email": "pupil@example.com"})
    assert r.status_code == 201, r.text


def test_another_schools_institute_course_cannot_be_attached(as_director: TestClient, world) -> None:
    r = as_director.post(f"/api/v1/cohorts/{world['cohort_a'].id}/courses", json={"course_id": "c-other-inst"})
    assert r.status_code == 404


def test_their_own_institute_course_and_any_public_one_can(as_director: TestClient, world) -> None:
    assert (
        as_director.post(
            f"/api/v1/cohorts/{world['cohort_a'].id}/courses", json={"course_id": "c-own-inst"}
        ).status_code
        == 201
    )
    assert (
        as_director.post(
            f"/api/v1/cohorts/{world['cohort_a'].id}/courses", json={"course_id": "c-other-pub"}
        ).status_code
        == 201
    )
