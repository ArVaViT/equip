import csv
import io
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
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
from app.models.course import Chapter, CourseStatus, Module
from app.models.enrollment import Enrollment
from app.models.grade_exemption import GradeExemption
from app.models.quiz import Quiz
from app.models.student_grade import StudentGrade
from app.models.user import User, UserRole
from app.schemas.grade import (
    ExemptionCreate,
    ExemptionResponse,
    GradeResponse,
    GradeSummaryResponse,
    GradeUpsert,
    GradingConfigResponse,
    GradingConfigUpdate,
    GradingSchemeResponse,
    GradingSchemeUpdate,
    StudentCalculatedGrade,
    StudentGradeResponse,
)
from app.services.audit_service import log_action
from app.services.grade_calculator import (
    calculate_all_student_grades,
    calculate_student_grade_for_course,
)
from app.services.grade_exemption_service import apply_exemption, chapter_for_item, remove_exemption
from app.services.grade_override import (
    ACTION_CHANGED,
    ACTION_CLEARED,
    ACTION_SET,
    audit_override,
    resolve_official_row,
    validate_override,
)
from app.services.grading_scheme import effective_bands, get_org_settings, validate_scheme_threshold
from app.services.translation.resolve_for_display import populate_spine_texts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/grades", tags=["grades"])

#: What the grade column says in a CSV when there is no score. The export is
#: printed and filed without the screen that would otherwise explain it, so the
#: cell has to carry its own explanation.
#: What the grade column says in a CSV when there is no score.
#:
#: Deliberately neutral for ``completion_pass``. The screen renders «По
#: завершению» there rather than a pass, because the state describes the
#: *course* having nothing to grade — it says nothing about whether this
#: student did the work. Writing "Passed" into an exported sheet would award a
#: pass to someone who never opened a chapter, on the more official of the two
#: documents, and a teacher would sign it. The pass decision belongs to the
#: teacher reading the completion figure, not to the export.
_RESULT_STATE_CSV = {
    "completion_pass": "By completion — see Course Progress (%)",
    "not_graded_yet": "Not graded yet",
    "zero_weighted": "No percentage (graded work is weighted 0%)",
    # Not a pass and not a failure. Every item was excused, so the sheet has to
    # say that a person still owes this student a decision — the 100% in the
    # progress column beside it would otherwise read as a finished course.
    "not_assessed": "Not assessed — all work excused; needs a teacher's grade",
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


@router.get("/course/{course_id}/student/{student_id}/exemptions", response_model=list[ExemptionResponse])
def list_exemptions(
    course_id: str,
    student_id: str,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Work this student has been excused from."""
    verify_course_owner(db, course_id, teacher)
    return (
        db.query(GradeExemption)
        .filter(GradeExemption.course_id == course_id, GradeExemption.student_id == UUID(str(student_id)))
        .order_by(GradeExemption.created_at.desc())
        .all()
    )


@router.post(
    "/course/{course_id}/student/{student_id}/exemptions",
    response_model=ExemptionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_exemption(
    course_id: str,
    student_id: str,
    data: ExemptionCreate,
    request: Request,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Excuse a student from a piece of work — in the grade and the progress (D6).

    Both denominators, or neither. Removing the item from the grade alone
    leaves the chapter incomplete, so progress never reaches 100 and the
    certificate stays permanently out of reach — for exactly the student the
    exemption was meant to help.
    """
    verify_course_owner(db, course_id, teacher)

    student_uuid = UUID(str(student_id))
    if not lookup_enrollment(db, student_uuid, course_id):
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Student is not enrolled in this course",
            context={"resource_type": "enrollment", "student_id": student_id, "course_id": course_id},
        )

    if chapter_for_item(db, item_type=data.item_type, item_id=data.item_id, course_id=course_id) is None:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="No such quiz or assignment in this course",
            context={"resource_type": data.item_type, "resource_id": str(data.item_id)},
        )

    exemption = apply_exemption(
        db,
        student_id=student_uuid,
        course_id=course_id,
        item_type=data.item_type,
        item_id=data.item_id,
        teacher_id=teacher.id,
        reason=data.reason,
    )
    db.commit()
    db.refresh(exemption)

    log_action(
        db,
        user_id=teacher.id,
        action="grade_exemption_created",
        resource_type="grade_exemption",
        resource_id=str(exemption.id),
        details={
            "student_id": str(student_uuid),
            "course_id": course_id,
            "item_type": data.item_type,
            "item_id": str(data.item_id),
            "reason": data.reason,
        },
        request=request,
    )
    return exemption


@router.delete(
    "/course/{course_id}/student/{student_id}/exemptions/{item_type}/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_exemption(
    course_id: str,
    student_id: str,
    item_type: str,
    item_id: str,
    request: Request,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> None:
    """Take an exemption back, reverting only what it created."""
    verify_course_owner(db, course_id, teacher)

    removed = remove_exemption(
        db,
        student_id=UUID(str(student_id)),
        course_id=course_id,
        item_type=item_type,
        item_id=UUID(str(item_id)),
    )
    if removed is None:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="No such exemption",
            context={"resource_type": "grade_exemption", "student_id": student_id},
        )

    # Commit the removal before writing the trail. `log_action` rolls the
    # session back if the audit write fails, which here would have discarded the
    # deletion and the progress revert with it — and the route still returned
    # 204, telling the teacher the work was returned while both halves sat
    # untouched in the database. The create path already commits first.
    removed_id = str(removed.id)
    db.commit()

    log_action(
        db,
        user_id=teacher.id,
        action="grade_exemption_removed",
        resource_type="grade_exemption",
        resource_id=removed_id,
        details={
            "student_id": str(student_id),
            "course_id": course_id,
            "item_type": item_type,
            "item_id": str(item_id),
        },
        request=request,
    )


def _quizzes_off_the_course_line(db: Session, course_id: str, threshold: Decimal) -> list[dict[str, object]]:
    """Quizzes whose own pass line no longer matches the course's.

    Reported into the audit entry so the change is answerable later: "the line
    moved to 85 and these four quizzes stayed at 60" is the sentence a director
    needs, and nobody can reconstruct it after the fact.
    """
    rows = (
        db.query(Quiz.id, Quiz.chapter_id, Quiz.passing_score)
        .join(Chapter, Chapter.id == Quiz.chapter_id)
        .join(Module, Module.id == Chapter.module_id)
        .filter(
            Module.course_id == course_id,
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
            Quiz.passing_score != int(threshold),
        )
        .all()
    )
    return [{"quiz_id": str(r.id), "chapter_id": r.chapter_id, "passing_score": r.passing_score} for r in rows]


@router.get("/course/{course_id}/scheme", response_model=GradingSchemeResponse)
def get_grading_scheme(
    course_id: str,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """The course's scheme, pass line, and the bands they are read against."""
    course = verify_course_owner(db, course_id, teacher)
    settings = get_org_settings(db)
    scheme = course.grading_scheme or settings.default_grading_scheme
    return GradingSchemeResponse(
        grading_scheme=scheme,
        pass_threshold=course.pass_threshold,
        bands=effective_bands(settings, scheme),
    )


@router.put("/course/{course_id}/scheme", response_model=GradingSchemeResponse)
def update_grading_scheme(
    course_id: str,
    data: GradingSchemeUpdate,
    request: Request,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Change how a course is graded — both values at once, and audited (D8).

    Three rules, each earned:

    1. **The pair is validated together.** A scheme without its pass line can
       produce a course nobody can pass — five-point above 75 leaves «3»
       unreachable.
    2. **Existing hand-set grades block the change (409).** An «A» means
       nothing in a five-point course, and silently reinterpreting it would
       change a student's official result without anyone deciding to. The
       teacher clears or re-enters them first.
    3. **It is written down.** Changing the scheme changes what every grade in
       the course means; that is not a settings tweak, it is an academic
       decision someone should be able to point at later.
    """
    course = verify_course_owner(db, course_id, teacher)

    invalid = validate_scheme_threshold(data.grading_scheme, data.pass_threshold)
    if invalid:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message=invalid,
            context={"resource_type": "course", "resource_id": course_id},
        )

    previous_scheme = course.grading_scheme
    previous_threshold = course.pass_threshold

    if data.grading_scheme != previous_scheme:
        overrides = db.query(StudentGrade).filter(StudentGrade.course_id == course_id).all()
        if overrides:
            # Reinterpreting «A» as a five-point grade is not a conversion, it
            # is a guess about someone's result. Refuse and name the students,
            # so the teacher can decide deliberately.
            raise equip_error(
                ErrorCode.VALIDATION_FAILED,
                status_code=status.HTTP_409_CONFLICT,
                message=(
                    f"{len(overrides)} hand-set grade(s) exist under the {previous_scheme} scheme. "
                    "Clear or re-enter them before changing how this course is graded."
                ),
                context={
                    "resource_type": "course",
                    "resource_id": course_id,
                    "affected_students": [str(o.student_id) for o in overrides],
                },
            )

    course.grading_scheme = data.grading_scheme
    course.pass_threshold = data.pass_threshold

    # Quizzes carry their own pass line, inherited from the course's when they
    # were written (D3). Moving the course's leaves them where they were, and
    # the drift is invisible from here: raise the line and a student clears
    # every quiz, is congratulated each time, and still lands below the mark the
    # course grades them on — with every chapter green. Recorded rather than
    # silently rewritten, because a quiz threshold is a teacher's decision and
    # this endpoint is not the place to overrule it.
    drifted = _quizzes_off_the_course_line(db, course_id, data.pass_threshold)

    db.commit()
    db.refresh(course)

    log_action(
        db,
        user_id=teacher.id,
        action="grading_scheme_changed",
        resource_type="course",
        resource_id=course_id,
        details={
            "previous": {
                "grading_scheme": previous_scheme,
                "pass_threshold": float(previous_threshold) if previous_threshold is not None else None,
            },
            "new": {
                "grading_scheme": data.grading_scheme,
                "pass_threshold": float(data.pass_threshold),
            },
            "reason": data.reason,
            "quizzes_off_the_new_line": drifted,
        },
        request=request,
    )

    settings = get_org_settings(db)
    return GradingSchemeResponse(
        grading_scheme=course.grading_scheme,
        pass_threshold=course.pass_threshold,
        bands=effective_bands(settings, course.grading_scheme),
    )


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

    # Resolved by cohort, not by whichever row the database returns first —
    # a leftover cohort-less override must not outrank this term's (D7).
    official = resolve_official_row(db, student_id=str(student_id), course_id=course_id)
    manual = (
        None
        if official is None
        else (
            official.override_code
            if official.override_code is not None
            else (f"{official.override_score:.2f}" if official.override_score is not None else None)
        )
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

    # Course progress, straight from the enrolment. On a completion-only course
    # this is the *only* honest figure — «Participation (%)» is computed over
    # gradable chapters, and a course qualifies as completion-only precisely
    # because it has none, so that column is a structural zero there. Pointing
    # a teacher at a column that cannot be anything but zero is a different lie
    # from the one it replaced.
    progress_by_student = {
        str(user_id): progress
        for user_id, progress in db.query(Enrollment.user_id, Enrollment.progress)
        .filter(Enrollment.course_id == course.id)
        .all()
    }

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
            "Course Progress (%)",
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
                # Completion over *gradable* chapters — structurally zero on a
                # completion-only course, which is why the real progress figure
                # travels beside it.
                b.participation_pct,
                progress_by_student.get(r["student_id"], 0),
                b.final_score if graded else "—",
                b.letter_grade
                if graded
                # A course still being filled in must not certify anything.
                else (
                    "Course not filled in yet (no quiz or assignment saved)"
                    if b.result_state == "completion_pass" and b.has_gradable_chapters
                    else _RESULT_STATE_CSV[b.result_state]
                ),
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


@router.get("/my", response_model=list[StudentGradeResponse])
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


@router.get("/my/{course_id}", response_model=StudentGradeResponse)
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
    request: Request,
    cohort_id: str | None = Query(None, max_length=36),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> StudentGrade:
    """Set or change a hand-set grade (D7).

    The override wins over the computed grade wherever the official result is
    needed, so three things happen every time: the value is checked against the
    course's scheme, the computed score is snapshotted beside it, and the
    change is written to the audit log with what it replaced.
    """
    course = verify_course_owner(db, course_id, teacher)

    # The path gives strings; the columns are typed. Convert before any query
    # touches them, or the comparison fails deep in the driver with
    # "'str' object has no attribute 'hex'" and surfaces as a 503.
    try:
        student_uuid = UUID(str(student_id))
        cohort_uuid = UUID(cohort_id) if cohort_id else None
    except ValueError:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message="student_id and cohort_id must be UUIDs",
            context={"resource_type": "grade", "student_id": student_id},
        ) from None

    enrolled = lookup_enrollment(db, student_uuid, course_id)
    if not enrolled:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Student is not enrolled in this course",
            context={"resource_type": "enrollment", "student_id": student_id, "course_id": course_id},
        )

    invalid = validate_override(course, code=data.override_code, score=data.override_score)
    if invalid:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message=invalid,
            context={"resource_type": "grade", "course_id": course_id, "scheme": course.grading_scheme},
        )

    # What the system itself arrived at, recorded beside the hand-set value so
    # neither surface has to guess later what was overridden.
    computed = calculate_student_grade_for_course(db, course, student_uuid)
    computed_score = Decimal(str(computed.final_score)) if computed.result_state == "graded" else None

    query = db.query(StudentGrade).filter(
        StudentGrade.student_id == student_uuid,
        StudentGrade.course_id == course_id,
    )
    query = query.filter(
        StudentGrade.cohort_id == cohort_uuid if cohort_uuid is not None else StudentGrade.cohort_id.is_(None)
    )
    grade = query.first()

    if grade:
        previous = {
            "override_code": grade.override_code,
            "override_score": float(grade.override_score) if grade.override_score is not None else None,
            "graded_by": str(grade.graded_by) if grade.graded_by else None,
        }
        grade.override_code = data.override_code
        grade.override_score = data.override_score
        grade.computed_score = computed_score
        grade.reason = data.reason
        if data.comment is not None:
            grade.comment = data.comment
        grade.graded_by = teacher.id
        grade.graded_at = datetime.now(UTC)
        db.commit()
        db.refresh(grade)
        audit_override(
            db,
            actor_id=teacher.id,
            action=ACTION_CHANGED,
            row=grade,
            previous=previous,
            request=request,
        )
        return grade

    grade = StudentGrade(
        id=uuid.uuid4(),
        student_id=student_uuid,
        course_id=course_id,
        cohort_id=cohort_uuid,
        override_code=data.override_code,
        override_score=data.override_score,
        computed_score=computed_score,
        reason=data.reason,
        comment=data.comment,
        graded_by=teacher.id,
    )
    db.add(grade)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent upsert just inserted the same (student, course, cohort)
        # row. The unique index in migration 20260521172911 surfaces the race
        # as a clean IntegrityError instead of two duplicate rows. Re-read,
        # apply this caller's values on top of the winner, return that.
        db.rollback()
        existing_query = db.query(StudentGrade).filter(
            StudentGrade.student_id == student_uuid,
            StudentGrade.course_id == course_id,
        )
        existing_query = existing_query.filter(
            StudentGrade.cohort_id == cohort_uuid if cohort_uuid is not None else StudentGrade.cohort_id.is_(None)
        )
        existing = existing_query.first()
        if not existing:
            raise equip_error(
                ErrorCode.VALIDATION_FAILED,
                status_code=status.HTTP_409_CONFLICT,
                message="Grade could not be saved due to a conflict; please retry.",
                context={"resource_type": "grade", "student_id": student_id, "course_id": course_id},
            ) from None
        previous = {
            "override_code": existing.override_code,
            "override_score": float(existing.override_score) if existing.override_score is not None else None,
            "graded_by": str(existing.graded_by) if existing.graded_by else None,
        }
        existing.override_code = data.override_code
        existing.override_score = data.override_score
        existing.computed_score = computed_score
        existing.reason = data.reason
        if data.comment is not None:
            existing.comment = data.comment
        existing.graded_by = teacher.id
        existing.graded_at = datetime.now(UTC)
        db.commit()
        db.refresh(existing)
        audit_override(
            db,
            actor_id=teacher.id,
            action=ACTION_CHANGED,
            row=existing,
            previous=previous,
            request=request,
        )
        return existing
    db.refresh(grade)
    audit_override(db, actor_id=teacher.id, action=ACTION_SET, row=grade, request=request)
    return grade


@router.delete("/course/{course_id}/student/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def clear_student_grade(
    course_id: str,
    student_id: str,
    request: Request,
    cohort_id: str | None = Query(None, max_length=36),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> None:
    """Remove a hand-set grade and fall back to the computed one.

    There was no way to do this before. The old write path treated an omitted
    field as "leave it alone", so once a teacher had set an F nothing could
    take it back — and the typed CHECK makes "row with neither value" illegal
    anyway, so clearing has to be a deletion rather than an emptying.
    """
    verify_course_owner(db, course_id, teacher)

    try:
        student_uuid = UUID(str(student_id))
        cohort_uuid = UUID(cohort_id) if cohort_id else None
    except ValueError:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            message="student_id and cohort_id must be UUIDs",
            context={"resource_type": "grade", "student_id": student_id},
        ) from None

    query = db.query(StudentGrade).filter(
        StudentGrade.student_id == student_uuid,
        StudentGrade.course_id == course_id,
    )
    query = query.filter(
        StudentGrade.cohort_id == cohort_uuid if cohort_uuid is not None else StudentGrade.cohort_id.is_(None)
    )
    grade = query.first()
    if not grade:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="No hand-set grade to remove",
            context={"resource_type": "grade", "student_id": student_id, "course_id": course_id},
        )

    previous = {
        "override_code": grade.override_code,
        "override_score": float(grade.override_score) if grade.override_score is not None else None,
        "graded_by": str(grade.graded_by) if grade.graded_by else None,
        "reason": grade.reason,
    }
    # Audited before anything is removed: afterwards the values are gone.
    audit_override(
        db,
        actor_id=teacher.id,
        action=ACTION_CLEARED,
        row=grade,
        previous=previous,
        request=request,
    )

    # Clearing removes the *grade*, not the teacher's note to the student. A
    # comment written alongside it ("resubmit section 3") has nothing to do
    # with the override and must survive; the row goes only when nothing is
    # left on it.
    grade.override_code = None
    grade.override_score = None
    grade.computed_score = None
    grade.reason = None
    grade.graded_by = teacher.id
    grade.graded_at = datetime.now(UTC)
    if not grade.comment:
        db.delete(grade)
    db.commit()
