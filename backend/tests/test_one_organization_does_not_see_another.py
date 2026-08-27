"""What an organization keeps to itself, and what it publishes.

Two decisions from 2026-08-26 meet here, and they pull in opposite
directions on purpose:

* A course marked ``public`` is public. It appears in the catalogue at
  equipbible.com whichever organization made it, with that
  organization's name beside it — that is what makes the name worth
  defending.
* A course marked ``institute`` belongs to its organization and to
  nobody else.

Before organizations existed the second sentence had nowhere to land, so
``institute`` courses sat in the public catalogue and their whole tree
was readable by anyone holding the id. These tests are the measurement
that found it, kept as the guard that it does not come back.

**404, not 403.** A 403 answers the question the request was really
asking — does this course exist. Course ids are short and guessable
enough to be worth not confirming, and the two people entitled to tell
"not yours" from "not there" — the owner and platform staff — see the
course either way.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_optional_user
from app.core.database import get_db
from app.main import app
from app.models.organization import Organization
from app.models.user import User, UserRole
from tests._cv_helpers import make_course_with_text
from tests.conftest import TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

OTHER_ORGANIZATION_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


@pytest.fixture()
def other_organization(db: Session) -> Organization:
    organization = Organization(
        id=OTHER_ORGANIZATION_ID,
        slug="other-organization",
        public_name="Other Organization",
    )
    db.add(organization)
    db.commit()
    return organization


@pytest.fixture()
def their_teacher(db: Session, other_organization: Organization) -> User:
    user = User(
        id=uuid.uuid4(),
        email="theirs@example.com",
        full_name="Their Teacher",
        role=UserRole.TEACHER.value,
        organization_id=OTHER_ORGANIZATION_ID,
    )
    db.add(user)
    db.commit()
    return user


def _their_course(db: Session, owner: User, *, access_mode: str, course_id: str):
    course = make_course_with_text(
        db,
        course_id=course_id,
        title="Their Course",
        description="Not yours",
        status="published",
        created_by=owner.id,
    )
    course.organization_id = OTHER_ORGANIZATION_ID
    course.access_mode = access_mode
    db.commit()
    return course


@pytest.fixture()
def our_client(db: Session):
    """Signed in as a teacher of the *test* organization."""
    user = User(
        id=uuid.uuid4(),
        email="ours@example.com",
        full_name="Our Teacher",
        role=UserRole.TEACHER.value,
        organization_id=TEST_ORGANIZATION_ID,
    )
    db.add(user)
    db.commit()

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_optional_user] = lambda: user
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc
    app.dependency_overrides.clear()


def test_an_institute_course_is_not_in_the_public_catalogue(our_client: TestClient, db: Session, their_teacher: User):
    course = _their_course(db, their_teacher, access_mode="institute", course_id="theirs-institute")

    resp = our_client.get("/api/v1/courses")

    assert resp.status_code == 200
    assert course.id not in resp.text, "another organization's institute course is in the catalogue"


def test_an_institute_course_is_not_readable_by_id(our_client: TestClient, db: Session, their_teacher: User):
    course = _their_course(db, their_teacher, access_mode="institute", course_id="theirs-by-id")

    resp = our_client.get(f"/api/v1/courses/{course.id}")

    assert resp.status_code == 404, "another organization's institute course opened by id"


def test_a_public_course_of_another_organization_is_visible(our_client: TestClient, db: Session, their_teacher: User):
    """The other half, and it must stay this way.

    A public course is public. Hiding it would make the catalogue a list
    of one organization's work, which is not what was decided and not
    what the platform is for.
    """
    course = _their_course(db, their_teacher, access_mode="public", course_id="theirs-public")

    listed = our_client.get("/api/v1/courses")
    detail = our_client.get(f"/api/v1/courses/{course.id}")

    assert course.id in listed.text
    assert detail.status_code == 200


def test_our_own_institute_course_is_readable(our_client: TestClient, db: Session, teacher: User):
    """Belonging is what grants it, not owning."""
    course = make_course_with_text(
        db,
        course_id="ours-institute",
        title="Our Course",
        description="Ours",
        status="published",
        created_by=teacher.id,
    )
    course.access_mode = "institute"
    db.commit()

    resp = our_client.get(f"/api/v1/courses/{course.id}")

    assert resp.status_code == 200


def test_the_organizations_own_list_holds_both_kinds(our_client: TestClient, db: Session, teacher: User):
    ours_public = make_course_with_text(
        db, course_id="ours-public", title="Ours Public", description="", status="published", created_by=teacher.id
    )
    ours_institute = make_course_with_text(
        db, course_id="ours-inst", title="Ours Institute", description="", status="published", created_by=teacher.id
    )
    ours_institute.access_mode = "institute"
    db.commit()

    resp = our_client.get("/api/v1/courses/my-organization")

    assert resp.status_code == 200
    body = resp.text
    assert ours_public.id in body
    assert ours_institute.id in body


def test_the_organizations_own_list_stops_at_its_own(our_client: TestClient, db: Session, their_teacher: User):
    theirs = _their_course(db, their_teacher, access_mode="public", course_id="theirs-in-my-list")

    resp = our_client.get("/api/v1/courses/my-organization")

    assert resp.status_code == 200
    assert theirs.id not in resp.text
