"""TDD spec — certificate lifecycle invariants.

The existing ``test_certificates_and_grades.py`` covers the happy
paths and most 4xx surfaces of the certificate endpoints. This file
pins the **invariants** that protect the institutional trust chain:

  * Two-eyes guard — the human who teacher-approved a cert cannot
    also admin-approve it, even if they hold the admin role.
  * Reject-stage authorisation — once a cert is teacher_approved,
    only an admin can reject it; the originating teacher loses the
    walk-back option.
  * Self-approval guard — the cert recipient cannot approve their
    own cert, regardless of their role.
  * Status transition matrix — illegal transitions
    (approved→pending, rejected→teacher_approved, etc.) are
    refused with a 400.
  * Cert number uniqueness — rapid issuance must not collide.

A regression in any of these silently corrupts the audit chain —
duplicate cert numbers, one-person sign-offs, undisclosed
approvers. These are the exact failure modes you only discover
after a relying party (employer, accreditation body) does their
own verification.

These tests exercise ``services/certificate_service.py`` directly
(unit level) rather than the HTTP layer — the refactor risk Agent B
flagged is that the service contract drift gets masked by the
route adapter.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.certificate import Certificate
from app.models.course import Course
from app.models.user import User, UserRole
from app.services.certificate_service import (
    admin_approve,
    generate_certificate_number,
    reject,
    teacher_approve,
)

TEACHER_ID = uuid.UUID("ccccaaaa-cccc-cccc-cccc-cccccccccccc")
OTHER_TEACHER_ID = uuid.UUID("ccccbbbb-cccc-cccc-cccc-cccccccccccc")
ADMIN_ID = uuid.UUID("ccccdddd-cccc-cccc-cccc-cccccccccccc")
OTHER_ADMIN_ID = uuid.UUID("ccccffff-cccc-cccc-cccc-cccccccccccc")
STUDENT_ID = uuid.UUID("ccccaaab-cccc-cccc-cccc-cccccccccccc")


@pytest.fixture
def db():
    from tests.conftest import test_engine

    session = Session(bind=test_engine)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def mock_request() -> Any:
    """Minimal Request stub for audit-log calls — those only read
    ``client.host`` and ``headers``. Returning a MagicMock saves us
    from constructing a Starlette Request."""
    req = MagicMock()
    req.client = MagicMock(host="127.0.0.1")
    req.headers = {}
    return req


def _make_user(db: Session, *, user_id: uuid.UUID, role: str) -> User:
    existing = db.query(User).filter(User.id == user_id).first()
    if existing:
        return existing
    user = User(
        id=user_id,
        email=f"cert-{user_id.hex[:8]}@test",
        full_name=f"Test {role}",
        role=role,
        preferred_locale="en",
    )
    db.add(user)
    db.commit()
    return user


def _make_course(db: Session, *, owner_id: uuid.UUID, course_id: str | None = None) -> Course:
    _make_user(db, user_id=owner_id, role=UserRole.TEACHER.value)
    course = Course(
        id=course_id or str(uuid.uuid4()),
        title="Genesis study course",
        description="Study guide for the book of Genesis.",
        status="published",
        source_locale="en",
        created_by=owner_id,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def _make_cert(
    db: Session,
    *,
    course: Course,
    student_id: uuid.UUID = STUDENT_ID,
    status: str = "pending",
    teacher_approved_by: uuid.UUID | None = None,
) -> Certificate:
    _make_user(db, user_id=student_id, role=UserRole.STUDENT.value)
    cert = Certificate(
        id=uuid.uuid4(),
        user_id=student_id,
        course_id=course.id,
        status=status,
        teacher_approved_by=teacher_approved_by,
    )
    db.add(cert)
    db.commit()
    db.refresh(cert)
    return cert


class TestTwoEyesApprovalGuard:
    """The admin who teacher-approved a cert cannot also admin-approve
    it. Without this guard, an admin who also teaches a course could
    collapse the two-stage review into one human (sign off as
    teacher, then issue as admin) — defeating the entire design.
    """

    def test_admin_who_teacher_approved_cannot_admin_approve(self, db, mock_request):
        # Admin acts as the course owner (teacher-stage) AND as admin.
        admin = _make_user(db, user_id=ADMIN_ID, role=UserRole.ADMIN.value)
        course = _make_course(db, owner_id=ADMIN_ID)  # admin owns the course
        cert = _make_cert(
            db,
            course=course,
            status="teacher_approved",
            teacher_approved_by=ADMIN_ID,  # admin already teacher-approved
        )

        with pytest.raises(HTTPException) as exc_info:
            admin_approve(db, cert.id, admin, mock_request)
        assert exc_info.value.status_code == 403
        assert "another admin" in exc_info.value.detail.lower()

    def test_different_admin_can_admin_approve_teacher_approved_cert(self, db, mock_request):
        # Sanity check: when the admin is different from the teacher-
        # approver, the gate passes.
        teacher = _make_user(db, user_id=TEACHER_ID, role=UserRole.TEACHER.value)
        admin = _make_user(db, user_id=ADMIN_ID, role=UserRole.ADMIN.value)
        course = _make_course(db, owner_id=teacher.id)
        cert = _make_cert(
            db,
            course=course,
            status="teacher_approved",
            teacher_approved_by=teacher.id,
        )

        result = admin_approve(db, cert.id, admin, mock_request)
        assert result.status == "approved"
        assert result.admin_approved_by == admin.id


class TestRejectStageAuthorisation:
    """Reject permissions tighten as the cert moves through stages.
    Pending → either teacher or admin. teacher_approved → admin only.
    Without the second gate, a teacher could approve and then reject
    their own prior decision (single-person veto)."""

    def test_teacher_cannot_reject_their_own_teacher_approved_cert(self, db, mock_request):
        teacher = _make_user(db, user_id=TEACHER_ID, role=UserRole.TEACHER.value)
        course = _make_course(db, owner_id=teacher.id)
        cert = _make_cert(
            db,
            course=course,
            status="teacher_approved",
            teacher_approved_by=teacher.id,
        )

        with pytest.raises(HTTPException) as exc_info:
            reject(db, cert.id, teacher, mock_request)
        assert exc_info.value.status_code == 403
        assert "administrator" in exc_info.value.detail.lower()

    def test_admin_can_reject_teacher_approved_cert(self, db, mock_request):
        teacher = _make_user(db, user_id=TEACHER_ID, role=UserRole.TEACHER.value)
        admin = _make_user(db, user_id=ADMIN_ID, role=UserRole.ADMIN.value)
        course = _make_course(db, owner_id=teacher.id)
        cert = _make_cert(
            db,
            course=course,
            status="teacher_approved",
            teacher_approved_by=teacher.id,
        )

        result = reject(db, cert.id, admin, mock_request)
        assert result.status == "rejected"

    def test_teacher_can_reject_pending_cert(self, db, mock_request):
        # At pending stage, the originating teacher hasn't committed
        # to anything — they can still reject without needing admin
        # involvement.
        teacher = _make_user(db, user_id=TEACHER_ID, role=UserRole.TEACHER.value)
        course = _make_course(db, owner_id=teacher.id)
        cert = _make_cert(db, course=course, status="pending")

        result = reject(db, cert.id, teacher, mock_request)
        assert result.status == "rejected"


class TestStatusTransitionMatrix:
    """Status transitions are constrained to legal forward paths:
       pending → teacher_approved → approved
                ↘ rejected            ↘ rejected
    No other transitions are allowed; every illegal one is a 400.
    """

    def test_admin_approve_on_pending_cert_fails(self, db, mock_request):
        """``admin_approve`` requires the cert to be already
        teacher_approved. A direct pending→approved skip would bypass
        the entire two-stage review."""
        admin = _make_user(db, user_id=ADMIN_ID, role=UserRole.ADMIN.value)
        teacher = _make_user(db, user_id=TEACHER_ID, role=UserRole.TEACHER.value)
        course = _make_course(db, owner_id=teacher.id)
        cert = _make_cert(db, course=course, status="pending")

        with pytest.raises(HTTPException) as exc_info:
            admin_approve(db, cert.id, admin, mock_request)
        assert exc_info.value.status_code == 400
        assert "teacher-approved" in exc_info.value.detail.lower()

    def test_teacher_approve_on_already_teacher_approved_fails(self, db, mock_request):
        """No double-tap of teacher_approve."""
        teacher = _make_user(db, user_id=TEACHER_ID, role=UserRole.TEACHER.value)
        course = _make_course(db, owner_id=teacher.id)
        cert = _make_cert(
            db,
            course=course,
            status="teacher_approved",
            teacher_approved_by=teacher.id,
        )

        with pytest.raises(HTTPException) as exc_info:
            teacher_approve(db, cert.id, teacher, mock_request)
        assert exc_info.value.status_code == 400
        assert "pending" in exc_info.value.detail.lower()

    def test_teacher_approve_on_approved_cert_fails(self, db, mock_request):
        teacher = _make_user(db, user_id=TEACHER_ID, role=UserRole.TEACHER.value)
        course = _make_course(db, owner_id=teacher.id)
        cert = _make_cert(db, course=course, status="approved")

        with pytest.raises(HTTPException):
            teacher_approve(db, cert.id, teacher, mock_request)

    def test_reject_on_approved_cert_fails(self, db, mock_request):
        teacher = _make_user(db, user_id=TEACHER_ID, role=UserRole.TEACHER.value)
        course = _make_course(db, owner_id=teacher.id)
        cert = _make_cert(db, course=course, status="approved")

        with pytest.raises(HTTPException) as exc_info:
            reject(db, cert.id, teacher, mock_request)
        assert exc_info.value.status_code == 400

    def test_reject_on_already_rejected_cert_fails(self, db, mock_request):
        teacher = _make_user(db, user_id=TEACHER_ID, role=UserRole.TEACHER.value)
        course = _make_course(db, owner_id=teacher.id)
        cert = _make_cert(db, course=course, status="rejected")

        with pytest.raises(HTTPException) as exc_info:
            reject(db, cert.id, teacher, mock_request)
        assert exc_info.value.status_code == 400


class TestSelfApprovalGuard:
    """The cert recipient cannot approve their own cert. Without
    this, a course-owning teacher could enroll in their own course,
    request a cert, and self-sign it; or an admin could issue their
    own cert with no second pair of eyes."""

    def test_teacher_cannot_teacher_approve_own_cert(self, db, mock_request):
        teacher = _make_user(db, user_id=TEACHER_ID, role=UserRole.TEACHER.value)
        course = _make_course(db, owner_id=teacher.id)
        # Teacher is also the recipient.
        cert = _make_cert(db, course=course, student_id=teacher.id, status="pending")

        with pytest.raises(HTTPException) as exc_info:
            teacher_approve(db, cert.id, teacher, mock_request)
        assert exc_info.value.status_code == 403
        assert "own" in exc_info.value.detail.lower()

    def test_admin_cannot_admin_approve_own_cert(self, db, mock_request):
        admin = _make_user(db, user_id=ADMIN_ID, role=UserRole.ADMIN.value)
        teacher = _make_user(db, user_id=TEACHER_ID, role=UserRole.TEACHER.value)
        course = _make_course(db, owner_id=teacher.id)
        # Admin is also the recipient. Teacher already approved (by a
        # DIFFERENT teacher) so the cert is at the admin desk.
        cert = _make_cert(
            db,
            course=course,
            student_id=admin.id,
            status="teacher_approved",
            teacher_approved_by=teacher.id,
        )

        with pytest.raises(HTTPException) as exc_info:
            admin_approve(db, cert.id, admin, mock_request)
        assert exc_info.value.status_code == 403
        assert "own" in exc_info.value.detail.lower()


class TestCertificateNumberUniqueness:
    """Cert numbers are the public identifier issued to graduates;
    a collision would silently break verify-by-number. The generator
    uses a SHA-256 prefix over UUID4 + time — verify the output is
    well-formed and unique across rapid generation."""

    def test_generated_number_has_expected_prefix_and_length(self):
        n = generate_certificate_number()
        assert n.startswith("CERT-")
        # CERT- (5) + 12 hex chars uppercase
        assert len(n) == 5 + 12
        assert n[5:].isalnum()
        assert n[5:] == n[5:].upper()

    def test_thousand_consecutive_generations_are_all_unique(self):
        # The hash-of-UUID4+time pattern should never collide in the
        # practical regime. A 1000-iteration check catches accidental
        # regressions (e.g. someone replacing UUID4 with time-only).
        seen: set[str] = set()
        for _ in range(1000):
            n = generate_certificate_number()
            assert n not in seen, f"collision on {n}"
            seen.add(n)
