from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    lookup_enrollment,
    require_teacher,
    resolve_chapter_course_id,
    verify_chapter_access,
    verify_chapter_owner,
)
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.core.metrics import increment
from app.models.assignment import Assignment, AssignmentSubmission
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Course, Module
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
from app.services.content_versions import (
    delete_entity_cv_rows,
    dual_write_entity_content,
    fetch_cv_entity_texts_with_fallback,
)
from app.services.course_service import sync_enrollment_progress
from app.services.notification_service import create_notification
from app.services.translation.pipeline_hooks import reconcile_entity_if_course_published
from app.services.translation.resolve_for_display import (
    localize_assignment_rows,
    resolve_chapter_locale_context,
)

router = APIRouter(prefix="/assignments", tags=["assignments"])


_TRANSLATABLE_ASSIGNMENT_FIELDS = ("title", "description")


def _assignment_to_response(db: Session, assignment: Assignment, *, source_locale: str = "en") -> AssignmentResponse:
    """Phase 5e3: title + description columns dropped — pull both from
    cv (preferring source_locale, falling back to any active locale).
    Used by the single-entity routes (create / update); list / source
    routes use ``localize_assignment_rows`` which is locale-aware.
    """
    texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="assignment",
        entity_ids=[str(assignment.id)],
        fields=list(_TRANSLATABLE_ASSIGNMENT_FIELDS),
        display_locale=source_locale,
        source_locale=source_locale,
    )
    title = texts.get((str(assignment.id), "title")) or ""
    description = texts.get((str(assignment.id), "description"))
    return AssignmentResponse.model_validate(
        {
            "id": assignment.id,
            "chapter_id": assignment.chapter_id,
            "title": title,
            "description": description,
            "max_score": assignment.max_score,
            "due_date": assignment.due_date,
            "created_at": assignment.created_at,
            "updated_at": assignment.updated_at,
        }
    )


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
    # One chapter→module→course join covers the locale + access decisions
    # below.
    ctx = resolve_chapter_locale_context(db, chapter_id=chapter_id, current_user=current_user)
    if source:
        if not ctx.is_owner_or_admin:
            raise equip_error(
                ErrorCode.AUTH_FORBIDDEN,
                status_code=status.HTTP_403_FORBIDDEN,
                message="Only the course owner or an admin can request source-language content",
                context={"resource_type": "assignment", "chapter_id": chapter_id},
            )
        # Phase 5e3: title + description columns dropped — re-use the
        # localize path with display==source so the cv lookup populates
        # the source-locale text. ``prefer_human=True`` makes the
        # any-locale fallback skip MT rows so the editor never sees
        # machine output as the "source" text.
        return localize_assignment_rows(
            db, rows, display_locale=ctx.source_locale, source_locale=ctx.source_locale, prefer_human=True
        )
    display_locale: LocaleCode = normalize_locale(accept_language)
    return localize_assignment_rows(db, rows, display_locale=display_locale, source_locale=ctx.source_locale)


def _course_source_locale_for_chapter(db: Session, chapter_id: str) -> str | None:
    """Walk Assignment -> Chapter -> Module -> Course."""
    return (
        db.query(Course.source_locale)
        .join(Module, Module.course_id == Course.id)
        .join(Chapter, Chapter.module_id == Module.id)
        .filter(Chapter.id == chapter_id)
        .scalar()
    )


@router.post("", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
def create_assignment(
    data: AssignmentCreate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    verify_chapter_owner(db, data.chapter_id, teacher)
    # Phase 5e3: title + description go to cv; only structural fields
    # land on the Assignment row.
    payload = data.model_dump()
    title = payload.pop("title")
    description = payload.pop("description", None)
    assignment = Assignment(**payload)
    db.add(assignment)
    db.flush()
    source_locale = _course_source_locale_for_chapter(db, data.chapter_id)
    dual_write_entity_content(
        db,
        entity_type="assignment",
        entity_id=str(assignment.id),
        fallback_locale=source_locale,
        authored_by=teacher.id,
        texts={"title": title, "description": description},
    )
    db.commit()
    db.refresh(assignment)
    reconcile_entity_if_course_published(db, "assignment", assignment)
    return _assignment_to_response(db, assignment, source_locale=source_locale or "en")


@router.put("/{assignment_id}", response_model=AssignmentResponse)
def update_assignment(
    assignment_id: UUID,
    data: AssignmentUpdate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Assignment not found",
            context={"resource_type": "assignment", "resource_id": str(assignment_id)},
        )
    verify_chapter_owner(db, assignment.chapter_id, teacher)

    patch = data.model_dump(exclude_unset=True)
    # Phase 5e3: title + description live in cv. Pop them off the patch
    # so they don't try to setattr on the (now-text-less) ORM row.
    text_patch: dict[str, str | None] = {}
    if "title" in patch:
        text_patch["title"] = patch.pop("title")
    if "description" in patch:
        text_patch["description"] = patch.pop("description")
    for field, value in patch.items():
        setattr(assignment, field, value)

    db.flush()
    source_locale = _course_source_locale_for_chapter(db, assignment.chapter_id)
    if text_patch:
        dual_write_entity_content(
            db,
            entity_type="assignment",
            entity_id=str(assignment.id),
            fallback_locale=source_locale,
            authored_by=teacher.id,
            only_fields=set(text_patch.keys()),
            texts=text_patch,
        )
    db.commit()
    db.refresh(assignment)
    reconcile_entity_if_course_published(db, "assignment", assignment)
    return _assignment_to_response(db, assignment, source_locale=source_locale or "en")


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment(
    assignment_id: UUID,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Assignment not found",
            context={"resource_type": "assignment", "resource_id": str(assignment_id)},
        )
    verify_chapter_owner(db, assignment.chapter_id, teacher)
    # Phase 5ad: cv has no FK back; drop its rows explicitly.
    delete_entity_cv_rows(db, entity_type="assignment", entity_id=assignment.id)
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
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Assignment not found",
            context={"resource_type": "assignment", "resource_id": str(assignment_id)},
        )

    course_id = resolve_chapter_course_id(db, assignment.chapter_id)
    enrolled = lookup_enrollment(db, current_user.id, course_id)
    if not enrolled:
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="You must be enrolled in this course to submit assignments",
            context={"resource_type": "assignment", "assignment_id": str(assignment_id), "course_id": course_id},
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

    newly_completed = False
    if not progress.completed:
        progress.completed = True
        progress.completed_at = datetime.now(UTC)
        progress.completion_type = "self"
        newly_completed = True

    sync_enrollment_progress(db, current_user.id, course_id)
    db.commit()
    db.refresh(submission)
    if newly_completed:
        increment(
            "equip.engagement.chapter_completed_total",
            chapter_id=str(assignment.chapter_id),
            course_id=str(course_id),
            completion_type="assignment",
        )
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
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Assignment not found",
            context={"resource_type": "assignment", "resource_id": str(assignment_id)},
        )
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
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Assignment not found",
            context={"resource_type": "assignment", "resource_id": str(assignment_id)},
        )

    course_id = resolve_chapter_course_id(db, assignment.chapter_id)
    enrolled = lookup_enrollment(db, current_user.id, course_id)
    if not enrolled and current_user.role not in (UserRole.TEACHER.value, UserRole.ADMIN.value):
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Not enrolled in this course",
            context={"resource_type": "assignment", "assignment_id": str(assignment_id), "course_id": course_id},
        )

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
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Submission not found",
            context={"resource_type": "submission", "resource_id": str(submission_id)},
        )
    assignment = db.query(Assignment).filter(Assignment.id == submission.assignment_id).first()
    if not assignment:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Assignment not found",
            context={"resource_type": "assignment", "resource_id": str(submission.assignment_id)},
        )
    verify_chapter_owner(db, assignment.chapter_id, teacher)

    if data.grade > assignment.max_score:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            message=f"Grade ({data.grade}) cannot exceed max score ({assignment.max_score})",
            context={
                "resource_type": "submission",
                "submission_id": str(submission_id),
                "grade": data.grade,
                "max_score": assignment.max_score,
            },
        )

    submission.grade = data.grade
    submission.feedback = data.feedback
    submission.status = data.status
    submission.graded_by = teacher.id
    submission.graded_at = datetime.now(UTC)

    # Phase 5e3: assignment.title moved to cv — fetch the source-locale
    # title for the notification message (any locale fallback covers
    # edge cases where the source row hasn't been recorded yet).
    source_locale_for_msg = _course_source_locale_for_chapter(db, assignment.chapter_id) or "en"
    assignment_texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="assignment",
        entity_ids=[str(assignment.id)],
        fields=["title"],
        display_locale=source_locale_for_msg,
        source_locale=source_locale_for_msg,
    )
    assignment_title = assignment_texts.get((str(assignment.id), "title")) or "your assignment"
    create_notification(
        db,
        user_id=submission.student_id,
        type="assignment_graded",
        title="Assignment Graded",
        message=f'Your submission for "{assignment_title}" has been graded: {data.grade}/{assignment.max_score}.',
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
