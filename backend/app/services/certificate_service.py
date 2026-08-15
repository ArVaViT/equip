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

from fastapi import Request, status

from app.core.errors import ErrorCode, equip_error
from app.core.i18n import t
from app.models.certificate import Certificate, CertificateStatus
from app.models.course import Course
from app.models.user import User, UserRole
from app.schemas.locale import LocaleCode, normalize_locale
from app.services.audit_service import log_action
from app.services.certificate_grade_snapshot import snapshot_certificate_grade
from app.services.domain_access import assert_course_owner
from app.services.notification_service import create_notification
from app.services.translation.resolve_for_display import fetch_course_titles_by_id

# The language of the document itself. A certificate is read by people
# with no account here — an employer, a pastor — and possibly years
# later. It says one thing to all of them. Matches the grade sheet's
# ``SHEET_LOCALE``.
CERTIFICATE_LOCALE: LocaleCode = "en"


def _recipient_locale(db: Session, user_id: uuid.UUID | str) -> str:
    raw = db.query(User.preferred_locale).filter(User.id == user_id).scalar()
    return normalize_locale(raw)


if TYPE_CHECKING:
    from sqlalchemy.orm import Session


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
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Certificate not found",
            context={"resource_type": "certificate", "resource_id": str(cert_id)},
        )
    return cert


def _assert_student_active(db: Session, cert: Certificate) -> None:
    """Refuse to advance a certificate whose student was deactivated.

    Deactivated students are hidden from both pending queues, so an
    approve-by-id against one is a stale click (or a probe). Surface a
    409 rather than silently issuing a credential to a soft-deleted
    account; restoring the student makes the certificate approvable
    again.
    """
    deactivated = db.query(User.deactivated_at).filter(User.id == cert.user_id).scalar()
    if deactivated is not None:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_409_CONFLICT,
            message="Cannot approve a certificate for a deactivated account",
            context={"resource_type": "certificate", "resource_id": str(cert.id)},
        )


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
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message=ownership_detail,
        )
    course = db.query(Course).filter(Course.id == course_id, Course.deleted_at.is_(None)).first()
    if not course:
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message=ownership_detail,
        )
    return course


def _assert_status(cert: Certificate, expected: str | tuple[str, ...]) -> None:
    allowed = (expected,) if isinstance(expected, str) else expected
    if cert.status not in allowed:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message=_status_error_message(cert, allowed),
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
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="You cannot approve or issue your own certificate",
        )


def _status_error_message(cert: Certificate, allowed: tuple[str, ...]) -> str:
    if allowed == (CertificateStatus.PENDING,):
        return f"Certificate is not pending (current status: {cert.status})"
    if allowed == (CertificateStatus.TEACHER_APPROVED,):
        return f"Certificate must be teacher-approved first (current status: {cert.status})"
    return f"Certificate cannot transition from status: {cert.status}"


def teacher_approve(db: Session, cert_id: UUID, teacher: User, request: Request) -> Certificate:
    cert = _load_cert_or_404(db, cert_id, for_update=True)
    _assert_status(cert, CertificateStatus.PENDING)
    _assert_not_self_approval(cert, teacher)
    _assert_student_active(db, cert)

    ownership_detail = "You can only approve certificates for your own courses"
    course = _load_active_course_or_403(db, cert.course_id, ownership_detail=ownership_detail)
    # Deliberately owner-only (NOT the admin-allowed default used across the
    # content tree): certificate approval is two-stage (teacher -> admin), and
    # letting an admin act as the teacher here would collapse the two-man rule.
    assert_course_owner(course, teacher, allow_admin=False, detail=ownership_detail)

    cert.status = CertificateStatus.TEACHER_APPROVED
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
    _assert_status(cert, CertificateStatus.TEACHER_APPROVED)
    _assert_not_self_approval(cert, admin)
    _assert_student_active(db, cert)

    # Two-eyes guard. An admin who is ALSO the course's teacher can land on
    # the cert at the ``teacher_approved`` stage (they signed it themselves
    # via ``teacher_approve``) and then immediately admin-approve it,
    # collapsing the two-step review into one human. Refuse when the
    # admin's id matches the teacher-approver's so issuance always involves
    # two distinct accounts.
    if cert.teacher_approved_by is not None and str(cert.teacher_approved_by) == str(admin.id):
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message=(
                "You can't admin-approve a certificate you teacher-approved yourself. "
                "Another admin needs to sign off on this issuance."
            ),
        )

    cert.status = CertificateStatus.APPROVED
    cert.certificate_number = generate_certificate_number()
    now = datetime.now(UTC)
    cert.admin_approved_at = now
    cert.admin_approved_by = admin.id
    cert.issued_at = now

    # Soft-deleted course is OK here — we still notify the student and issue
    # the cert since the course was live when approval started.
    # Phase 5v: course title is resolved at the RECIPIENT's locale and the
    # title/message strings come from the locale branch so a Russian
    # student doesn't get English notification text.
    course = db.query(Course).filter(Course.id == cert.course_id, Course.deleted_at.is_(None)).first()

    # Freeze the grade onto the document at the moment it becomes one (M6).
    # Everything it is computed from stays editable afterwards, so a certificate
    # that recomputed on read would quietly change years later.
    snapshot_certificate_grade(db, cert, course)
    _snapshot_letterhead(db, cert, course)

    recipient_locale = normalize_locale(_recipient_locale(db, cert.user_id))
    course_title = (
        fetch_course_titles_by_id(db, [course.id], display_locale=recipient_locale).get(course.id) if course else None
    ) or t(recipient_locale, "fallback.your_course")
    notif_title = t(recipient_locale, "notif.cert_approved.title")
    notif_message = t(recipient_locale, "notif.cert_approved.body", course=course_title)
    create_notification(
        db,
        user_id=cert.user_id,
        type="certificate_approved",
        title=notif_title,
        message=notif_message,
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
    if cert.status in (CertificateStatus.APPROVED, CertificateStatus.REJECTED):
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"Certificate cannot be rejected (current status: {cert.status})",
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
    if cert.status == CertificateStatus.TEACHER_APPROVED and user.role != UserRole.ADMIN.value:
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Only an administrator can reject a certificate that has already passed teacher approval.",
        )

    ownership_detail = "You can only reject certificates for your own courses"
    # Reject does not require the course to be live — teachers may still need
    # to clear a request against a course they've since soft-deleted.
    course = db.query(Course).filter(Course.id == cert.course_id).first()
    if not course:
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message=ownership_detail,
        )
    assert_course_owner(course, user, detail=ownership_detail)

    cert.status = CertificateStatus.REJECTED

    # Phase 5v: same locale-aware fan-out as the approval path.
    recipient_locale = normalize_locale(_recipient_locale(db, cert.user_id))
    course_title = fetch_course_titles_by_id(db, [course.id], display_locale=recipient_locale).get(course.id) or t(
        recipient_locale, "fallback.your_course"
    )
    notif_title = t(recipient_locale, "notif.cert_rejected.title")
    notif_message = t(recipient_locale, "notif.cert_rejected.body", course=course_title)
    create_notification(
        db,
        user_id=cert.user_id,
        type="certificate_rejected",
        title=notif_title,
        message=notif_message,
        link="/certificates",
        metadata={"course_id": cert.course_id, "certificate_id": str(cert.id)},
    )

    db.commit()
    db.refresh(cert)

    log_action(db, user.id, "reject", "certificate", str(cert_id), request=request)
    return cert


def _snapshot_letterhead(db: Session, cert: Certificate, course: Course | None) -> None:
    """Freeze the words on the document, the way M6 froze the number.

    The school's name, the city under it, the student's name, the teacher's,
    and the course title — all as they stand at issuance. Read live instead
    and a school that renames itself in March rewrites what it certified in
    February, which is the same bug the ведомость had until it was fixed
    there.

    The course title is captured in English, not in the recipient's language.
    A certificate is the one artefact of this platform that leaves it: read by
    people with no account here, possibly years later. It has to say the same
    thing to all of them. The grade sheet already works this way
    (``SHEET_LOCALE``).
    """
    from app.models.user import User as _User
    from app.services.grading_scheme import get_org_settings

    settings = get_org_settings(db)
    cert.school_name = settings.school_name_en or settings.school_name_ru
    cert.school_city = settings.city

    student = db.query(_User).filter(_User.id == cert.user_id).first()
    # The legal name once memberships carry one; the profile name until then.
    cert.student_name = (student.full_name or student.email) if student else None

    if course is not None and course.created_by is not None:
        teacher = db.query(_User).filter(_User.id == course.created_by).first()
        cert.teacher_name = (teacher.full_name or teacher.email) if teacher else None

    if course is not None:
        # ``fetch_course_titles_by_id`` falls back to the course's own source
        # text when no English row exists — a course from before the
        # publication gate, or one whose English is still being checked. A
        # title in the wrong language is still better than a blank line on a
        # document someone has to show an employer.
        cert.course_title = fetch_course_titles_by_id(
            db,
            [course.id],
            display_locale=CERTIFICATE_LOCALE,
            # The one place that asks for another language on purpose. A
            # certificate is a document: a blank where the course name goes
            # is worse than a name in the language the teacher wrote it in.
            fallback="source_then_any",
        ).get(course.id)
