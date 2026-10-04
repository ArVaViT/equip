"""Membership decides what an organization lets you see.

Phase 2 of the memberships plan. Until 2026-10-03 every organization check
compared against one column, ``profiles.organization_id``, so a person was
in exactly one organization and the isolation tests needed only two
people. The source of truth is now ``organization_members`` — one row per
(person, organization), the role held there — and the shapes that could
not exist before are the ones worth measuring:

* a student who is in A **and** B;
* a director of A who teaches in B — and who must still get 404 on
  everything of B's that a director would see;
* a director of A **and** B, who has to say which one they are acting in.

The rule from the earlier tests holds throughout: an object of an
organization the caller has no standing in answers **404**, never 403.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_optional_user
from app.core.database import get_db
from app.main import app
from app.models.certificate import Certificate, CertificateStatus
from app.models.cohort import Cohort, CohortCourse
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.organization import MembershipSource, Organization, OrganizationMember
from app.models.user import User, UserRole
from tests._cv_helpers import make_course_with_text

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

A_ID = uuid.UUID("aaaa0000-0000-0000-0000-00000000000a")
B_ID = uuid.UUID("bbbb0000-0000-0000-0000-00000000000b")


def _member(db: Session, user: User, organization_id: uuid.UUID, role: str) -> None:
    db.add(
        OrganizationMember(
            user_id=user.id,
            organization_id=organization_id,
            role=role,
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


def _institute_course(db: Session, organization_id: uuid.UUID, owner: User, course_id: str) -> Course:
    course = make_course_with_text(
        db, course_id=course_id, title=course_id, description="", status="published", created_by=owner.id
    )
    course.organization_id = organization_id
    course.access_mode = "institute"
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


@pytest.fixture()
def world(db: Session, nobody_belongs_anywhere: None) -> dict:
    """Two organizations, a director and an institute course in each."""
    db.add_all(
        [
            Organization(id=A_ID, slug="school-a", public_name="School A"),
            Organization(id=B_ID, slug="school-b", public_name="School B"),
        ]
    )
    db.commit()
    director_a = _person(db, "director-a@example.com", UserRole.DIRECTOR.value, (A_ID, "director"))
    director_b = _person(db, "director-b@example.com", UserRole.DIRECTOR.value, (B_ID, "director"))
    return {
        "director_a": director_a,
        "director_b": director_b,
        "course_a": _institute_course(db, A_ID, director_a, "inst-a"),
        "course_b": _institute_course(db, B_ID, director_b, "inst-b"),
        "cohort_a": _cohort(db, A_ID, director_a),
        "cohort_b": _cohort(db, B_ID, director_b),
    }


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


class TestAStudentInTwoOrganizations:
    def test_reads_both_closed_courses(self, db: Session, world: dict) -> None:
        both = _person(db, "both@example.com", UserRole.STUDENT.value, (A_ID, "student"), (B_ID, "student"))
        client = _as(db, both)
        assert client.get("/api/v1/courses/inst-a").status_code == 200
        assert client.get("/api/v1/courses/inst-b").status_code == 200

    def test_a_student_of_a_only_does_not_see_b(self, db: Session, world: dict) -> None:
        only_a = _person(db, "only-a@example.com", UserRole.STUDENT.value, (A_ID, "student"))
        client = _as(db, only_a)
        assert client.get("/api/v1/courses/inst-a").status_code == 200
        assert client.get("/api/v1/courses/inst-b").status_code == 404
        assert client.get("/api/v1/cohorts/course/inst-b").status_code == 404
        assert client.get("/api/v1/courses/inst-b/author").status_code == 404

    def test_a_suspended_membership_opens_nothing(self, db: Session, world: dict) -> None:
        person = _person(db, "suspended@example.com", UserRole.STUDENT.value, (A_ID, "student"))
        db.query(OrganizationMember).filter(OrganizationMember.user_id == person.id).update({"status": "suspended"})
        db.commit()
        assert _as(db, person).get("/api/v1/courses/inst-a").status_code == 404

    def test_my_organizations_lists_one_block_per_membership(self, db: Session, world: dict) -> None:
        both = _person(db, "both@example.com", UserRole.STUDENT.value, (A_ID, "student"), (B_ID, "teacher"))
        resp = _as(db, both).get("/api/v1/courses/my-organizations")
        assert resp.status_code == 200, resp.text
        blocks = {b["organization_slug"]: b for b in resp.json()}
        assert set(blocks) == {"school-a", "school-b"}
        assert blocks["school-a"]["role"] == "student"
        assert blocks["school-b"]["role"] == "teacher"
        assert [c["id"] for c in blocks["school-a"]["courses"]] == ["inst-a"]
        assert [c["id"] for c in blocks["school-b"]["courses"]] == ["inst-b"]

    def test_a_member_may_enrol_on_a_closed_course_by_themselves(self, db: Session, world: dict) -> None:
        """The 2026-10-03 amendment to ADR-010: membership is the gate, the
        course's own window the schedule. A stranger meets a 404 — not the
        old 403 that named the course as institute."""
        member = _person(db, "member@example.com", UserRole.STUDENT.value, (A_ID, "student"))
        stranger = _person(db, "stranger@example.com", UserRole.STUDENT.value)

        assert _as(db, member).post("/api/v1/courses/inst-a/enroll", json={}).status_code in (200, 201)
        assert (
            db.query(Enrollment).filter(Enrollment.user_id == member.id, Enrollment.course_id == "inst-a").count() == 1
        )

        refused = _as(db, stranger).post("/api/v1/courses/inst-a/enroll", json={})
        assert refused.status_code == 404, refused.text
        assert "institute" not in refused.text
        assert db.query(Enrollment).filter(Enrollment.user_id == stranger.id).count() == 0


class TestADirectorOfAWhoTeachesInB:
    """The shape the one-column model could not express, and the one most
    likely to leak: the person *is* in B, as a teacher, and still must not
    reach anything a director of B would."""

    @pytest.fixture()
    def director_a_teacher_b(self, db: Session, world: dict) -> User:
        return _person(db, "a-and-b@example.com", UserRole.DIRECTOR.value, (A_ID, "director"), (B_ID, "teacher"))

    def test_bs_cohort_by_id_is_404(self, db: Session, world: dict, director_a_teacher_b: User) -> None:
        client = _as(db, director_a_teacher_b)
        assert client.get(f"/api/v1/cohorts/{world['cohort_b'].id}").status_code == 404
        assert client.patch(f"/api/v1/cohorts/{world['cohort_b'].id}", json={"max_students": 3}).status_code == 404
        assert client.get(f"/api/v1/cohorts/{world['cohort_b'].id}/students").status_code == 404
        assert (
            client.post(f"/api/v1/cohorts/{world['cohort_b'].id}/students", json={"email": "a-and-b@example.com"})
        ).status_code == 404
        # And their own cohort still answers.
        assert client.get(f"/api/v1/cohorts/{world['cohort_a'].id}").status_code == 200

    def test_the_lists_resolve_to_a_without_a_header(
        self, db: Session, world: dict, director_a_teacher_b: User
    ) -> None:
        """One directorship, so there is nothing to ask: the lists are A's."""
        client = _as(db, director_a_teacher_b)
        cohorts = client.get("/api/v1/cohorts")
        assert cohorts.status_code == 200, cohorts.text
        assert {c["id"] for c in cohorts.json()} == {str(world["cohort_a"].id)}

    def test_naming_b_as_the_acting_organization_is_refused(
        self, db: Session, world: dict, director_a_teacher_b: User
    ) -> None:
        """A member below the required role gets 403; a non-member 404."""
        client = _as(db, director_a_teacher_b)
        as_b = client.get("/api/v1/cohorts", headers={"X-Organization-Id": str(B_ID)})
        assert as_b.status_code == 403, as_b.text
        nowhere = client.get("/api/v1/cohorts", headers={"X-Organization-Id": str(uuid.uuid4())})
        assert nowhere.status_code == 404, nowhere.text
        as_a = client.get("/api/v1/cohorts", headers={"X-Organization-Id": str(A_ID)})
        assert as_a.status_code == 200, as_a.text

    def test_bs_certificate_cannot_be_issued(self, db: Session, world: dict, director_a_teacher_b: User) -> None:
        student = _person(db, "b-student@example.com", UserRole.STUDENT.value, (B_ID, "student"))
        cert = Certificate(
            id=uuid.uuid4(),
            organization_id=B_ID,
            user_id=student.id,
            course_id="inst-b",
            status=CertificateStatus.TEACHER_APPROVED,
            teacher_approved_at=datetime.now(UTC),
            teacher_approved_by=world["director_b"].id,
        )
        db.add(cert)
        db.commit()
        client = _as(db, director_a_teacher_b)
        queue = client.get("/api/v1/certificates/admin/pending")
        assert queue.status_code == 200, queue.text
        assert str(cert.id) not in queue.text
        assert client.put(f"/api/v1/certificates/{cert.id}/admin-approve").status_code == 404
        db.refresh(cert)
        assert cert.certificate_number is None

    def test_bs_course_is_not_theirs_to_direct(self, db: Session, world: dict, director_a_teacher_b: User) -> None:
        client = _as(db, director_a_teacher_b)
        # The ведомость and the grading scheme are a director's, of their own school.
        assert client.get("/api/v1/grades/course/inst-b/sheet").status_code in (403, 404)
        assert client.get("/api/v1/grades/course/inst-b/sheet").status_code != 200
        # Closing or opening a course is its organization's director's.
        assert client.put("/api/v1/courses/inst-b", json={"access_mode": "public"}).status_code in (403, 404)
        db.refresh(world["course_b"])
        assert world["course_b"].access_mode == "institute"
        # Inviting into B at large is a director's act, and they direct only A.
        refused = client.post(
            "/api/v1/invitations",
            json={"email": "x@example.com", "role": "student", "scope": "organization", "age_attested": True},
            headers={"X-Organization-Id": str(B_ID)},
        )
        assert refused.status_code == 403, refused.text

    def test_a_student_of_b_does_not_take_a_copy(self, db: Session, world: dict) -> None:
        """Copying is a staff act: a teacher of A who merely *studies* in B
        reads B's closed course and gets a 404 on cloning it, as a teacher
        with no standing in B does at all."""
        teacher_a_student_b = _person(
            db, "a-teacher-b-student@example.com", UserRole.TEACHER.value, (A_ID, "teacher"), (B_ID, "student")
        )
        client = _as(db, teacher_a_student_b)
        assert client.get("/api/v1/courses/inst-b").status_code == 200
        assert client.post("/api/v1/courses/inst-b/clone").status_code == 404
        outsider = _person(db, "a-only-teacher@example.com", UserRole.TEACHER.value, (A_ID, "teacher"))
        assert _as(db, outsider).post("/api/v1/courses/inst-b/clone").status_code == 404

    def test_but_teaches_in_b(self, db: Session, world: dict, director_a_teacher_b: User) -> None:
        """What the teacher membership in B does open: B's closed course, and a copy of it."""
        client = _as(db, director_a_teacher_b)
        assert client.get("/api/v1/courses/inst-b").status_code == 200
        copy = client.post("/api/v1/courses/inst-b/clone", headers={"X-Organization-Id": str(B_ID)})
        assert copy.status_code == 201, copy.text
        assert db.query(Course).filter(Course.id == copy.json()["id"]).one().organization_id == B_ID


class TestADirectorOfBoth:
    @pytest.fixture()
    def director_of_both(self, db: Session, world: dict) -> User:
        return _person(db, "both-dir@example.com", UserRole.DIRECTOR.value, (A_ID, "director"), (B_ID, "director"))

    def test_a_list_without_a_header_asks_which(self, db: Session, world: dict, director_of_both: User) -> None:
        resp = _as(db, director_of_both).get("/api/v1/cohorts")
        assert resp.status_code == 400, resp.text
        body = resp.json()["detail"]
        assert body["code"] == "organization.ambiguous"
        offered = {o["slug"]: o["role"] for o in body["context"]["organizations"]}
        assert offered == {"school-a": "director", "school-b": "director"}

    def test_the_header_picks_the_organization(self, db: Session, world: dict, director_of_both: User) -> None:
        client = _as(db, director_of_both)
        a = client.get("/api/v1/cohorts", headers={"X-Organization-Id": str(A_ID)})
        b = client.get("/api/v1/cohorts", headers={"X-Organization-Id": str(B_ID)})
        assert {c["id"] for c in a.json()} == {str(world["cohort_a"].id)}
        assert {c["id"] for c in b.json()} == {str(world["cohort_b"].id)}

    def test_an_object_needs_no_header(self, db: Session, world: dict, director_of_both: User) -> None:
        """The cohort names its organization; the caller directs it; done."""
        client = _as(db, director_of_both)
        assert client.get(f"/api/v1/cohorts/{world['cohort_a'].id}").status_code == 200
        assert client.get(f"/api/v1/cohorts/{world['cohort_b'].id}").status_code == 200

    def test_a_cohort_is_created_where_the_header_says(self, db: Session, world: dict, director_of_both: User) -> None:
        client = _as(db, director_of_both)
        body = {"name": "Autumn", "start_date": "2026-09-01", "end_date": "2026-12-01"}
        created = client.post("/api/v1/cohorts", json=body, headers={"X-Organization-Id": str(B_ID)})
        assert created.status_code == 201, created.text
        assert db.query(Cohort).filter(Cohort.id == uuid.UUID(created.json()["id"])).one().organization_id == B_ID
        assert client.post("/api/v1/cohorts", json=body).status_code == 400

    def test_the_access_mode_of_either_course_is_theirs(self, db: Session, world: dict, director_of_both: User) -> None:
        """Until 2026-10-03 only platform staff could close or open a course;
        a director could not close a course of their own school."""
        client = _as(db, director_of_both)
        # Only the author edits a course; make them its author first.
        world["course_b"].created_by = director_of_both.id
        db.commit()
        resp = client.put("/api/v1/courses/inst-b", json={"access_mode": "public"})
        assert resp.status_code == 200, resp.text
        db.refresh(world["course_b"])
        assert world["course_b"].access_mode == "public"


class TestPlacingAStudentInACohort:
    def test_a_closed_course_makes_the_student_a_member(self, db: Session, world: dict) -> None:
        """A director who puts somebody in a cohort of a closed course has
        decided they belong; without the row the student would hold a seat
        on a course that answers them 404."""
        db.add(CohortCourse(cohort_id=world["cohort_a"].id, course_id="inst-a"))
        db.commit()
        newcomer = _person(db, "newcomer@example.com", UserRole.STUDENT.value)
        client = _as(db, world["director_a"])

        resp = client.post(f"/api/v1/cohorts/{world['cohort_a'].id}/students", json={"email": "newcomer@example.com"})

        assert resp.status_code == 201, resp.text
        membership = db.query(OrganizationMember).filter(OrganizationMember.user_id == newcomer.id).one()
        assert (membership.organization_id, membership.role) == (A_ID, "student")
        assert (membership.joined_via, membership.invited_by) == ("appointment", world["director_a"].id)
        assert _as(db, newcomer).get("/api/v1/courses/inst-a").status_code == 200

    def test_a_public_course_does_not(self, db: Session, world: dict) -> None:
        public = make_course_with_text(
            db, course_id="pub-a", title="Public", description="", status="published", created_by=world["director_a"].id
        )
        public.organization_id = A_ID
        db.add(CohortCourse(cohort_id=world["cohort_a"].id, course_id=public.id))
        db.commit()
        newcomer = _person(db, "newcomer@example.com", UserRole.STUDENT.value)

        resp = _as(db, world["director_a"]).post(
            f"/api/v1/cohorts/{world['cohort_a'].id}/students", json={"email": "newcomer@example.com"}
        )

        assert resp.status_code == 201, resp.text
        assert db.query(OrganizationMember).filter(OrganizationMember.user_id == newcomer.id).count() == 0

    def test_attaching_a_closed_course_places_the_students_already_there(self, db: Session, world: dict) -> None:
        seated = _person(db, "seated@example.com", UserRole.STUDENT.value)
        db.add(Enrollment(id=str(uuid.uuid4()), user_id=seated.id, course_id="inst-a", cohort_id=world["cohort_a"].id))
        db.commit()
        # A second closed course of A attached to the cohort.
        _institute_course(db, A_ID, world["director_a"], "inst-a-2")

        resp = _as(db, world["director_a"]).post(
            f"/api/v1/cohorts/{world['cohort_a'].id}/courses", json={"course_id": "inst-a-2"}
        )

        assert resp.status_code == 201, resp.text
        membership = db.query(OrganizationMember).filter(OrganizationMember.user_id == seated.id).one()
        assert (membership.organization_id, membership.role) == (A_ID, "student")

    def test_a_teacher_already_there_is_not_lowered(self, db: Session, world: dict) -> None:
        db.add(CohortCourse(cohort_id=world["cohort_a"].id, course_id="inst-a"))
        db.commit()
        teacher = _person(db, "teacher-a@example.com", UserRole.TEACHER.value, (A_ID, "teacher"))

        resp = _as(db, world["director_a"]).post(
            f"/api/v1/cohorts/{world['cohort_a'].id}/students", json={"email": "teacher-a@example.com"}
        )

        assert resp.status_code == 201, resp.text
        membership = db.query(OrganizationMember).filter(OrganizationMember.user_id == teacher.id).one()
        assert membership.role == "teacher"
        db.refresh(teacher)
        assert teacher.role == UserRole.TEACHER.value


class TestTheMirror:
    def test_profiles_role_follows_the_highest_membership(self, db: Session, world: dict) -> None:
        from app.services.memberships import grant_membership

        person = _person(db, "mirror@example.com", UserRole.STUDENT.value)
        grant_membership(db, user=person, organization_id=A_ID, role="teacher", joined_via="appointment")
        db.commit()
        assert person.role == UserRole.TEACHER.value
        grant_membership(db, user=person, organization_id=B_ID, role="director", joined_via="appointment")
        db.commit()
        assert person.role == UserRole.DIRECTOR.value
        # Granting a lower role somewhere else changes nothing.
        grant_membership(db, user=person, organization_id=A_ID, role="student", joined_via="appointment")
        db.commit()
        assert person.role == UserRole.DIRECTOR.value
        assert {
            m.organization_id: m.role
            for m in db.query(OrganizationMember).filter(OrganizationMember.user_id == person.id)
        } == {A_ID: "teacher", B_ID: "director"}

    def test_platform_staff_are_never_touched(self, db: Session, world: dict) -> None:
        from app.services.memberships import grant_membership

        staff = _person(db, "staff@equipbible.com", UserRole.ADMIN.value)
        grant_membership(db, user=staff, organization_id=A_ID, role="student", joined_via="appointment")
        db.commit()
        assert staff.role == UserRole.ADMIN.value

    def test_the_first_membership_fills_the_deprecated_column_and_the_second_does_not(
        self, db: Session, world: dict
    ) -> None:
        from app.services.memberships import grant_membership

        person = _person(db, "column@example.com", UserRole.STUDENT.value)
        assert person.organization_id is None
        grant_membership(db, user=person, organization_id=B_ID, role="student", joined_via="appointment")
        grant_membership(db, user=person, organization_id=A_ID, role="student", joined_via="appointment")
        db.commit()
        assert person.organization_id == B_ID


class TestPlatformStaff:
    def test_see_every_organization_and_may_name_one(self, db: Session, world: dict) -> None:
        staff = _person(db, "staff@equipbible.com", UserRole.ADMIN.value)
        client = _as(db, staff)
        everything = client.get("/api/v1/cohorts")
        assert everything.status_code == 200, everything.text
        assert {c["id"] for c in everything.json()} == {str(world["cohort_a"].id), str(world["cohort_b"].id)}
        only_b = client.get("/api/v1/cohorts", headers={"X-Organization-Id": str(B_ID)})
        assert {c["id"] for c in only_b.json()} == {str(world["cohort_b"].id)}
        assert client.get("/api/v1/cohorts", headers={"X-Organization-Id": str(uuid.uuid4())}).status_code == 404

    def test_creating_needs_a_place(self, db: Session, world: dict) -> None:
        """Staff who sit nowhere must say where; staff who sit in one place act there."""
        homeless = _person(db, "nowhere@equipbible.com", UserRole.ADMIN.value)
        body = {"name": "Spring", "start_date": "2026-01-01", "end_date": "2026-06-01"}
        assert _as(db, homeless).post("/api/v1/cohorts", json=body).status_code == 403
        seated = _person(db, "seated@equipbible.com", UserRole.ADMIN.value, (A_ID, "teacher"))
        created = _as(db, seated).post("/api/v1/cohorts", json=body)
        assert created.status_code == 201, created.text
        assert db.query(Cohort).filter(Cohort.id == uuid.UUID(created.json()["id"])).one().organization_id == A_ID
