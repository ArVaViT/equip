"""Every public course carries the name of the school behind it.

Decision 3 of the engineering plan's §8: the catalogue names the
organization behind every public course, next to the title, before
enrolling. It is the plain answer to "who is teaching me", and it is
what makes ``public_name`` worth defending — a name nobody sees is not a
name anyone can misuse or protect.

The name is **not** localized. It is what the organization's
certificates print, and showing one thing in the catalogue while
printing another on the document is how a name stops meaning anything.
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

SCHOOL_ID = uuid.UUID("cccccccc-9999-8888-7777-666666666666")


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
    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc
    app.dependency_overrides.clear()


def _published_course(db: Session, owner: User, course_id: str, *, organization_id=SCHOOL_ID):
    course = make_course_with_text(
        db,
        course_id=course_id,
        title="Genesis, chapter one",
        description="A first course",
        status="published",
        created_by=owner.id,
    )
    course.organization_id = organization_id
    course.access_mode = "public"
    db.commit()
    return course


def _card(body: list[dict], course_id: str) -> dict:
    matches = [c for c in body if c["id"] == course_id]
    assert matches, f"{course_id} is not in the catalogue"
    return matches[0]


class TestTheCatalogueNamesTheSchool:
    def test_a_public_course_carries_its_organization(
        self, stranger_client: TestClient, db: Session, their_teacher: User
    ):
        _published_course(db, their_teacher, "ucoat-genesis")

        resp = stranger_client.get("/api/v1/courses")

        assert resp.status_code == 200, resp.text
        card = _card(resp.json(), "ucoat-genesis")
        assert card["organization_name"] == "UCOAT"
        assert card["organization_slug"] == "ucoat", "the slug is what /s/<slug> needs to link there"

    def test_the_name_is_not_translated(self, stranger_client: TestClient, db: Session, their_teacher: User):
        """A certificate prints ``public_name``. If the catalogue showed a
        translated version, the document and the page would disagree about
        the name of the same school."""
        _published_course(db, their_teacher, "ucoat-untranslated")

        for language in ("en", "de", "uk", "ru"):
            body = stranger_client.get("/api/v1/courses", headers={"Accept-Language": language}).json()
            assert _card(body, "ucoat-untranslated")["organization_name"] == "UCOAT", (
                f"the school's name changed when read in {language}"
            )

    def test_each_card_names_its_own_school(self, stranger_client: TestClient, db: Session, their_teacher: User):
        """Two schools in one catalogue, each course under its own name.

        ``courses.organization_id`` is NOT NULL, so there is no such thing
        as a course belonging to nobody — the interesting failure is not a
        missing name but the wrong one, carried over from the previous row.
        """
        other = Organization(id=uuid.uuid4(), slug="other-school", public_name="Other School")
        db.add(other)
        db.flush()
        _published_course(db, their_teacher, "ucoat-course")
        _published_course(db, their_teacher, "other-course", organization_id=other.id)

        body = stranger_client.get("/api/v1/courses").json()

        assert _card(body, "ucoat-course")["organization_name"] == "UCOAT"
        assert _card(body, "other-course")["organization_name"] == "Other School"
