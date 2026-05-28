from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_admin, require_teacher
from app.core.database import get_db
from app.models.certificate import Certificate
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.user import User
from app.schemas.certificate import CertificateResponse, CertificateVerifyResponse
from app.schemas.locale import LocaleCode, normalize_locale
from app.services import certificate_service
from app.services.translation.resolve_for_display import (
    fetch_overlay_triples_bulk,
    pick_overlay_value,
)

router = APIRouter(prefix="/certificates", tags=["certificates"])


def _localize_cert_responses(
    db: Session,
    certs: list[Certificate],
    *,
    display_locale: LocaleCode,
) -> list[CertificateResponse]:
    """Build ``CertificateResponse`` instances with the course title
    overlaid into the requested display locale. Falls back to the
    course's source title when no translation row exists.
    """
    if not certs:
        return []
    course_ids = sorted({str(c.course_id) for c in certs if c.course_id})
    if not course_ids:
        return [CertificateResponse.model_validate(c, from_attributes=True) for c in certs]
    courses = db.query(Course.id, Course.title, Course.source_locale).filter(Course.id.in_(course_ids)).all()
    course_meta: dict[str, tuple[str, LocaleCode]] = {
        str(cid): (title, normalize_locale(src)) for cid, title, src in courses
    }
    specs = [("course", cid, "title") for cid in course_meta]
    overlay = fetch_overlay_triples_bulk(db, specs, display_locale)
    out: list[CertificateResponse] = []
    for cert in certs:
        base = CertificateResponse.model_validate(cert, from_attributes=True)
        meta = course_meta.get(str(cert.course_id))
        if meta is None:
            out.append(base)
            continue
        source_title, source_locale = meta
        title = (
            pick_overlay_value(
                overlay,
                "course",
                str(cert.course_id),
                "title",
                source_title,
                source_locale=source_locale,
                display_locale=display_locale,
            )
            or source_title
        )
        out.append(base.model_copy(update={"course_title": title}))
    return out


@router.post("/course/{course_id}", response_model=CertificateResponse, status_code=status.HTTP_201_CREATED)
def request_certificate(
    course_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Certificate:
    """Request a certificate (creates a pending request).

    Re-request after rejection: the cert row carries a ``(user_id,
    course_id)`` unique constraint, so we cannot just INSERT a fresh
    pending row when a previous request was rejected. Instead we reset
    the rejected row back to ``pending`` (clearing approver timestamps)
    so the student can have another go through the teacher / admin
    workflow — matching ``reject``'s docstring promise that "a rejected
    certificate stays rejected and the student must re-request".
    """
    # Soft-deleted courses must not accept new certificate requests.
    course = db.query(Course).filter(Course.id == course_id, Course.deleted_at.is_(None)).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    enrollment = (
        db.query(Enrollment).filter(Enrollment.user_id == current_user.id, Enrollment.course_id == course_id).first()
    )
    if not enrollment:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not enrolled in this course")
    if enrollment.progress < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Course not completed. Current progress: {enrollment.progress}%",
        )

    existing = (
        db.query(Certificate).filter(Certificate.user_id == current_user.id, Certificate.course_id == course_id).first()
    )
    if existing is not None:
        if existing.status == "rejected":
            # Reopen the request rather than silently returning the
            # rejected row (which previously made the "request" button a
            # no-op for any student who had been rejected once).
            existing.status = "pending"
            existing.teacher_approved_at = None
            existing.teacher_approved_by = None
            existing.admin_approved_at = None
            existing.admin_approved_by = None
            db.commit()
            db.refresh(existing)
        return existing

    cert = Certificate(user_id=current_user.id, course_id=course_id, status="pending")
    db.add(cert)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        existing = (
            db.query(Certificate)
            .filter(Certificate.user_id == current_user.id, Certificate.course_id == course_id)
            .first()
        )
        if existing is not None:
            if existing.status == "rejected":
                existing.status = "pending"
                existing.teacher_approved_at = None
                existing.teacher_approved_by = None
                existing.admin_approved_at = None
                existing.admin_approved_by = None
                db.commit()
                db.refresh(existing)
            return existing
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Certificate already requested") from exc
    db.refresh(cert)
    return cert


@router.get("/course/{course_id}", response_model=CertificateResponse)
def get_course_certificate(
    response: Response,
    course_id: str,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CertificateResponse:
    """Get the current user's certificate for a specific course."""
    response.headers["Vary"] = "Accept-Language"
    cert = (
        db.query(Certificate).filter(Certificate.user_id == current_user.id, Certificate.course_id == course_id).first()
    )
    if not cert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No certificate found")
    display_locale: LocaleCode = normalize_locale(accept_language)
    return _localize_cert_responses(db, [cert], display_locale=display_locale)[0]


@router.get("/my", response_model=list[CertificateResponse])
def list_my_certificates(
    response: Response,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CertificateResponse]:
    response.headers["Vary"] = "Accept-Language"
    rows = (
        db.query(Certificate)
        .filter(Certificate.user_id == current_user.id)
        .order_by(Certificate.requested_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    display_locale: LocaleCode = normalize_locale(accept_language)
    return _localize_cert_responses(db, rows, display_locale=display_locale)


def _enrich_pending_certs(
    db: Session,
    certs: list[Certificate],
) -> list[CertificateResponse]:
    """Resolve the contextual labels (student name/email, course title,
    teacher approver name) for a list of pending Certificate rows.

    Three batched lookups instead of N+1: one ``users`` query (covers
    both student and approver in a single IN-list) and one ``courses``
    query. Empty input short-circuits so the common no-pending case
    stays free.
    """
    if not certs:
        return []
    student_ids = {c.user_id for c in certs}
    approver_ids = {c.teacher_approved_by for c in certs if c.teacher_approved_by}
    course_ids = {str(c.course_id) for c in certs if c.course_id}
    user_meta: dict[str, tuple[str | None, str]] = {}
    if student_ids or approver_ids:
        for uid, full_name, email in (
            db.query(User.id, User.full_name, User.email).filter(User.id.in_(student_ids | approver_ids)).all()
        ):
            user_meta[str(uid)] = (full_name, email)
    course_titles: dict[str, str] = {}
    if course_ids:
        for cid, title in db.query(Course.id, Course.title).filter(Course.id.in_(course_ids)).all():
            course_titles[str(cid)] = title

    out: list[CertificateResponse] = []
    for cert in certs:
        student = user_meta.get(str(cert.user_id))
        approver = user_meta.get(str(cert.teacher_approved_by)) if cert.teacher_approved_by else None
        base = CertificateResponse.model_validate(cert, from_attributes=True)
        out.append(
            base.model_copy(
                update={
                    "student_name": student[0] if student else None,
                    "student_email": student[1] if student else None,
                    "course_title": (
                        course_titles.get(str(cert.course_id)) if cert.course_id else cert.archived_course_title
                    ),
                    "teacher_approver_name": ((approver[0] or approver[1]) if approver else None),
                }
            )
        )
    return out


@router.get("/pending", response_model=list[CertificateResponse])
def list_pending_certificates(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> list[CertificateResponse]:
    """Teacher: list pending certificates for courses they teach.

    Returns enriched rows (student name + email, course title) so the
    teacher dashboard's pending-certs panel can render context without
    a per-row follow-up call.
    """
    certs = (
        db.query(Certificate)
        .join(Course, Course.id == Certificate.course_id)
        .filter(
            Course.created_by == teacher.id,
            Course.deleted_at.is_(None),
            Certificate.status == "pending",
        )
        .order_by(Certificate.requested_at.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return _enrich_pending_certs(db, certs)


@router.get("/admin/pending", response_model=list[CertificateResponse])
def list_admin_pending_certificates(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[CertificateResponse]:
    """Admin: teacher-approved certificates awaiting admin approval.

    Returns enriched rows (student name + email, course title, name of
    the teacher who signed off) so the admin overview panel can render
    a real \"who / what / when\" context without per-row follow-up calls.
    """
    certs = (
        db.query(Certificate)
        .filter(Certificate.status == "teacher_approved")
        .order_by(Certificate.teacher_approved_at.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return _enrich_pending_certs(db, certs)


@router.put(
    "/{cert_id}/teacher-approve",
    response_model=CertificateResponse,
    summary="Teacher signs off on a pending certificate request",
    responses={
        200: {"description": "Certificate moved from ``pending`` to ``teacher_approved``"},
        400: {"description": "Certificate is not in ``pending`` state"},
        403: {"description": "Caller does not own the certificate's course"},
        404: {"description": "Certificate not found"},
    },
)
def teacher_approve_certificate(
    cert_id: UUID,
    request: Request,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> Certificate:
    """First step of the two-stage approval workflow.

    The teacher who owns the course must confirm the student earned the
    certificate before an admin can issue it. This call is idempotent
    against concurrent reviewer clicks: a ``FOR UPDATE`` lock on the
    certificate row serializes parallel approvers (see
    ``certificate_service._load_cert_or_404``).
    """
    return certificate_service.teacher_approve(db, cert_id, teacher, request)


@router.put(
    "/{cert_id}/admin-approve",
    response_model=CertificateResponse,
    summary="Admin issues a teacher-approved certificate",
    responses={
        200: {"description": "Certificate issued with a unique ``certificate_number``"},
        400: {"description": "Certificate is not in ``teacher_approved`` state"},
        403: {"description": "Caller is not an admin"},
        404: {"description": "Certificate not found"},
    },
)
def admin_approve_certificate(
    cert_id: UUID,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Certificate:
    """Second step. Generates the public ``certificate_number`` and
    fires a ``certificate_approved`` notification to the student. The
    ``FOR UPDATE`` lock prevents double-issuance from concurrent admin
    clicks."""
    return certificate_service.admin_approve(db, cert_id, admin, request)


@router.put(
    "/{cert_id}/reject",
    response_model=CertificateResponse,
    summary="Reject a certificate request (teacher or admin)",
    responses={
        200: {"description": "Certificate moved to ``rejected`` state"},
        400: {"description": "Certificate is already in a terminal state"},
        403: {"description": "Caller does not own the course"},
        404: {"description": "Certificate not found"},
    },
)
def reject_certificate(
    cert_id: UUID,
    request: Request,
    current_user: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> Certificate:
    """Either reviewer (teacher or admin) can reject up until issuance.
    Cannot be reversed — a rejected certificate stays rejected and the
    student must re-request."""
    return certificate_service.reject(db, cert_id, current_user, request)


@router.get(
    "/verify/{certificate_number}",
    response_model=CertificateVerifyResponse,
    summary="Public lookup by certificate number",
    responses={
        200: {
            "description": "``valid=true`` with issuee + course info if the number "
            "matches an issued certificate, else ``valid=false`` with no PII."
        },
    },
)
def verify_certificate(
    # Real certificate numbers are ~17 chars (``CERT-`` + 12 hex). The
    # column is ``String(50)``; cap the path param at 50 so a crafted
    # multi-KB URL is rejected by FastAPI before the public unauth
    # rate-limit bucket and the DB scan run.
    certificate_number: str = Path(..., max_length=50),
    db: Session = Depends(get_db),
) -> CertificateVerifyResponse:
    """Unauthenticated certificate verification.

    Used by recipients to share their credential — the URL is something
    like ``https://equipbible.com/verify/{number}`` that the SPA hits
    this endpoint from. Returns a minimal PII surface (``user_name`` +
    ``course_title``) only for valid numbers; invalid numbers return
    ``valid=false`` with the number echoed so the caller can show a
    "not found" page without confirming what other numbers exist.
    """
    row = (
        db.query(Certificate, User, Course)
        .outerjoin(User, Certificate.user_id == User.id)
        .outerjoin(Course, Certificate.course_id == Course.id)
        .filter(Certificate.certificate_number == certificate_number)
        .first()
    )
    if not row:
        return CertificateVerifyResponse(valid=False, certificate_number=certificate_number)

    cert, user, course = row
    # Fall back to ``archived_course_title`` (snapshotted by the
    # BEFORE-DELETE trigger on ``courses``) when the source course has
    # been deleted — the credential still has to verify even after the
    # underlying course is gone.
    course_title = course.title if course else cert.archived_course_title
    return CertificateVerifyResponse(
        valid=True,
        certificate_number=cert.certificate_number,
        user_name=user.full_name if user else None,
        course_title=course_title,
        issued_at=cert.issued_at,
    )
