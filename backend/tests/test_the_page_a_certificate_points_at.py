"""`/s/<slug>` is read by people who followed a link off a diploma.

An employer holds a certificate, sees a school name and a number, and
comes here to find out whether the school is real. That makes three
things load-bearing:

* the page answers **without a token** — the reader has no account;
* it shows the organization's **public** courses and never its
  ``institute`` ones, which belong to its own students;
* a **suspended** organization keeps its page and loses its courses.
  Deleting the page would break every certificate that points at it, and
  a certificate records work done while the school was in good standing.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app
from app.models.organization import Organization
from app.models.user import User, UserRole
from tests._cv_helpers import make_course_with_text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

SCHOOL_ID = uuid.UUID("cccccccc-1111-2222-3333-444444444444")


@pytest.fixture()
def school(db: Session) -> Organization:
    organization = Organization(
        id=SCHOOL_ID,
        slug="ucoat",
        public_name="UCOAT",
        country="UA",
        status="verified",
    )
    db.add(organization)
    db.commit()
    return organization


@pytest.fixture()
def their_teacher(db: Session, school: Organization) -> User:
    user = User(
        id=uuid.uuid4(),
        email="teacher@ucoat.example",
        full_name="Their Teacher",
        role=UserRole.TEACHER.value,
        organization_id=SCHOOL_ID,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture()
def stranger_client(db: Session):
    """Nobody at all — no token, no account."""

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc
    app.dependency_overrides.clear()


def _course(db: Session, owner: User, course_id: str, *, access_mode: str, status: str = "published"):
    course = make_course_with_text(
        db,
        course_id=course_id,
        title=f"Course {course_id}",
        description="",
        status=status,
        created_by=owner.id,
    )
    course.organization_id = SCHOOL_ID
    course.access_mode = access_mode
    db.commit()
    return course


class TestTheStrangerCanRead:
    def test_the_page_answers_without_a_token(self, stranger_client: TestClient, school: Organization):
        resp = stranger_client.get("/api/v1/organizations/ucoat")

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["public_name"] == "UCOAT"
        assert body["country"] == "UA"
        assert body["active"] is True
        assert body["verified"] is True

    def test_an_unknown_slug_is_a_404(self, stranger_client: TestClient):
        resp = stranger_client.get("/api/v1/organizations/no-such-school")
        assert resp.status_code == 404, resp.text

    def test_the_page_carries_no_internal_bookkeeping(self, stranger_client: TestClient, school: Organization):
        """A reader of a diploma has no business seeing member counts,
        director emails or the admission status string."""
        body = stranger_client.get("/api/v1/organizations/ucoat").json()

        for leaked in ("member_count", "director_emails", "status", "legal_name", "verification_basis"):
            assert leaked not in body, f"{leaked} is on the public page"


class TestWhichCoursesShow:
    def test_public_courses_are_listed(self, stranger_client: TestClient, db: Session, their_teacher: User):
        _course(db, their_teacher, "ucoat-public", access_mode="public")

        body = stranger_client.get("/api/v1/organizations/ucoat").json()

        assert [c["id"] for c in body["courses"]] == ["ucoat-public"]

    def test_institute_courses_are_not(self, stranger_client: TestClient, db: Session, their_teacher: User):
        _course(db, their_teacher, "ucoat-institute", access_mode="institute")

        body = stranger_client.get("/api/v1/organizations/ucoat").json()

        assert body["courses"] == [], "an institute course is on the public page"

    def test_drafts_are_not(self, stranger_client: TestClient, db: Session, their_teacher: User):
        _course(db, their_teacher, "ucoat-draft", access_mode="public", status="draft")

        body = stranger_client.get("/api/v1/organizations/ucoat").json()

        assert body["courses"] == []

    def test_another_organizations_course_is_not(self, stranger_client: TestClient, db: Session, their_teacher: User):
        other = Organization(id=uuid.uuid4(), slug="other-school", public_name="Other School")
        db.add(other)
        db.flush()
        course = _course(db, their_teacher, "not-ucoat", access_mode="public")
        course.organization_id = other.id
        db.commit()

        body = stranger_client.get("/api/v1/organizations/ucoat").json()

        assert body["courses"] == []


class TestSuspension:
    def test_a_suspended_school_keeps_its_page_and_loses_its_courses(
        self, stranger_client: TestClient, db: Session, their_teacher: User, school: Organization
    ):
        _course(db, their_teacher, "ucoat-was-public", access_mode="public")
        school.status = "suspended"
        db.commit()

        resp = stranger_client.get("/api/v1/organizations/ucoat")

        assert resp.status_code == 200, "the page a certificate points at disappeared"
        body = resp.json()
        assert body["public_name"] == "UCOAT"
        assert body["active"] is False
        assert body["verified"] is False
        assert body["courses"] == []
