"""A role held in one organization opens nothing in another, and nothing on the platform.

Phase 1 of the memberships plan made ``profiles.role`` a mirror of the
highest membership a person holds *anywhere*. The security review of
2026-10-03 then walked every surface that still read that column, or
``profiles.organization_id``, as if it named one place — and found each of
them answering for the wrong organization. These are the reviewer's probes
turned the right way up: each asserted a leak then, each asserts it closed
now, and each fails with its fix removed.

The SQL side — the three RLS policies and ``fulfil_pending_invitations`` —
is proved in ``supabase/ci/rls_assertions.sql`` and
``supabase/ci/invitation_fulfilment_assertions.sql``, which run on Postgres;
the test database here is SQLite and cannot see a policy.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.api.dependencies import get_current_user, get_optional_user
from app.core.database import get_db
from app.main import app
from app.models.cohort import Cohort
from app.models.course import Chapter, Course, Module
from app.models.enrollment import Enrollment
from app.models.invitation import Invitation
from app.models.organization import MembershipSource, MembershipStatus, Organization, OrganizationMember
from app.models.user import User, UserRole
from app.services.memberships import directs, grant_student_memberships
from app.services.students_at_risk import students_at_risk
from tests._cv_helpers import make_course_with_text

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

A_ID = uuid.UUID("aaaa0000-0000-0000-0000-00000000000a")
B_ID = uuid.UUID("bbbb0000-0000-0000-0000-00000000000b")
ROLE_ROUTE = "/api/v1/users/admin/users/{}/role"


def _member(db: Session, user: User, organization_id: uuid.UUID, role: str, status: str = "active") -> None:
    db.add(
        OrganizationMember(
            user_id=user.id,
            organization_id=organization_id,
            role=role,
            status=status,
            joined_via=MembershipSource.MIGRATION.value,
        )
    )
    db.commit()


def _person(db: Session, email: str, role: str, *memberships: tuple[uuid.UUID, str]) -> User:
    """A user with exactly these memberships (``nobody_belongs_anywhere`` is on)."""
    user = User(id=uuid.uuid4(), email=email, full_name=email.split("@")[0], role=role)
    db.add(user)
    db.commit()
    for organization_id, membership_role in memberships:
        _member(db, user, organization_id, membership_role)
    db.refresh(user)
    return user


def _membership(db: Session, user: User, organization_id: uuid.UUID) -> OrganizationMember | None:
    return (
        db.query(OrganizationMember)
        .filter(OrganizationMember.user_id == user.id, OrganizationMember.organization_id == organization_id)
        .first()
    )


def _course(db: Session, organization_id: uuid.UUID, owner: User, course_id: str, access_mode: str) -> Course:
    course = make_course_with_text(
        db, course_id=course_id, title=course_id, description="", status="published", created_by=owner.id
    )
    course.organization_id = organization_id
    course.access_mode = access_mode
    db.commit()
    return course


def _cohort(db: Session, organization_id: uuid.UUID, owner: User) -> Cohort:
    cohort = Cohort(
        id=uuid.uuid4(),
        organization_id=organization_id,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 1),
        created_by=owner.id,
    )
    db.add(cohort)
    db.commit()
    return cohort


def _pending_invitation(db: Session, *, email: str, organization_id: uuid.UUID, invited_by: User, role: str) -> str:
    token = uuid.uuid4().hex
    db.add(
        Invitation(
            id=uuid.uuid4(),
            email=email,
            role=role,
            scope="organization",
            organization_id=organization_id,
            token=token,
            invited_by=invited_by.id,
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
    )
    db.commit()
    return token


@pytest.fixture()
def world(db: Session, nobody_belongs_anywhere: None) -> dict:
    """Two organizations, a director in each, a closed course with a lesson in A, platform staff."""
    db.add_all(
        [
            Organization(id=A_ID, slug="school-a", public_name="School A"),
            Organization(id=B_ID, slug="school-b", public_name="School B"),
        ]
    )
    db.commit()
    director_a = _person(db, "director-a@example.com", UserRole.DIRECTOR.value, (A_ID, "director"))
    director_b = _person(db, "director-b@example.com", UserRole.DIRECTOR.value, (B_ID, "director"))
    admin = _person(db, "staff@equipbible.com", UserRole.ADMIN.value)
    course_a = _course(db, A_ID, director_a, "inst-a", "institute")
    db.add(Module(id="mod-a", course_id="inst-a", order_index=0))
    db.add(Chapter(id="ch-a", course_id="inst-a", module_id="mod-a", order_index=0, title="Secret lesson"))
    db.commit()
    return {"director_a": director_a, "director_b": director_b, "admin": admin, "course_a": course_a}


def _as(db: Session, user: User | None) -> TestClient:
    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_optional_user] = lambda: user
    if user is not None:
        app.dependency_overrides[get_current_user] = lambda: user
    else:
        app.dependency_overrides.pop(get_current_user, None)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


class TestAModuleOfAClosedCourse:
    """The module route kept its own copy of the visibility rule — status
    and owner, nothing about ``access_mode`` — so a closed course's module
    and its lesson titles read 200 by id while the course read 404."""

    def test_is_as_hidden_as_the_course(self, db: Session, world: dict) -> None:
        stranger = _person(db, "nobody@example.com", UserRole.STUDENT.value)
        assert _as(db, stranger).get("/api/v1/courses/inst-a").status_code == 404
        assert _as(db, stranger).get("/api/v1/courses/inst-a/modules/mod-a").status_code == 404
        assert _as(db, None).get("/api/v1/courses/inst-a/modules/mod-a").status_code == 404

    def test_and_as_visible(self, db: Session, world: dict) -> None:
        member = _person(db, "member@example.com", UserRole.STUDENT.value, (A_ID, "student"))
        resp = _as(db, member).get("/api/v1/courses/inst-a/modules/mod-a")
        assert resp.status_code == 200, resp.text
        assert [c["title"] for c in resp.json()["chapters"]] == ["Secret lesson"]
        assert _as(db, world["director_a"]).get("/api/v1/courses/inst-a/modules/mod-a").status_code == 200

    def test_a_suspended_member_is_a_stranger(self, db: Session, world: dict) -> None:
        suspended = _person(db, "suspended@example.com", UserRole.STUDENT.value)
        _member(db, suspended, A_ID, "student", status="suspended")
        assert _as(db, suspended).get("/api/v1/courses/inst-a/modules/mod-a").status_code == 404


class TestTheAdminRoleRoute:
    """``profiles.role`` below ``admin`` is the mirror's. The route used to
    write any value, and the next membership write anywhere put the old one
    back: a director demoted to student became a director again by accepting
    a student invitation to another school."""

    def test_a_director_cannot_be_demoted_here(self, db: Session, world: dict) -> None:
        director_a = world["director_a"]
        resp = _as(db, world["admin"]).put(ROLE_ROUTE.format(director_a.id), params={"role": "student"})
        assert resp.status_code == 422, resp.text
        body = resp.json()["detail"]
        assert body["code"] == "user.role_held_by_membership"
        assert body["context"]["role"] == "director"
        assert body["context"]["memberships"] == [{"organization_id": str(A_ID), "role": "director"}]
        db.refresh(director_a)
        assert director_a.role == UserRole.DIRECTOR.value
        assert directs(db, director_a, A_ID)

    def test_nor_a_student_promoted(self, db: Session, world: dict) -> None:
        student = _person(db, "s@example.com", UserRole.STUDENT.value, (A_ID, "student"))
        resp = _as(db, world["admin"]).put(ROLE_ROUTE.format(student.id), params={"role": "teacher"})
        assert resp.status_code == 422
        db.refresh(student)
        assert student.role == UserRole.STUDENT.value

    def test_asking_for_what_the_memberships_say_is_a_no_op(self, db: Session, world: dict) -> None:
        teacher = _person(db, "t@example.com", UserRole.TEACHER.value, (A_ID, "teacher"))
        resp = _as(db, world["admin"]).put(ROLE_ROUTE.format(teacher.id), params={"role": "teacher"})
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] == "teacher"

    def test_in_and_out_of_platform_staff(self, db: Session, world: dict) -> None:
        teacher = _person(db, "t@example.com", UserRole.TEACHER.value, (A_ID, "teacher"))
        client = _as(db, world["admin"])

        up = client.put(ROLE_ROUTE.format(teacher.id), params={"role": "admin"})
        assert (up.status_code, up.json()["role"]) == (200, "admin")

        # Any non-admin value means "stop being platform staff"; what is left
        # is what the memberships say — this one teaches in A.
        down = client.put(ROLE_ROUTE.format(teacher.id), params={"role": "student"})
        assert (down.status_code, down.json()["role"]) == (200, "teacher"), down.text

        # And the next membership write anywhere keeps it there — nothing
        # makes them admin again.
        token = _pending_invitation(
            db, email=teacher.email, organization_id=B_ID, invited_by=world["director_b"], role="student"
        )
        db.refresh(teacher)
        assert _as(db, teacher).post("/api/v1/invitations/accept", json={"token": token}).status_code == 200
        db.refresh(teacher)
        assert teacher.role == UserRole.TEACHER.value

    def test_a_stale_mirror_is_repaired_by_the_ask(self, db: Session, world: dict) -> None:
        # The shape the old platform invitation left: a global teacher with no membership.
        ghost = _person(db, "ghost@example.com", UserRole.TEACHER.value)
        resp = _as(db, world["admin"]).put(ROLE_ROUTE.format(ghost.id), params={"role": "student"})
        assert (resp.status_code, resp.json()["role"]) == (200, "student"), resp.text

    def test_the_bulk_route_holds_the_same_line(self, db: Session, world: dict) -> None:
        director_a = world["director_a"]
        student = _person(db, "s@example.com", UserRole.STUDENT.value, (A_ID, "student"))
        client = _as(db, world["admin"])

        resp = client.put(
            "/api/v1/users/admin/users/bulk-role",
            json={"user_ids": [str(director_a.id), str(student.id)], "role": "teacher"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["updated"] == 0
        assert set(resp.json()["held_by_membership"]) == {str(director_a.id), str(student.id)}
        db.refresh(director_a)
        assert director_a.role == UserRole.DIRECTOR.value

        resp = client.put(
            "/api/v1/users/admin/users/bulk-role",
            json={"user_ids": [str(director_a.id), str(student.id)], "role": "admin"},
        )
        assert resp.json() == {"updated": 2, "role": "admin", "held_by_membership": []}


class TestAPlatformInvitation:
    """An account and nothing else, and only the platform offers one. It used
    to write the offered role onto the profile with no membership behind it
    — a teacher of nowhere, which any director could mint and which the
    mirror undid on the next membership write."""

    def test_a_director_cannot_write_one(self, db: Session, world: dict) -> None:
        resp = _as(db, world["director_a"]).post(
            "/api/v1/invitations",
            json={"email": "new@example.com", "role": "student", "scope": "platform", "age_attested": True},
        )
        assert resp.status_code == 403, resp.text
        assert db.query(Invitation).count() == 0

    def test_it_carries_no_role(self, db: Session, world: dict) -> None:
        resp = _as(db, world["admin"]).post(
            "/api/v1/invitations",
            json={"email": "new@example.com", "role": "teacher", "scope": "platform", "age_attested": True},
            headers={"X-Organization-Id": str(A_ID)},
        )
        assert resp.status_code == 422, resp.text
        assert db.query(Invitation).count() == 0

    def test_accepting_one_grants_an_account_and_nothing_else(self, db: Session, world: dict) -> None:
        newcomer = _person(db, "new@example.com", UserRole.STUDENT.value)
        resp = _as(db, world["admin"]).post(
            "/api/v1/invitations",
            json={"email": "new@example.com", "role": "student", "scope": "platform", "age_attested": True},
            headers={"X-Organization-Id": str(A_ID)},
        )
        assert resp.status_code == 201, resp.text
        token = db.query(Invitation).filter(Invitation.email == "new@example.com").one().token
        assert _as(db, newcomer).post("/api/v1/invitations/accept", json={"token": token}).status_code == 200
        db.refresh(newcomer)
        assert newcomer.role == UserRole.STUDENT.value
        assert db.query(OrganizationMember).filter(OrganizationMember.user_id == newcomer.id).count() == 0

    def test_a_pending_teacher_row_from_before_grants_no_role_either(self, db: Session, world: dict) -> None:
        newcomer = _person(db, "new@example.com", UserRole.STUDENT.value)
        token = uuid.uuid4().hex
        db.add(
            Invitation(
                id=uuid.uuid4(),
                email=newcomer.email,
                role="teacher",
                scope="platform",
                organization_id=A_ID,
                token=token,
                invited_by=world["director_a"].id,
                status="pending",
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
        )
        db.commit()
        assert _as(db, newcomer).post("/api/v1/invitations/accept", json={"token": token}).status_code == 200
        db.refresh(newcomer)
        assert newcomer.role == UserRole.STUDENT.value
        assert _as(db, newcomer).get("/api/v1/courses/my").status_code == 403


class TestASuspendedTeacher:
    def test_keeps_the_course_but_not_the_door(self, db: Session, world: dict) -> None:
        """Owning a course let a teacher invite students into the organization
        after it had suspended them."""
        teacher = _person(db, "t@example.com", UserRole.TEACHER.value, (A_ID, "teacher"), (B_ID, "teacher"))
        _course(db, A_ID, teacher, "pub-a", "public")
        invite = {"role": "student", "scope": "course", "course_id": "pub-a", "age_attested": True}

        before = _as(db, teacher).post("/api/v1/invitations", json={"email": "first@example.com", **invite})
        assert before.status_code == 201, before.text

        db.query(OrganizationMember).filter(
            OrganizationMember.user_id == teacher.id, OrganizationMember.organization_id == A_ID
        ).update({"status": MembershipStatus.SUSPENDED.value})
        db.commit()

        after = _as(db, teacher).post("/api/v1/invitations", json={"email": "second@example.com", **invite})
        assert after.status_code == 403, after.text
        assert db.query(Invitation).filter(Invitation.email == "second@example.com").count() == 0


class TestPlacingACohort:
    """Attaching a closed course places every seated student in the
    organization — in two statements, not three per student, and without
    touching anybody who already has a row."""

    def test_who_joins_and_who_is_left_alone(self, db: Session, world: dict) -> None:
        director_a = world["director_a"]
        cohort = _cohort(db, A_ID, director_a)
        newcomer = _person(db, "newcomer@example.com", UserRole.STUDENT.value)
        teacher = _person(db, "teacher-a@example.com", UserRole.TEACHER.value, (A_ID, "teacher"))
        suspended = _person(db, "suspended@example.com", UserRole.STUDENT.value)
        _member(db, suspended, A_ID, "student", status="suspended")
        elsewhere = _person(db, "elsewhere@example.com", UserRole.TEACHER.value, (B_ID, "teacher"))
        for person in (newcomer, teacher, suspended, elsewhere):
            db.add(Enrollment(id=str(uuid.uuid4()), user_id=person.id, course_id="inst-a", cohort_id=cohort.id))
        db.commit()
        _course(db, A_ID, director_a, "inst-a-2", "institute")

        resp = _as(db, director_a).post(f"/api/v1/cohorts/{cohort.id}/courses", json={"course_id": "inst-a-2"})

        assert resp.status_code == 201, resp.text
        joined = _membership(db, newcomer, A_ID)
        assert joined is not None
        assert (joined.role, joined.status, joined.joined_via, joined.invited_by) == (
            "student",
            "active",
            "appointment",
            director_a.id,
        )
        assert _membership(db, elsewhere, A_ID) is not None
        teacher_row = _membership(db, teacher, A_ID)
        assert teacher_row is not None and teacher_row.role == "teacher"
        suspended_row = _membership(db, suspended, A_ID)
        assert suspended_row is not None and suspended_row.status == "suspended"
        for person, role in (
            (newcomer, "student"),
            (teacher, "teacher"),
            (suspended, "student"),
            (elsewhere, "teacher"),
        ):
            db.refresh(person)
            assert person.role == role, person.email

    def test_a_cohort_of_many_costs_what_a_cohort_of_one_costs(self, db: Session, world: dict) -> None:
        # Ids taken before counting starts: a commit expires every loaded
        # row, and reading ``.id`` afterwards is a SELECT per person that
        # belongs to the test, not to the placement.
        few = {_person(db, f"few-{i}@example.com", UserRole.STUDENT.value).id for i in range(1)}
        many = {_person(db, f"many-{i}@example.com", UserRole.STUDENT.value).id for i in range(6)}
        placed_by = world["director_a"].id
        statements: list[str] = []

        def _count(_conn, _cursor, statement, _params, _context, _executemany):
            statements.append(statement)

        engine = db.get_bind()
        event.listen(engine, "before_cursor_execute", _count)
        try:
            grant_student_memberships(db, user_ids=few, organization_id=A_ID, placed_by=placed_by)
            db.commit()
            for_few = len(statements)
            statements.clear()
            grant_student_memberships(db, user_ids=many, organization_id=A_ID, placed_by=placed_by)
            db.commit()
            for_many = len(statements)
        finally:
            event.remove(engine, "before_cursor_execute", _count)

        assert for_many == for_few, f"{for_few} statements for one student, {for_many} for six"
        assert db.query(OrganizationMember).filter(OrganizationMember.organization_id == A_ID).count() == 1 + 1 + 6


class TestASuspendedMembershipAndAnInvitation:
    """A link reopens a suspended membership only if whoever wrote it still
    speaks for the organization."""

    def test_an_invitation_from_the_organization_s_director_reopens_it(self, db: Session, world: dict) -> None:
        person = _person(db, "p@example.com", UserRole.STUDENT.value)
        _member(db, person, A_ID, "student", status="suspended")
        token = _pending_invitation(
            db, email=person.email, organization_id=A_ID, invited_by=world["director_a"], role="student"
        )
        assert _as(db, person).post("/api/v1/invitations/accept", json={"token": token}).status_code == 200
        row = _membership(db, person, A_ID)
        assert row is not None and row.status == "active"

    def test_an_invitation_from_somebody_since_let_go_does_not(self, db: Session, world: dict) -> None:
        former = _person(db, "former@example.com", UserRole.TEACHER.value, (A_ID, "teacher"))
        person = _person(db, "p@example.com", UserRole.STUDENT.value)
        _member(db, person, A_ID, "student", status="suspended")
        token = _pending_invitation(db, email=person.email, organization_id=A_ID, invited_by=former, role="student")
        db.query(OrganizationMember).filter(
            OrganizationMember.user_id == former.id, OrganizationMember.organization_id == A_ID
        ).update({"status": MembershipStatus.SUSPENDED.value})
        db.commit()

        resp = _as(db, person).post("/api/v1/invitations/accept", json={"token": token})

        # Refused outright, and told why — not a 200 that quietly changed
        # nothing (which is what this answered until 2026-10-03, while the
        # same link still admitted anyone who was not yet a member).
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"]["code"] == "invitation.inviter_not_staff"
        row = _membership(db, person, A_ID)
        assert row is not None and row.status == "suspended"
        db.refresh(person)
        assert person.role == UserRole.STUDENT.value
        assert db.query(Invitation).filter(Invitation.token == token).one().status == "pending"


class TestWhoIsAStudentHere:
    def test_a_student_who_teaches_elsewhere_is_still_on_the_list(self, db: Session, world: dict) -> None:
        """The at-risk roster read ``User.role == 'student'``; with the role a
        mirror of the highest membership anywhere, a quiet student of this
        course who teaches in another school was the one person not called."""
        director_a = world["director_a"]
        course = _course(db, A_ID, director_a, "pub-a", "public")
        now = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
        quiet = _person(db, "quiet@example.com", UserRole.TEACHER.value, (A_ID, "student"), (B_ID, "teacher"))
        colleague = _person(db, "colleague@example.com", UserRole.TEACHER.value, (A_ID, "teacher"))
        assert quiet.role == UserRole.TEACHER.value, "the mirror made this student read teacher"
        for person in (quiet, colleague, director_a, world["admin"]):
            db.add(
                Enrollment(
                    id=str(uuid.uuid4()),
                    user_id=person.id,
                    course_id=course.id,
                    progress=10,
                    enrolled_at=now - timedelta(days=30),
                )
            )
        db.commit()

        rows = students_at_risk(db, director_a.id, now=now)

        assert [r.email for r in rows] == ["quiet@example.com"]
