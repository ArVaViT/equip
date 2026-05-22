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

from app.api.dependencies import get_current_user, require_teacher, verify_course_owner
from app.core.database import get_db
from app.models.course import Course
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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/grades", tags=["grades"])


@router.get("/course/{course_id}/config", response_model=GradingConfigResponse)
def get_grading_config(
    course_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    course = db.query(Course).filter(Course.id == course_id, Course.deleted_at.is_(None)).first()
    if not course:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")

    is_owner = str(course.created_by) == str(current_user.id)
    is_admin = current_user.role == UserRole.ADMIN.value
    is_enrolled = (
        db.query(Enrollment).filter(Enrollment.user_id == current_user.id, Enrollment.course_id == course_id).first()
        is not None
    )
    if not (is_owner or is_admin or is_enrolled):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

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

    enrolled = (
        db.query(Enrollment).filter(Enrollment.user_id == str(student_id), Enrollment.course_id == course_id).first()
    )
    if not enrolled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not enrolled in this course",
        )

    user = db.query(User).filter(User.id == str(student_id)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

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
        class_avg = round(sum(s.breakdown.final_score for s in students) / len(students), 2) if students else 0.0

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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Grade calculation failed",
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
        writer.writerow(
            [
                r["student_name"] or "",
                r["student_email"],
                b.quiz_avg,
                b.quiz_weighted,
                b.assignment_avg,
                b.assignment_weighted,
                b.participation_pct,
                b.participation_weighted,
                b.final_score,
                b.letter_grade,
                r["manual_grade"] or "",
            ]
        )

    buf.seek(0)
    # ASCII-only fallback for the legacy ``filename=`` header. ``c.isalnum``
    # accepts non-ASCII code points (e.g. Cyrillic letters), which then break
    # starlette's latin-1 header encoding, so we gate on ASCII explicitly.
    safe_title = "".join(c for c in course.title if c.isascii() and (c.isalnum() or c in " -_"))[:50].strip()
    if not safe_title:
        safe_title = str(course_id)[:8]
    ascii_filename = f"grades_{safe_title}.csv"
    utf8_filename = quote(f"grades_{course.title[:50].strip()}.csv", safe="")

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{utf8_filename}"),
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No grade found for course '{course_id}'",
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No grade found for student '{student_id}' in course '{course_id}'",
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

    enrolled = db.query(Enrollment).filter(Enrollment.user_id == student_id, Enrollment.course_id == course_id).first()
    if not enrolled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student is not enrolled in this course")

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
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Grade could not be saved due to a conflict; please retry.",
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
