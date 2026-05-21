"""Business rules for certificate status transitions.

Each of the approve/reject flows shares the same shape:
  1. Load the certificate (404 if missing).
  2. Assert the current status is a valid starting state for this transition.
  3. Resolve the related course (soft-delete-aware for approvals; reject may
     still run against a deleted course so a bad request is not silently
     accepted).
  4. Assert the acting user owns the course (or is an allowed admin).
  5. Mutate the certificate, commit, refresh.
  6. Audit log and, for user-facing transitions, fire a notification.

Routers should stay as thin wrappers that map HTTP -> these functions.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from fastapi import HTTPException, Request, status

from app.api.dependencies import assert_course_owner
from app.models.certificate import Certificate
from app.models.course import Course
from app.models.user import UserRole
from app.services.audit_service import log_action
from app.services.notification_service import create_notification

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User


def generate_certificate_number() -> str:
    """Opaque, human-presentable certificate id (stored verbatim)."""
    raw = f"{uuid.uuid4().hex}{time.time()}"
    return "CERT-" + hashlib.sha256(raw.encode()).hexdigest()[:12].upper()


def _load_cert_or_404(db: Session, cert_id: UUID, *, for_update: bool = False) -> Certificate:
    """Load a certificate row, optionally with ``FOR UPDATE``.

    Transition helpers (``teacher_approve`` / ``admin_approve`` /
    ``reject``) pass ``for_update=True`` so concurrent reviewer clicks
    serialize on the row. Without it, two parallel approve clicks both
    pass the ``_assert_status`` gate, both regenerate
    ``certificate_number``, both fire the ``certificate_approved``
    notification, and both write an audit row. Read paths use the
    default ``for_update=False`` — no need to hold a lock for a view.
    SQLite (test path) treats ``with_for_update`` as a no-op.
    """
    q = db.query(Certificate).filter(Certificate.id == cert_id)
    if for_update:
        q = q.with_for_update()
    cert = q.first()
    if not cert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate not found",
        )
    return cert


def _load_active_course_or_403(
    db: Session,
    course_id: str | None,
    *,
    ownership_detail: str,
) -> Course:
    """Load a non-deleted course. If it's gone, surface a 403 with the
    provided ownership-denied message — a missing course for a cert is
    indistinguishable to the caller from "you don't own it".

    ``course_id`` is nullable on ``Certificate`` because the FK fires
    ``ON DELETE SET NULL`` when the underlying course is hard-deleted (see
    migration ``20260516020225``). An archived certificate can no longer be
    teacher-approved or admin-approved — there's no course to verify
    ownership against — so we collapse that to the same 403.
    """
    if course_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ownership_detail)
    course = db.query(Course).filter(Course.id == course_id, Course.deleted_at.is_(None)).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ownership_detail)
    return course


def _assert_status(cert: Certificate, expected: str | tuple[str, ...]) -> None:
    allowed = (expected,) if isinstance(expected, str) else expected
    if cert.status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_status_error_message(cert, allowed),
        )


def _assert_not_self_approval(cert: Certificate, approver: User) -> None:
    """Refuse approval / issuance when the approver is the certificate recipient.

    A teacher who owns a course satisfies ``assert_course_owner``, and an
    admin satisfies ``require_admin`` — but neither check stops them from
    being the *student* whose certificate is being signed off. That path
    would let a course owner enroll in their own course, request a cert,
    and self-sign it; or an admin to issue their own cert with no second
    pair of eyes. Both undermine the two-stage approval design.
    """
    if str(cert.user_id) == str(approver.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot approve or issue your own certificate",
        )


def _status_error_message(cert: Certificate, allowed: tuple[str, ...]) -> str:
    if allowed == ("pending",):
        return f"Certificate is not pending (current status: {cert.status})"
    if allowed == ("teacher_approved",):
        return f"Certificate must be teacher-approved first (current status: {cert.status})"
    return f"Certificate cannot transition from status: {cert.status}"


def teacher_approve(db: Session, cert_id: UUID, teacher: User, request: Request) -> Certificate:
    cert = _load_cert_or_404(db, cert_id, for_update=True)
    _assert_status(cert, "pending")
    _assert_not_self_approval(cert, teacher)

    ownership_detail = "You can only approve certificates for your own courses"
    course = _load_active_course_or_403(db, cert.course_id, ownership_detail=ownership_detail)
    assert_course_owner(course, teacher, allow_admin=False, detail=ownership_detail)

    cert.status = "teacher_approved"
    cert.teacher_approved_at = datetime.now(UTC)
    cert.teacher_approved_by = teacher.id
    db.commit()
    db.refresh(cert)

    log_action(
        db,
        teacher.id,
        "approve",
        "certificate",
        str(cert_id),
        details={"level": "teacher"},
        request=request,
    )
    return cert


def admin_approve(db: Session, cert_id: UUID, admin: User, request: Request) -> Certificate:
    cert = _load_cert_or_404(db, cert_id, for_update=True)
    _assert_status(cert, "teacher_approved")
    _assert_not_self_approval(cert, admin)

    # Two-eyes guard. An admin who is ALSO the course's teacher can land on
    # the cert at the ``teacher_approved`` stage (they signed it themselves
    # via ``teacher_approve``) and then immediately admin-approve it,
    # collapsing the two-step review into one human. Refuse when the
    # admin's id matches the teacher-approver's so issuance always involves
    # two distinct accounts.
    if cert.teacher_approved_by is not None and str(cert.teacher_approved_by) == str(admin.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You can't admin-approve a certificate you teacher-approved yourself. "
                "Another admin needs to sign off on this issuance."
            ),
        )

    cert.status = "approved"
    cert.certificate_number = generate_certificate_number()
    now = datetime.now(UTC)
    cert.admin_approved_at = now
    cert.admin_approved_by = admin.id
    cert.issued_at = now

    # Soft-deleted course is OK here — we still notify the student and issue
    # the cert since the course was live when approval started.
    course = db.query(Course).filter(Course.id == cert.course_id, Course.deleted_at.is_(None)).first()
    course_title = course.title if course else "a course"
    create_notification(
        db,
        user_id=cert.user_id,
        type="certificate_approved",
        title="Certificate Approved",
        message=f'Your certificate for "{course_title}" has been approved!',
        link="/certificates",
        metadata={"course_id": cert.course_id, "certificate_id": str(cert.id)},
    )

    db.commit()
    db.refresh(cert)

    log_action(
        db,
        admin.id,
        "approve",
        "certificate",
        str(cert_id),
        details={"level": "admin"},
        request=request,
    )
    return cert


def reject(db: Session, cert_id: UUID, user: User, request: Request) -> Certificate:
    cert = _load_cert_or_404(db, cert_id, for_update=True)
    if cert.status in ("approved", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Certificate cannot be rejected (current status: {cert.status})",
        )

    # Stage-gated authorisation:
    #   pending           -> teacher (course owner) or admin
    #   teacher_approved  -> admin only (the cert is at the admin desk;
    #                        the original teacher already signed off and
    #                        shouldn't be able to walk it back without
    #                        a second pair of eyes)
    # Without this gate, a course-owning teacher could teacher-approve a
    # cert, change their mind, and reject it after it reached the admin
    # queue -- effectively a one-person veto of their own prior approval.
    if cert.status == "teacher_approved" and user.role != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=("Only an administrator can reject a certificate that has already passed teacher approval."),
        )

    ownership_detail = "You can only reject certificates for your own courses"
    # Reject does not require the course to be live — teachers may still need
    # to clear a request against a course they've since soft-deleted.
    course = db.query(Course).filter(Course.id == cert.course_id).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=ownership_detail)
    assert_course_owner(course, user, detail=ownership_detail)

    cert.status = "rejected"

    create_notification(
        db,
        user_id=cert.user_id,
        type="certificate_rejected",
        title="Certificate Rejected",
        message=f'Your certificate request for "{course.title}" was rejected.',
        link="/certificates",
        metadata={"course_id": cert.course_id, "certificate_id": str(cert.id)},
    )

    db.commit()
    db.refresh(cert)

    log_action(db, user.id, "reject", "certificate", str(cert_id), request=request)
    return cert
