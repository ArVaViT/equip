"""Step 3, second half: cohorts, grade sheets, invitations, certificates.

The first half measured the course surface and found exactly two holes
out of 108 routes — the catalogue and the course detail — which is why
the fix was two filters rather than a hundred edited handlers. This is
the same probe pointed at the other four surfaces a director owns.

The shape of the probe: two organizations, a director in each, an object
created inside the second one, and the first director asking for it by
id. The answer must be 404 rather than 403 — 403 confirms the object
exists, which is the question the request was asking.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.api.consent_gate import consent_subject
from app.api.dependencies import get_current_user, get_optional_user
from app.core.database import get_db
from app.main import app
from app.models.certificate import Certificate, CertificateStatus
from app.models.cohort import Cohort
from app.models.enrollment import Enrollment
from app.models.invitation import Invitation
from app.models.organization import Organization
from app.models.user import User, UserRole
from tests._cv_helpers import make_course_with_text
from tests.conftest import TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

THEIR_ORGANIZATION_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


@pytest.fixture()
def their_organization(db: Session) -> Organization:
    organization = Organization(
        id=THEIR_ORGANIZATION_ID,
        slug="their-organization",
        public_name="Their Organization",
    )
    db.add(organization)
    db.commit()
    return organization


@pytest.fixture()
def their_director(db: Session, their_organization: Organization) -> User:
    user = User(
        id=uuid.uuid4(),
        email="their-director@example.com",
        full_name="Their Director",
        role=UserRole.DIRECTOR.value,
        organization_id=THEIR_ORGANIZATION_ID,
    )
    db.add(user)
    db.commit()
    return user


@pytest.fixture()
def our_director_client(db: Session):
    """Signed in as a director of the *test* organization."""
    user = User(
        id=uuid.uuid4(),
        email="our-director@example.com",
        full_name="Our Director",
        role=UserRole.DIRECTOR.value,
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


def _their_cohort(db: Session, owner: User) -> Cohort:
    cohort = Cohort(
        id=uuid.uuid4(),
        organization_id=THEIR_ORGANIZATION_ID,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 6, 1),
        created_by=owner.id,
    )
    db.add(cohort)
    db.commit()
    return cohort


def _their_course(db: Session, owner: User, course_id: str):
    course = make_course_with_text(
        db,
        course_id=course_id,
        title="Their Course",
        description="Not yours",
        status="published",
        created_by=owner.id,
    )
    course.organization_id = THEIR_ORGANIZATION_ID
    course.access_mode = "institute"
    db.commit()
    return course


class TestCohorts:
    def test_reading_their_cohort_by_id(self, our_director_client: TestClient, db: Session, their_director: User):
        cohort = _their_cohort(db, their_director)
        resp = our_director_client.get(f"/api/v1/cohorts/{cohort.id}")
        assert resp.status_code == 404, resp.text

    def test_their_cohort_is_not_in_the_list(self, our_director_client: TestClient, db: Session, their_director: User):
        cohort = _their_cohort(db, their_director)
        resp = our_director_client.get("/api/v1/cohorts")
        assert resp.status_code == 200, resp.text
        assert str(cohort.id) not in resp.text

    def test_editing_their_cohort(self, our_director_client: TestClient, db: Session, their_director: User):
        cohort = _their_cohort(db, their_director)
        resp = our_director_client.patch(
            f"/api/v1/cohorts/{cohort.id}",
            json={"max_students": 5},
        )
        assert resp.status_code == 404, resp.text

    def test_deleting_their_cohort(self, our_director_client: TestClient, db: Session, their_director: User):
        cohort = _their_cohort(db, their_director)
        resp = our_director_client.delete(f"/api/v1/cohorts/{cohort.id}")
        assert resp.status_code == 404, resp.text

    def test_completing_their_cohort(self, our_director_client: TestClient, db: Session, their_director: User):
        cohort = _their_cohort(db, their_director)
        resp = our_director_client.post(f"/api/v1/cohorts/{cohort.id}/complete")
        assert resp.status_code == 404, resp.text

    def test_reading_their_cohort_roster(self, our_director_client: TestClient, db: Session, their_director: User):
        cohort = _their_cohort(db, their_director)
        resp = our_director_client.get(f"/api/v1/cohorts/{cohort.id}/students")
        assert resp.status_code == 404, resp.text


class TestGradeSheets:
    """Grade routes are gated by ``require_teacher`` and by course
    ownership, not by the director role — so a director gets 403 on
    every one of them, their own organization's included, and the
    isolation here rides on the course check that step 3a already
    closed. These cases pin that: whatever the code, the answer is never
    200 and never leaks a row."""

    def test_reading_their_sheet(self, our_director_client: TestClient, db: Session, their_director: User):
        course = _their_course(db, their_director, "their-course-sheet")
        resp = our_director_client.get(f"/api/v1/grades/course/{course.id}/sheet")
        assert resp.status_code in (403, 404), resp.text

    def test_closing_a_sheet_on_their_course(self, our_director_client: TestClient, db: Session, their_director: User):
        course = _their_course(db, their_director, "their-course-close")
        resp = our_director_client.post(f"/api/v1/grades/course/{course.id}/sheet")
        assert resp.status_code in (403, 404), resp.text

    def test_reading_their_grade_summary(self, our_director_client: TestClient, db: Session, their_director: User):
        course = _their_course(db, their_director, "their-course-summary")
        resp = our_director_client.get(f"/api/v1/grades/course/{course.id}/summary")
        assert resp.status_code in (403, 404), resp.text

    def test_exporting_their_grades(self, our_director_client: TestClient, db: Session, their_director: User):
        course = _their_course(db, their_director, "their-course-csv")
        resp = our_director_client.get(f"/api/v1/grades/course/{course.id}/export-csv")
        assert resp.status_code in (403, 404), resp.text


class TestCertificates:
    def _their_certificate(self, db: Session, their_director: User) -> Certificate:
        course = _their_course(db, their_director, "their-course-cert")
        student = User(
            id=uuid.uuid4(),
            email="their-student@example.com",
            full_name="Their Student",
            role=UserRole.STUDENT.value,
            organization_id=THEIR_ORGANIZATION_ID,
        )
        db.add(student)
        db.flush()
        cert = Certificate(
            id=uuid.uuid4(),
            organization_id=THEIR_ORGANIZATION_ID,
            user_id=student.id,
            course_id=course.id,
            status=CertificateStatus.TEACHER_APPROVED,
            teacher_approved_at=datetime.now(UTC),
            teacher_approved_by=their_director.id,
        )
        db.add(cert)
        db.commit()
        return cert

    def test_their_certificate_is_not_in_our_queue(
        self, our_director_client: TestClient, db: Session, their_director: User
    ):
        cert = self._their_certificate(db, their_director)
        resp = our_director_client.get("/api/v1/certificates/admin/pending")
        assert resp.status_code == 200, resp.text
        assert str(cert.id) not in resp.text
        assert "their-student@example.com" not in resp.text

    def test_we_cannot_issue_their_certificate(
        self, our_director_client: TestClient, db: Session, their_director: User
    ):
        """Issuance mints a public number and cannot be undone."""
        cert = self._their_certificate(db, their_director)
        resp = our_director_client.put(f"/api/v1/certificates/{cert.id}/admin-approve")
        assert resp.status_code == 404, resp.text

        db.refresh(cert)
        assert cert.status == CertificateStatus.TEACHER_APPROVED
        assert cert.certificate_number is None

    def test_we_cannot_issue_their_certificate_from_before_the_column_was_written(
        self, our_director_client: TestClient, db: Session, their_director: User
    ):
        """The request path wrote no ``organization_id`` from 2026-08-27 to
        2026-10-17, and the gate let a NULL through. Such a row belongs to
        its course's organization, not to whoever asks first."""
        cert = self._their_certificate(db, their_director)
        db.query(Certificate).filter(Certificate.id == cert.id).update({Certificate.organization_id: None})
        db.commit()

        resp = our_director_client.put(f"/api/v1/certificates/{cert.id}/admin-approve")
        assert resp.status_code == 404, resp.text

        db.refresh(cert)
        assert cert.status == CertificateStatus.TEACHER_APPROVED
        assert cert.certificate_number is None

    def test_their_director_still_issues_their_certificate_from_before_the_column_was_written(
        self, our_director_client: TestClient, db: Session, their_director: User
    ):
        """Fail-closed must not lock out the school the row belongs to:
        with the column empty, the course's organization decides, and its
        own director (not the one who signed as teacher) issues it."""
        cert = self._their_certificate(db, their_director)
        db.query(Certificate).filter(Certificate.id == cert.id).update({Certificate.organization_id: None})
        their_second_director = User(
            id=uuid.uuid4(),
            email="their-second-director@example.com",
            full_name="Their Second Director",
            role=UserRole.DIRECTOR.value,
            organization_id=THEIR_ORGANIZATION_ID,
        )
        db.add(their_second_director)
        db.commit()

        _act_as(their_second_director)
        resp = our_director_client.put(f"/api/v1/certificates/{cert.id}/admin-approve")
        assert resp.status_code == 200, resp.text

        db.refresh(cert)
        assert cert.status == CertificateStatus.APPROVED
        assert cert.certificate_number is not None

    def test_a_certificate_with_no_course_and_no_organization_stays_with_platform_staff(
        self, our_director_client: TestClient, db: Session, their_director: User
    ):
        """A hard-deleted course leaves ``course_id`` NULL: nobody is left
        to vouch for the row, so no director passes the gate."""
        cert = self._their_certificate(db, their_director)
        db.query(Certificate).filter(Certificate.id == cert.id).update(
            {Certificate.organization_id: None, Certificate.course_id: None}
        )
        db.commit()

        resp = our_director_client.put(f"/api/v1/certificates/{cert.id}/admin-approve")
        assert resp.status_code == 404, resp.text
        _act_as(their_director)
        resp = our_director_client.put(f"/api/v1/certificates/{cert.id}/admin-approve")
        assert resp.status_code == 404, resp.text

        db.refresh(cert)
        assert cert.status == CertificateStatus.TEACHER_APPROVED
        assert cert.certificate_number is None

    def test_a_request_is_filed_under_the_course_s_organization(
        self, our_director_client: TestClient, db: Session, their_director: User
    ):
        """Requested through the API, a certificate carries its course's
        organization from the start — and so is in that director's queue
        once the teacher has signed, and in nobody else's."""
        course = _their_course(db, their_director, "their-course-request")
        student = User(
            id=uuid.uuid4(),
            email="their-graduate@example.com",
            full_name="Their Graduate",
            role=UserRole.STUDENT.value,
            organization_id=THEIR_ORGANIZATION_ID,
        )
        db.add(student)
        db.add(Enrollment(id="enr-their-course-request", user_id=student.id, course_id=course.id, progress=100))
        db.commit()

        _act_as(student)
        resp = our_director_client.post(f"/api/v1/certificates/course/{course.id}")
        assert resp.status_code == 201, resp.text
        cert = db.query(Certificate).filter(Certificate.id == uuid.UUID(resp.json()["id"])).one()
        assert cert.organization_id == THEIR_ORGANIZATION_ID

        _act_as(their_director)
        resp = our_director_client.put(f"/api/v1/certificates/{cert.id}/teacher-approve")
        assert resp.status_code == 200, resp.text
        resp = our_director_client.get("/api/v1/certificates/admin/pending")
        assert resp.status_code == 200, resp.text
        assert str(cert.id) in resp.text


def _act_as(user: User) -> None:
    """Swap who the signed-in client is, consent gate included."""
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_optional_user] = lambda: user
    app.dependency_overrides[consent_subject] = lambda: user


class TestInvitations:
    def test_their_invitation_is_not_in_our_list(
        self, our_director_client: TestClient, db: Session, their_director: User
    ):
        invitation = Invitation(
            id=uuid.uuid4(),
            email="recruit@example.com",
            role=UserRole.TEACHER.value,
            invited_by=their_director.id,
            organization_id=THEIR_ORGANIZATION_ID,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
        db.add(invitation)
        db.commit()

        resp = our_director_client.get("/api/v1/invitations")
        assert resp.status_code == 200, resp.text
        assert "recruit@example.com" not in resp.text
