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
from datetime import UTC, datetime
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


# ── the page an organization is sold by (phase 4, 2026-10-03) ──────────


def _person(db: Session, name: str | None, role: str, *, email: str | None = None) -> User:
    from app.services.memberships import grant_membership

    user = User(
        id=uuid.uuid4(),
        email=email or f"{uuid.uuid4().hex[:8]}@ucoat.example",
        full_name=name,
        role=UserRole.STUDENT.value,
    )
    db.add(user)
    db.flush()
    grant_membership(db, user=user, organization_id=SCHOOL_ID, role=role, joined_via="appointment")
    db.commit()
    return user


def _client_as(db: Session, user: User | None):
    from app.api.dependencies import get_current_user, get_optional_user

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_optional_user] = lambda: user
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


class TestTheOrganizationIntroducesItself:
    def test_the_director_is_named_and_never_addressed(
        self, stranger_client: TestClient, db: Session, school: Organization
    ):
        _person(db, "Дмитрий Константинов", "director", email="director@ucoat.example")
        body = stranger_client.get("/api/v1/organizations/ucoat").json()
        assert body["directors"] == [{"full_name": "Дмитрий Константинов", "avatar_url": None}]
        assert "director@ucoat.example" not in str(body)

    def test_a_deactivated_account_is_not_counted(self, stranger_client: TestClient, db: Session, school: Organization):
        # Memberships outlive the account's deactivation; the numbers on the
        # page are about people who can sign in. Until 2026-10-03 the
        # director list left them out and the counts kept them.
        _person(db, "Director", "director")
        for i in range(10):
            _person(db, f"S{i}", "student")
        for i in range(3):
            _person(db, f"T{i}", "teacher")
        stats = stranger_client.get("/api/v1/organizations/ucoat").json()["stats"]
        assert (stats["members"], stats["teachers"]) == (14, 4)

        gone = [u for u in db.query(User).filter(User.full_name.in_(["S0", "T0"])).all()]
        for user in gone:
            user.deactivated_at = datetime.now(UTC)
        db.commit()
        stats = stranger_client.get("/api/v1/organizations/ucoat").json()["stats"]
        assert (stats["members"], stats["teachers"]) == (12, 3)

    def test_small_numbers_about_people_are_not_shown(
        self, stranger_client: TestClient, db: Session, school: Organization
    ):
        for i in range(4):
            _person(db, f"S{i}", "student")
        _person(db, "T", "teacher")
        stats = stranger_client.get("/api/v1/organizations/ucoat").json()["stats"]
        assert stats["members"] is None, "4 people next to a director's name is nearly a list"
        assert stats["teachers"] is None
        for i in range(6):
            _person(db, f"S{i + 4}", "student")
        _person(db, "T2", "teacher")
        _person(db, "T3", "teacher")
        stats = stranger_client.get("/api/v1/organizations/ucoat").json()["stats"]
        assert stats["members"] == 13
        assert stats["teachers"] == 3

    def test_a_closed_course_is_a_title_and_a_lock_to_a_stranger_and_a_course_to_a_member(
        self, stranger_client: TestClient, db: Session, their_teacher: User
    ):
        _course(db, their_teacher, "ucoat-institute", access_mode="institute")
        body = stranger_client.get("/api/v1/organizations/ucoat").json()
        assert body["courses"] == []
        assert [c["id"] for c in body["locked_courses"]] == ["ucoat-institute"]
        assert set(body["locked_courses"][0]) == {"id", "title", "image_url"}

        member = _person(db, "Member", "student")
        with _client_as(db, member) as c:
            body = c.get("/api/v1/organizations/ucoat").json()
        app.dependency_overrides.clear()
        assert body["viewer_is_member"] is True
        assert [x["id"] for x in body["courses"]] == ["ucoat-institute"]
        assert body["locked_courses"] == []

    def test_an_organization_not_yet_verified_is_its_own_people_s_to_see(
        self, stranger_client: TestClient, db: Session, school: Organization
    ):
        school.status = "approved"
        db.commit()
        assert stranger_client.get("/api/v1/organizations/ucoat").status_code == 404
        member = _person(db, "Member", "student")
        with _client_as(db, member) as c:
            assert c.get("/api/v1/organizations/ucoat").status_code == 200
        app.dependency_overrides.clear()


class TestTheDirectorWritesThePage:
    def test_the_director_writes_the_paragraph_and_nobody_else_can(self, db: Session, school: Organization):
        director = _person(db, "Director", "director")
        teacher = _person(db, "Teacher", "teacher")
        payload = {"description": "Библейская школа при церкви.", "website_url": "https://ucoat.example"}
        with _client_as(db, teacher) as c:
            assert c.patch(f"/api/v1/organizations/{SCHOOL_ID}/profile", json=payload).status_code == 404
        with _client_as(db, director) as c:
            r = c.patch(f"/api/v1/organizations/{SCHOOL_ID}/profile", json=payload)
        app.dependency_overrides.clear()
        assert r.status_code == 200, r.text
        assert r.json()["description"] == "Библейская школа при церкви."
        assert r.json()["website_url"] == "https://ucoat.example"

    def test_a_website_must_be_https_and_a_paragraph_short(self, db: Session, school: Organization):
        director = _person(db, "Director", "director")
        with _client_as(db, director) as c:
            # The form's rule, held by the API too: https, a host with a dot,
            # no whitespace. "https://" alone used to pass (2026-10-03).
            for broken in ("http://x", "https://", "https://ucoat", "https://uco at.example", "https://x.y z"):
                resp = c.patch(f"/api/v1/organizations/{SCHOOL_ID}/profile", json={"website_url": broken})
                assert resp.status_code == 422, (broken, resp.text)
            assert (
                c.patch(f"/api/v1/organizations/{SCHOOL_ID}/profile", json={"description": "x" * 281}).status_code
                == 422
            )
        app.dependency_overrides.clear()


class TestTheShowcase:
    def test_lists_only_verified_organizations_with_a_director_and_a_course(
        self, stranger_client: TestClient, db: Session, their_teacher: User
    ):
        listed = lambda: [c["slug"] for c in stranger_client.get("/api/v1/organizations").json()]  # noqa: E731
        assert listed() == [], "no director, no course yet"
        _person(db, "Director", "director")
        assert listed() == [], "a director but no course"
        _course(db, their_teacher, "ucoat-public", access_mode="public")
        assert listed() == ["ucoat"]
        school = db.get(Organization, SCHOOL_ID)
        assert school is not None
        school.status = "suspended"
        db.commit()
        assert listed() == []

    def test_a_deactivated_director_runs_nothing(self, stranger_client: TestClient, db: Session, their_teacher: User):
        # The page's own list of directors leaves a deactivated account
        # out; the showcase used to count it as somebody running the place.
        director = _person(db, "Director", "director")
        _course(db, their_teacher, "ucoat-public", access_mode="public")
        assert [c["slug"] for c in stranger_client.get("/api/v1/organizations").json()] == ["ucoat"]
        director.deactivated_at = datetime.now(UTC)
        db.commit()
        assert stranger_client.get("/api/v1/organizations").json() == []
