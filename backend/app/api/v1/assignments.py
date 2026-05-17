from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    require_teacher,
    resolve_chapter_course_id,
    verify_chapter_access,
    verify_chapter_owner,
)
from app.core.database import get_db
from app.models.assignment import Assignment, AssignmentSubmission
from app.models.chapter_progress import ChapterProgress
from app.models.enrollment import Enrollment
from app.models.user import User, UserRole
from app.schemas.assignment import (
    AssignmentCreate,
    AssignmentResponse,
    AssignmentUpdate,
    GradeSubmissionRequest,
    SubmissionCreate,
    SubmissionResponse,
)
from app.schemas.locale import LocaleCode, normalize_locale
from app.services.audit_service import log_action
from app.services.course_service import sync_enrollment_progress
from app.services.notification_service import create_notification
from app.services.translation.pipeline_hooks import reconcile_entity_if_course_published
from app.services.translation.resolve_for_display import (
    get_course_source_locale_for_chapter,
    is_chapter_course_owner_or_admin,
    localize_assignment_rows,
    should_apply_course_translation_overlay_for_chapter,
)

router = APIRouter(prefix="/assignments", tags=["assignments"])


@router.get("/chapter/{chapter_id}", response_model=list[AssignmentResponse])
def list_chapter_assignments(
    chapter_id: str,
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    source: bool = Query(
        False,
        description=(
            "Bypass the translation overlay and return source-language columns "
            "(``title``, ``description``). Owner / admin only — used by the "
            "assignment editor."
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    verify_chapter_access(db, chapter_id, current_user)
    response.headers["Vary"] = "Accept-Language"
    rows = db.query(Assignment).filter(Assignment.chapter_id == chapter_id).order_by(Assignment.created_at).all()
    if source:
        if not is_chapter_course_owner_or_admin(db, chapter_id=chapter_id, current_user=current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the course owner or an admin can request source-language content",
            )
        return rows
    display_locale: LocaleCode = normalize_locale(accept_language)
    src = get_course_source_locale_for_chapter(db, chapter_id)
    if should_apply_course_translation_overlay_for_chapter(db, chapter_id=chapter_id, current_user=current_user):
        return localize_assignment_rows(db, rows, display_locale=display_locale, source_locale=src)
    return rows


@router.post("", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
def create_assignment(
    data: AssignmentCreate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    verify_chapter_owner(db, data.chapter_id, teacher)
    assignment = Assignment(**data.model_dump())
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    reconcile_entity_if_course_published(db, "assignment", assignment)
    return assignment


@router.put("/{assignment_id}", response_model=AssignmentResponse)
def update_assignment(
    assignment_id: UUID,
    data: AssignmentUpdate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    verify_chapter_owner(db, assignment.chapter_id, teacher)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(assignment, field, value)

    db.commit()
    db.refresh(assignment)
    reconcile_entity_if_course_published(db, "assignment", assignment)
    return assignment


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment(
    assignment_id: UUID,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    verify_chapter_owner(db, assignment.chapter_id, teacher)
    db.delete(assignment)
    db.commit()


@router.post(
    "/{assignment_id}/submit",
    response_model=SubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Student submits an assignment response",
    responses={
        201: {
            "description": "Submission persisted in ``pending`` state; chapter "
            "progress flipped to completed; enrollment percent re-synced."
        },
        403: {"description": "Student is not enrolled in the assignment's course"},
        404: {"description": "Assignment not found"},
    },
)
def submit_assignment(
    assignment_id: UUID,
    data: SubmissionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a response to an assignment.

    Resubmissions are allowed (a student can submit multiple times
    before the teacher grades). The chapter-progress side effect runs
    on every submit so a student who later resubmits doesn't lose
    their "this chapter is done" badge. Grading then happens through
    ``grade_submission`` on the teacher side.
    """
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    course_id = resolve_chapter_course_id(db, assignment.chapter_id)
    enrolled = (
        db.query(Enrollment).filter(Enrollment.user_id == current_user.id, Enrollment.course_id == course_id).first()
    )
    if not enrolled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be enrolled in this course to submit assignments",
        )

    submission = AssignmentSubmission(
        assignment_id=assignment_id,
        student_id=current_user.id,
        content=data.content,
        file_url=data.file_url,
    )
    db.add(submission)

    progress = (
        db.query(ChapterProgress)
        .filter(
            ChapterProgress.user_id == current_user.id,
            ChapterProgress.chapter_id == assignment.chapter_id,
        )
        .first()
    )
    if not progress:
        # Insert the new ChapterProgress inside a SAVEPOINT so a
        # concurrent writer (teacher manually marking the chapter
        # complete at the same instant, or another resubmit) racing us
        # to the ``uq_progress_user_chapter`` unique key does not abort
        # the whole submit and lose the AssignmentSubmission row. On
        # collision we re-fetch the winner row and use it instead.
        # Mirrors the race fix in ``teacher_complete_chapter`` (#301).
        try:
            with db.begin_nested():
                progress = ChapterProgress(
                    user_id=current_user.id,
                    chapter_id=assignment.chapter_id,
                )
                db.add(progress)
                db.flush()
        except IntegrityError:
            progress = (
                db.query(ChapterProgress)
                .filter(
                    ChapterProgress.user_id == current_user.id,
                    ChapterProgress.chapter_id == assignment.chapter_id,
                )
                .first()
            )
            if progress is None:
                raise

    if not progress.completed:
        progress.completed = True
        progress.completed_at = datetime.now(UTC)
        progress.completion_type = "self"

    sync_enrollment_progress(db, current_user.id, course_id)
    db.commit()
    db.refresh(submission)
    return submission


@router.get("/{assignment_id}/submissions", response_model=list[SubmissionResponse])
def list_submissions(
    assignment_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    verify_chapter_owner(db, assignment.chapter_id, teacher)
    return (
        db.query(AssignmentSubmission)
        .filter(AssignmentSubmission.assignment_id == assignment_id)
        .order_by(AssignmentSubmission.submitted_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{assignment_id}/my-submissions", response_model=list[SubmissionResponse])
def list_my_submissions(
    assignment_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    course_id = resolve_chapter_course_id(db, assignment.chapter_id)
    enrolled = (
        db.query(Enrollment).filter(Enrollment.user_id == current_user.id, Enrollment.course_id == course_id).first()
    )
    if not enrolled and current_user.role not in (UserRole.TEACHER.value, UserRole.ADMIN.value):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enrolled in this course")

    # Same pagination envelope as the teacher-facing list above so
    # unbounded resubmission history cannot balloon the response.
    return (
        db.query(AssignmentSubmission)
        .filter(
            AssignmentSubmission.assignment_id == assignment_id,
            AssignmentSubmission.student_id == current_user.id,
        )
        .order_by(AssignmentSubmission.submitted_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.put("/submissions/{submission_id}/grade", response_model=SubmissionResponse)
def grade_submission(
    submission_id: UUID,
    data: GradeSubmissionRequest,
    request: Request,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    submission = db.query(AssignmentSubmission).filter(AssignmentSubmission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")
    assignment = db.query(Assignment).filter(Assignment.id == submission.assignment_id).first()
    if not assignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    verify_chapter_owner(db, assignment.chapter_id, teacher)

    if data.grade > assignment.max_score:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Grade ({data.grade}) cannot exceed max score ({assignment.max_score})",
        )

    submission.grade = data.grade
    submission.feedback = data.feedback
    submission.status = data.status
    submission.graded_by = teacher.id
    submission.graded_at = datetime.now(UTC)

    create_notification(
        db,
        user_id=submission.student_id,
        type="assignment_graded",
        title="Assignment Graded",
        message=f'Your submission for "{assignment.title}" has been graded: {data.grade}/{assignment.max_score}.',
        link=None,
        metadata={"assignment_id": str(assignment.id), "submission_id": str(submission.id)},
    )

    db.commit()
    db.refresh(submission)
    log_action(
        db,
        teacher.id,
        "grade",
        "assignment_submission",
        str(submission_id),
        details={"grade": data.grade, "status": data.status},
        request=request,
    )
    return submission
