import csv
import io
import logging
import uuid
from datetime import UTC, datetime
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    get_live_course_or_404,
    lookup_enrollment,
    require_teacher,
    verify_course_owner,
)
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.course import CourseStatus
from app.models.enrollment import Enrollment
from app.models.student_grade import StudentGrade
from app.models.user import User, UserRole
from app.schemas.grade import (
    GradeResponse,
    GradeSummaryResponse,
    GradeUpsert,
    GradingConfigResponse,
    GradingConfigUpdate,
    StudentCalculatedGrade,
)
from app.services.grade_calculator import (
    calculate_all_student_grades,
    calculate_student_grade_for_course,
)
from app.services.translation.resolve_for_display import populate_spine_texts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/grades", tags=["grades"])

#: What the grade column says in a CSV when there is no score. The export is
#: printed and filed without the screen that would otherwise explain it, so the
#: cell has to carry its own explanation.
_RESULT_STATE_CSV = {
    "completion_pass": "Passed on completion (course has no graded work)",
    "not_graded_yet": "Not graded yet",
    "zero_weighted": "No percentage (graded work is weighted 0%)",
}

# Spreadsheet apps (Excel / Google Sheets / LibreOffice) treat a cell that
# begins with =, +, -, @, or a leading tab/CR as a FORMULA. Student names and
# emails come from OAuth/profile data the user controls, so a name like
# ``=HYPERLINK("http://evil","click")`` would execute on open. Prefix any such
# cell with a single quote so it renders as literal text (CSV formula-injection
# guard).
_CSV_FORMULA_TRIGGERS = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: object) -> object:
    if isinstance(value, str) and value and value[0] in _CSV_FORMULA_TRIGGERS:
        return "'" + value
    return value


@router.get("/course/{course_id}/config", response_model=GradingConfigResponse)
def get_grading_config(
    course_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    course = get_live_course_or_404(db, course_id)

    is_owner = str(course.created_by) == str(current_user.id)
    is_admin = current_user.role == UserRole.ADMIN.value
    is_enrolled = (
        db.query(Enrollment).filter(Enrollment.user_id == current_user.id, Enrollment.course_id == course_id).first()
        is not None
    )
    if not (is_owner or is_admin or is_enrolled):
        # Mirror the catalog / PDF-export leak guard: an unpublished
        # course 404s to non-member probes so its existence doesn't leak;
        # published courses keep the plain 403.
        if course.status != CourseStatus.PUBLISHED:
            raise equip_error(
                ErrorCode.RESOURCE_NOT_FOUND,
                status_code=status.HTTP_404_NOT_FOUND,
                message="Course not found",
                context={"resource_type": "course", "resource_id": course_id},
            )
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Access denied",
            context={"resource_type": "grading_config", "course_id": course_id},
        )

    return GradingConfigResponse.model_validate(course)


@router.put("/course/{course_id}/config", response_model=GradingConfigResponse)
def update_grading_config(
    course_id: str,
    data: GradingConfigUpdate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    course = verify_course_owner(db, course_id, teacher)
    course.quiz_weight = data.quiz_weight
    course.assignment_weight = data.assignment_weight
    course.participation_weight = data.participation_weight
    db.commit()
    db.refresh(course)
    return GradingConfigResponse.model_validate(course)


@router.get(
    "/course/{course_id}/student/{student_id}/calculated",
    response_model=StudentCalculatedGrade,
)
def get_calculated_grade(
    course_id: str,
    student_id: UUID,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    course = verify_course_owner(db, course_id, teacher)

    enrolled = lookup_enrollment(db, str(student_id), course_id)
    if not enrolled:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Student not enrolled in this course",
            context={"resource_type": "enrollment", "student_id": str(student_id), "course_id": course_id},
        )

    user = db.query(User).filter(User.id == str(student_id)).first()
    if not user:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Student not found",
            context={"resource_type": "user", "resource_id": str(student_id)},
        )

    breakdown = calculate_student_grade_for_course(db, course, student_id)

    manual = (
        db.query(StudentGrade.grade)
        .filter(StudentGrade.course_id == course_id, StudentGrade.student_id == str(student_id))
        .scalar()
    )

    return StudentCalculatedGrade(
        student_id=str(student_id),
        student_name=user.full_name,
        student_email=user.email,
        breakdown=breakdown,
        manual_grade=manual,
    )


@router.get("/course/{course_id}/summary", response_model=GradeSummaryResponse)
def get_grade_summary(
    course_id: str,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    try:
        course = verify_course_owner(db, course_id, teacher)
        results = calculate_all_student_grades(db, course)

        students = [StudentCalculatedGrade(**r) for r in results]
        # A class average only means something when there are grades to average.
        # ``result_state`` is resolved course-wide, so one student answers for
        # all: on a completion-only or not-yet-graded course every final_score
        # is a placeholder zero, and averaging them prints "class average 0.0%"
        # in bold under a table of dashes — the single most alarming line a
        # teacher can open a gradebook to.
        gradable = [s for s in students if s.breakdown.result_state == "graded"]
        class_avg = round(sum(s.breakdown.final_score for s in gradable) / len(gradable), 2) if gradable else None

        return GradeSummaryResponse(
            course_id=course_id,
            config=GradingConfigResponse.model_validate(course),
            students=students,
            class_average=class_avg,
        )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logger.exception("Grade summary DB error for course %s", course_id)
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            message="Grade calculation failed",
            context={"resource_type": "grade_summary", "course_id": course_id},
        ) from exc


# ── CSV Export ────────────────────────────────────────────────────


@router.get("/course/{course_id}/export-csv")
def export_grades_csv(
    course_id: str,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    course = verify_course_owner(db, course_id, teacher)
    results = calculate_all_student_grades(db, course)

    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Student Name",
            "Email",
            "Quiz Avg (%)",
            "Quiz Weighted",
            "Assignment Avg (%)",
            "Assignment Weighted",
            "Participation (%)",
            "Participation Weighted",
            "Final Score",
            "Letter Grade",
            "Manual Grade",
        ]
    )
    for r in results:
        b = r["breakdown"]
        # A course with nothing graded has no numbers to export — not in the
        # final score, and not in the per-category columns either. Writing
        # zeros sends a spreadsheet to the school that reads as "everyone
        # scored zero", and a printed page has no banner to explain itself, so
        # the cells must say so themselves.
        graded = b.result_state == "graded"
        # Category averages are real in `zero_weighted` too — they simply carry
        # no weight. Only the final score is genuinely absent there.
        has_category_figures = graded or b.result_state == "zero_weighted"

        def num(value: float, *, show: bool = has_category_figures) -> float | str:
            return value if show else "—"

        writer.writerow(
            [
                _csv_safe(r["student_name"] or ""),
                _csv_safe(r["student_email"]),
                num(b.quiz_avg),
                num(b.quiz_weighted),
                num(b.assignment_avg),
                num(b.assignment_weighted),
                # Chapter completion is a real figure in every state — it is
                # the one number that still means something here.
                b.participation_pct,
                b.participation_weighted,
                b.final_score if graded else "—",
                b.letter_grade if graded else _RESULT_STATE_CSV[b.result_state],
                r["manual_grade"] or "",
            ]
        )

    buf.seek(0)
    # Phase 5g: course.title lives in cv now — fetch the source title for
    # the filename. Empty string is fine; the ascii fallback covers it.
    populate_spine_texts(db, [course])
    course_title = course.title or ""
    # ASCII-only fallback for the legacy ``filename=`` header. ``c.isalnum``
    # accepts non-ASCII code points (e.g. Cyrillic letters), which then break
    # starlette's latin-1 header encoding, so we gate on ASCII explicitly.
    safe_title = "".join(c for c in course_title if c.isascii() and (c.isalnum() or c in " -_"))[:50].strip()
    if not safe_title:
        safe_title = str(course_id)[:8]
    ascii_filename = f"grades_{safe_title}.csv"
    utf8_filename = quote(f"grades_{course_title[:50].strip()}.csv", safe="")

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{utf8_filename}"),
            # Filename is derived from the locale-resolved course title, so
            # an EN and RU caller see different downloads. Vary keeps the
            # HTTP cache layers from conflating them.
            "Vary": "Accept-Language",
        },
    )


# ── Existing Manual Grade Endpoints ───────────────────────────────


@router.get("/my", response_model=list[GradeResponse])
def list_my_grades(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[StudentGrade]:
    return (
        db.query(StudentGrade)
        .filter(StudentGrade.student_id == current_user.id)
        .order_by(StudentGrade.graded_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/my/{course_id}", response_model=GradeResponse)
def get_my_grade_for_course(
    course_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StudentGrade:
    grade = (
        db.query(StudentGrade)
        .filter(
            StudentGrade.student_id == current_user.id,
            StudentGrade.course_id == course_id,
        )
        .first()
    )
    if not grade:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"No grade found for course '{course_id}'",
            context={"resource_type": "grade", "course_id": course_id},
        )
    return grade


@router.get("/course/{course_id}", response_model=list[GradeResponse])
def list_course_grades(
    course_id: str,
    cohort_id: str | None = Query(None, max_length=36),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> list[StudentGrade]:
    verify_course_owner(db, course_id, teacher)
    query = db.query(StudentGrade).filter(StudentGrade.course_id == course_id)
    if cohort_id is not None:
        query = query.filter(StudentGrade.cohort_id == cohort_id)
    return query.order_by(StudentGrade.graded_at.desc()).offset(skip).limit(limit).all()


@router.get("/course/{course_id}/student/{student_id}", response_model=GradeResponse)
def get_student_grade(
    course_id: str,
    student_id: str,
    cohort_id: str | None = Query(None, max_length=36),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> StudentGrade:
    verify_course_owner(db, course_id, teacher)
    query = db.query(StudentGrade).filter(
        StudentGrade.student_id == student_id,
        StudentGrade.course_id == course_id,
    )
    if cohort_id is not None:
        query = query.filter(StudentGrade.cohort_id == cohort_id)
    grade = query.first()
    if not grade:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"No grade found for student '{student_id}' in course '{course_id}'",
            context={"resource_type": "grade", "student_id": student_id, "course_id": course_id},
        )
    return grade


@router.put("/course/{course_id}/student/{student_id}", response_model=GradeResponse)
def upsert_student_grade(
    course_id: str,
    student_id: str,
    data: GradeUpsert,
    cohort_id: str | None = Query(None, max_length=36),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> StudentGrade:
    verify_course_owner(db, course_id, teacher)

    enrolled = lookup_enrollment(db, student_id, course_id)
    if not enrolled:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Student is not enrolled in this course",
            context={"resource_type": "enrollment", "student_id": student_id, "course_id": course_id},
        )

    query = db.query(StudentGrade).filter(
        StudentGrade.student_id == student_id,
        StudentGrade.course_id == course_id,
    )
    if cohort_id is not None:
        query = query.filter(StudentGrade.cohort_id == cohort_id)
    grade = query.first()

    if grade:
        if data.grade is not None:
            grade.grade = data.grade
        if data.comment is not None:
            grade.comment = data.comment
        grade.graded_by = teacher.id
        grade.graded_at = datetime.now(UTC)
        db.commit()
        db.refresh(grade)
        return grade

    grade = StudentGrade(
        id=uuid.uuid4(),
        student_id=student_id,
        course_id=course_id,
        cohort_id=cohort_id,
        grade=data.grade,
        comment=data.comment,
        graded_by=teacher.id,
    )
    db.add(grade)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent upsert just inserted the same (student, course,
        # cohort) row. The unique index in migration
        # ``20260521172911_student_grades_unique_constraint`` is what
        # surfaces the race as a clean IntegrityError instead of two
        # duplicate rows. Re-read, apply the caller's update on top of
        # the winner, return that.
        db.rollback()
        existing_query = db.query(StudentGrade).filter(
            StudentGrade.student_id == student_id,
            StudentGrade.course_id == course_id,
        )
        if cohort_id is not None:
            existing_query = existing_query.filter(StudentGrade.cohort_id == cohort_id)
        else:
            existing_query = existing_query.filter(StudentGrade.cohort_id.is_(None))
        existing = existing_query.first()
        if not existing:
            # IntegrityError without a matching row means a different
            # constraint fired (FK violation, etc). Surface a clean 409
            # instead of leaking via the generic SQLAlchemy 503 handler.
            raise equip_error(
                ErrorCode.VALIDATION_FAILED,
                status_code=status.HTTP_409_CONFLICT,
                message="Grade could not be saved due to a conflict; please retry.",
                context={"resource_type": "grade", "student_id": student_id, "course_id": course_id},
            ) from None
        if data.grade is not None:
            existing.grade = data.grade
        if data.comment is not None:
            existing.comment = data.comment
        existing.graded_by = teacher.id
        existing.graded_at = datetime.now(UTC)
        db.commit()
        db.refresh(existing)
        return existing
    db.refresh(grade)
    return grade
