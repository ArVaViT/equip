"""Top-level admin cohort API.

Implements ADR-010. Cohorts are admin-owned batches of students that
take some set of courses together over a date window. The director
creates an empty cohort, attaches courses + students via the junction
endpoints, and the backend auto-creates the per-(student, course)
enrollment rows so the director never has to do that by hand.

Visibility rules:

- All write surfaces (create / update / delete / attach / add student /
  complete) require admin role. Teachers do not manage cohorts.
- ``GET /cohorts/course/{course_id}`` is kept as a public-ish read so
  the catalog (for the enroll dialog cohort dropdown) and a teacher's
  gradebook filter can list cohorts that include their course. Same
  visibility gate as before: course must be published OR viewer is
  owner / admin.

The legacy course-scoped create endpoint (``POST /cohorts/course/{id}``)
is intentionally removed. Frontend that called it is being migrated to
the top-level admin UI.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_optional_user, require_admin
from app.core.database import get_db
from app.models.cohort import Cohort, CohortCourse
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.user import User, UserRole
from app.schemas.cohort import (
    CohortCourseAttach,
    CohortCreate,
    CohortResponse,
    CohortStudentAdd,
    CohortUpdate,
)
from app.schemas.locale import LocaleCode, normalize_locale
from app.services.translation.pipeline_hooks import reconcile_entity_if_course_published
from app.services.translation.resolve_for_display import (
    fetch_overlay_triples_bulk,
    pick_overlay_value,
)

router = APIRouter(prefix="/cohorts", tags=["cohorts"])


# ----------------------------- helpers --------------------------------


def _course_ids_for_cohort(db: Session, cohort_id: UUID) -> list[str]:
    """Return course_ids attached to the cohort via the junction."""
    return [row[0] for row in db.query(CohortCourse.course_id).filter(CohortCourse.cohort_id == cohort_id).all()]


def _student_count(db: Session, cohort_id: UUID) -> int:
    """Distinct users enrolled in this cohort. A cohort student typically
    has N enrollment rows (one per attached course), so we COUNT DISTINCT
    rather than count enrollment rows."""
    return (
        db.query(func.count(func.distinct(Enrollment.user_id))).filter(Enrollment.cohort_id == cohort_id).scalar() or 0
    )


def _serialize(db: Session, cohort: Cohort) -> CohortResponse:
    resp = CohortResponse.model_validate(cohort)
    resp.course_ids = _course_ids_for_cohort(db, cohort.id)
    resp.student_count = _student_count(db, cohort.id)
    return resp


def _get_or_404(db: Session, cohort_id: UUID) -> Cohort:
    cohort = db.query(Cohort).filter(Cohort.id == cohort_id).first()
    if not cohort:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cohort not found")
    return cohort


def _course_or_404(db: Session, course_id: str) -> Course:
    course = db.query(Course).filter(Course.id == course_id, Course.deleted_at.is_(None)).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    return course


# ----------------------------- admin CRUD -----------------------------


@router.get("", response_model=list[CohortResponse])
def list_cohorts(
    status_filter: str | None = Query(None, alias="status"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[CohortResponse]:
    """Admin-wide cohort list. Optional ``status`` filter
    (``upcoming|active|completed``)."""
    q = db.query(Cohort)
    if status_filter:
        q = q.filter(Cohort.status == status_filter)
    cohorts = q.order_by(Cohort.start_date.desc()).all()
    return [_serialize(db, c) for c in cohorts]


@router.post("", response_model=CohortResponse, status_code=status.HTTP_201_CREATED)
def create_cohort(
    data: CohortCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CohortResponse:
    """Create an empty cohort. Courses and students attach via the
    separate junction endpoints — keeps each step independently
    auditable."""
    cohort = Cohort(
        name=data.name,
        start_date=data.start_date,
        end_date=data.end_date,
        enrollment_start=data.enrollment_start,
        enrollment_end=data.enrollment_end,
        max_students=data.max_students,
        created_by=admin.id,
    )
    db.add(cohort)
    db.commit()
    db.refresh(cohort)
    return _serialize(db, cohort)


@router.get("/{cohort_id}", response_model=CohortResponse)
def get_cohort(
    cohort_id: UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CohortResponse:
    cohort = _get_or_404(db, cohort_id)
    return _serialize(db, cohort)


@router.patch("/{cohort_id}", response_model=CohortResponse)
def update_cohort(
    cohort_id: UUID,
    data: CohortUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CohortResponse:
    cohort = _get_or_404(db, cohort_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(cohort, field, value)
    db.commit()
    db.refresh(cohort)
    # Translation reconcile for each course this cohort is attached to —
    # cohort name is teacher/director-authored, so each course-locale
    # pair gets a translation overlay row.
    for cid in _course_ids_for_cohort(db, cohort.id):
        course = db.query(Course).filter(Course.id == cid).first()
        if course is not None:
            reconcile_entity_if_course_published(db, "cohort", cohort)
    return _serialize(db, cohort)


@router.delete("/{cohort_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cohort(
    cohort_id: UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    """Delete the cohort. ``ON DELETE CASCADE`` on the junction removes
    course attachments; the enrollment rows survive with their
    ``cohort_id`` set to NULL (``ON DELETE SET NULL`` on the FK) — that
    way historical grade data is preserved as orphaned solo enrollments."""
    cohort = _get_or_404(db, cohort_id)
    db.delete(cohort)
    db.commit()


@router.post("/{cohort_id}/complete", response_model=CohortResponse)
def complete_cohort(
    cohort_id: UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CohortResponse:
    cohort = _get_or_404(db, cohort_id)
    if cohort.status == "completed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cohort is already completed",
        )
    cohort.status = "completed"
    db.commit()
    db.refresh(cohort)
    return _serialize(db, cohort)


# ---------------------- junction: cohort x courses --------------------


@router.get("/{cohort_id}/courses", response_model=list[str])
def list_cohort_courses(
    cohort_id: UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[str]:
    _get_or_404(db, cohort_id)
    return _course_ids_for_cohort(db, cohort_id)


@router.post(
    "/{cohort_id}/courses",
    response_model=CohortResponse,
    status_code=status.HTTP_201_CREATED,
)
def attach_course(
    cohort_id: UUID,
    body: CohortCourseAttach,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CohortResponse:
    """Attach a course to the cohort. Any students already in the cohort
    are auto-enrolled in this course (one enrollment row per student,
    all sharing the same ``cohort_id``)."""
    cohort = _get_or_404(db, cohort_id)
    course = _course_or_404(db, body.course_id)

    # Already attached? Idempotent.
    existing = (
        db.query(CohortCourse).filter(CohortCourse.cohort_id == cohort.id, CohortCourse.course_id == course.id).first()
    )
    if existing is None:
        db.add(CohortCourse(cohort_id=cohort.id, course_id=course.id))
        db.flush()

    # Auto-enroll every existing cohort student in this course.
    existing_students = db.query(Enrollment.user_id).filter(Enrollment.cohort_id == cohort.id).distinct().all()
    for (user_id,) in existing_students:
        already = (
            db.query(Enrollment)
            .filter(
                Enrollment.user_id == user_id,
                Enrollment.course_id == course.id,
                Enrollment.cohort_id == cohort.id,
            )
            .first()
        )
        if already is None:
            db.add(
                Enrollment(
                    id=f"enr-{cohort.id}-{user_id}-{course.id}",
                    user_id=user_id,
                    course_id=course.id,
                    cohort_id=cohort.id,
                )
            )

    try:
        db.commit()
    except IntegrityError:
        # A concurrent attach raced us; safe to roll back and re-read.
        db.rollback()
    db.refresh(cohort)
    reconcile_entity_if_course_published(db, "cohort", cohort)
    return _serialize(db, cohort)


@router.delete(
    "/{cohort_id}/courses/{course_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def detach_course(
    cohort_id: UUID,
    course_id: str,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    """Detach a course from the cohort. Enrollment rows for cohort
    students in this course are NOT deleted — their ``cohort_id`` is
    set to NULL so grades survive as orphaned solo enrollments."""
    cohort = _get_or_404(db, cohort_id)
    link = (
        db.query(CohortCourse).filter(CohortCourse.cohort_id == cohort.id, CohortCourse.course_id == course_id).first()
    )
    if link is None:
        return
    db.query(Enrollment).filter(
        Enrollment.cohort_id == cohort.id,
        Enrollment.course_id == course_id,
    ).update({Enrollment.cohort_id: None}, synchronize_session=False)
    db.delete(link)
    db.commit()


# ---------------------- junction: cohort x students -------------------


@router.get("/{cohort_id}/students")
def list_cohort_students(
    cohort_id: UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    """One row per student in the cohort. Per-course progress is the
    union of their enrollment rows in this cohort, summarized by
    course_id so the cohort overview can show a matrix."""
    cohort = _get_or_404(db, cohort_id)
    rows = (
        db.query(Enrollment)
        .filter(Enrollment.cohort_id == cohort.id)
        .order_by(Enrollment.user_id, Enrollment.course_id)
        .all()
    )
    by_user: dict[str, dict] = {}
    for e in rows:
        key = str(e.user_id)
        by_user.setdefault(
            key,
            {
                "user_id": key,
                "per_course": {},
            },
        )
        by_user[key]["per_course"][e.course_id] = {
            "enrollment_id": str(e.id),
            "enrolled_at": e.enrolled_at.isoformat() if e.enrolled_at else None,
            "progress": e.progress,
        }
    return list(by_user.values())


@router.post(
    "/{cohort_id}/students",
    status_code=status.HTTP_201_CREATED,
)
def add_student(
    cohort_id: UUID,
    body: CohortStudentAdd,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Add a student to the cohort. Resolves ``user_id`` (preferred) or
    ``email`` to an existing platform user, then auto-creates enrollment
    rows for every course already attached to this cohort. Idempotent —
    re-adding the same student is a no-op."""
    cohort = _get_or_404(db, cohort_id)
    if not body.user_id and not body.email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide user_id or email",
        )

    if body.user_id:
        user = db.query(User).filter(User.id == body.user_id).first()
    else:
        user = db.query(User).filter(User.email == body.email).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found — ask them to sign up first",
        )

    if cohort.max_students:
        current_count = _student_count(db, cohort.id)
        already_in = (
            db.query(Enrollment).filter(Enrollment.cohort_id == cohort.id, Enrollment.user_id == user.id).first()
            is not None
        )
        if not already_in and current_count >= cohort.max_students:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cohort has reached maximum capacity",
            )

    course_ids = _course_ids_for_cohort(db, cohort.id)
    for course_id in course_ids:
        already = (
            db.query(Enrollment)
            .filter(
                Enrollment.user_id == user.id,
                Enrollment.course_id == course_id,
                Enrollment.cohort_id == cohort.id,
            )
            .first()
        )
        if already is None:
            db.add(
                Enrollment(
                    id=f"enr-{cohort.id}-{user.id}-{course_id}",
                    user_id=user.id,
                    course_id=course_id,
                    cohort_id=cohort.id,
                )
            )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    return {"user_id": str(user.id), "course_ids": course_ids}


@router.delete(
    "/{cohort_id}/students/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_student(
    cohort_id: UUID,
    user_id: UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    """Remove a student from the cohort. Enrollment rows survive with
    ``cohort_id`` nulled so grades stay accessible."""
    cohort = _get_or_404(db, cohort_id)
    db.query(Enrollment).filter(Enrollment.cohort_id == cohort.id, Enrollment.user_id == user_id).update(
        {Enrollment.cohort_id: None}, synchronize_session=False
    )
    db.commit()


# -------------------------- public-ish read ---------------------------


@router.get("/course/{course_id}", response_model=list[CohortResponse])
def list_cohorts_for_course(
    response: Response,
    course_id: str,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> list[CohortResponse]:
    """Cohorts that include this course (junction-based). Used by:

    - Catalog course-detail page → cohort dropdown in the enroll dialog.
    - Teacher gradebook → filter dropdown for "show cohort X".

    Visibility: course must be ``published`` OR the viewer is its
    owner or an admin. Cohort name is localized via the translation
    overlay just like the legacy endpoint did."""
    response.headers["Vary"] = "Accept-Language"
    course = db.query(Course).filter(Course.id == course_id, Course.deleted_at.is_(None)).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    if course.status != "published":
        if not current_user or (
            str(course.created_by) != str(current_user.id) and current_user.role != UserRole.ADMIN.value
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    cohorts = (
        db.query(Cohort)
        .join(CohortCourse, Cohort.id == CohortCourse.cohort_id)
        .filter(CohortCourse.course_id == course_id)
        .order_by(Cohort.start_date.desc())
        .all()
    )
    if not cohorts:
        return []

    is_owner = current_user is not None and str(course.created_by) == str(current_user.id)
    is_admin = current_user is not None and current_user.role == UserRole.ADMIN.value
    if is_owner or is_admin:
        return [_serialize(db, c) for c in cohorts]

    display_locale: LocaleCode = normalize_locale(accept_language)
    source_locale: LocaleCode = normalize_locale(course.source_locale)
    overlay_specs = [("cohort", str(c.id), "title") for c in cohorts]
    overlay = fetch_overlay_triples_bulk(db, overlay_specs, display_locale)
    out: list[CohortResponse] = []
    for c in cohorts:
        localized = pick_overlay_value(
            overlay,
            "cohort",
            str(c.id),
            "title",
            c.name,
            source_locale=source_locale,
            display_locale=display_locale,
        )
        resp = _serialize(db, c)
        resp.name = localized or c.name
        out.append(resp)
    return out
