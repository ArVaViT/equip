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
from app.models.submission_declaration import SubmissionDeclaration
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
from app.services.content_versions import (
    delete_entity_cv_rows,
    dual_write_entity_content,
    fetch_cv_entity_texts_with_fallback,
)
from app.services.course_service import sync_enrollment_progress
from app.services.submission_grading import apply_grade
from app.services.translation.pipeline_hooks import reconcile_entity_if_course_published
from app.services.translation.resolve_for_display import (
    localize_assignment_rows,
    resolve_chapter_locale_context,
)
from app.services.zachet import latest_submissions

router = APIRouter(prefix="/assignments", tags=["assignments"])


_TRANSLATABLE_ASSIGNMENT_FIELDS = ("title", "description")


def _get_assignment_or_404(db: Session, assignment_id: UUID) -> Assignment:
    """Fetch an assignment or raise the canonical 404.

    Consolidates the fetch-or-404 boilerplate this module repeated at
    every ``{assignment_id}`` route. The error envelope (code / status /
    message / context) is byte-identical to the hand-written call sites
    it replaced, so the HTTP contract is unchanged.
    """
    assignment = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not assignment:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Assignment not found",
            context={"resource_type": "assignment", "resource_id": str(assignment_id)},
        )
    return assignment


def _assignment_to_response(db: Session, assignment: Assignment, *, source_locale: str = "en") -> AssignmentResponse:
    """Phase 5e3: title + description columns dropped — pull both from
    cv (preferring source_locale, falling back to any active locale).
    Used by the single-entity routes (create / update); list / source
    routes use ``localize_assignment_rows`` which is locale-aware.

    ``include_author_edits`` because these are the create/update routes:
    the teacher is being answered about the text they just sent, and on
    a published course that text is held back from readers until its
    translations arrive. Showing them the released version instead
    would read as a save that did nothing.
    """
    texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="assignment",
        entity_ids=[str(assignment.id)],
        fields=list(_TRANSLATABLE_ASSIGNMENT_FIELDS),
        display_locale=source_locale,
        source_locale=source_locale,
        include_author_edits=True,
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
    return localize_assignment_rows(
        db,
        rows,
        display_locale=display_locale,
        source_locale=ctx.source_locale,
        # The owner sees their own work whichever route they came in by.
        # They are not always on the ``?source=1`` editor path — the
        # course builder lists assignments through this one — and a
        # teacher who cannot see the assignment they just wrote will
        # write it again.
        include_author_edits=ctx.is_owner_or_admin,
    )


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
    assignment = _get_assignment_or_404(db, assignment_id)
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
    assignment = _get_assignment_or_404(db, assignment_id)
    verify_chapter_owner(db, assignment.chapter_id, teacher)
    # Phase 5ad: cv has no FK back; drop its rows explicitly.
    delete_entity_cv_rows(db, entity_type="assignment", entity_id=assignment.id)
    db.delete(assignment)
    db.commit()


def _refuse_if_already_marked(db: Session, assignment_id: UUID, student_id: UUID) -> None:
    """A marked piece of work is finished until a teacher says otherwise.

    ``returned`` is deliberately *not* a stop: handing work back for revision
    is the invitation to submit again, and it is the teacher who issued it.
    Only ``graded`` closes the door — and it closes it towards «запросить
    пересдачу», which is the door that opens it.
    """
    latest = latest_submissions(db, student_id=student_id, assignment_ids=[assignment_id]).get(assignment_id)
    if latest is None or latest["status"] != "graded":
        return
    raise equip_error(
        ErrorCode.VALIDATION_FAILED,
        status_code=status.HTTP_409_CONFLICT,
        message="This work has already been marked. Ask your teacher for a retake if you want another attempt.",
        context={
            "resource_type": "assignment",
            "assignment_id": str(assignment_id),
            "reason": "already_graded",
        },
    )


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
        409: {"description": "The work has already been marked; a retake is the teacher's to grant"},
    },
)
def submit_assignment(
    assignment_id: UUID,
    data: SubmissionCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit a response to an assignment.

    Resubmission is allowed right up until a teacher marks the work, and
    stops there. Once it is marked, the way back in is the teacher's —
    they return it for revision, or they grant a retake (D12).

    That boundary is the whole point. Before it, this route inserted a new
    submission unconditionally, and ``latest_submissions`` resolves the newest
    row as the one that counts — so a student marked 90 could press submit
    again and the 90 stopped being their grade: the item went back to
    «ждёт проверки», their итоговая fell (unmarked work counts as zero) and
    the certificate gate refused them. It was a free re-grade on demand, it
    let a student undo their own certificate by accident, and it put the last
    word with the student rather than the teacher — which every document this
    platform issues assumes is the other way round.

    The chapter-progress side effect runs on every submit so a student who
    resubmits before marking doesn't lose their "this chapter is done" badge.
    """
    assignment = _get_assignment_or_404(db, assignment_id)

    course_id = resolve_chapter_course_id(db, assignment.chapter_id)
    enrolled = lookup_enrollment(db, current_user.id, course_id)
    if not enrolled:
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="You must be enrolled in this course to submit assignments",
            context={"resource_type": "assignment", "assignment_id": str(assignment_id), "course_id": course_id},
        )

    _refuse_if_already_marked(db, assignment_id, current_user.id)

    course = db.query(Course).filter(Course.id == course_id).first()
    policy = (course.ai_policy if course else None) or "ai_with_disclosure"
    if policy != "ai_open" and data.declaration is None:
        # Required now that every client sends it (#971 shipped the screen a
        # release earlier for exactly this reason). A client that omits it is
        # refused rather than quietly recorded as having said nothing —
        # «nothing» is not a statement anybody made, and the whole value of the
        # declaration is that it was made about this specific piece of work.
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Confirm how this work was written before handing it in. Reload the page if you do not see the confirmation.",
            context={"resource_type": "assignment", "assignment_id": str(assignment_id), "ai_policy": policy},
        )

    submission = AssignmentSubmission(
        assignment_id=assignment_id,
        student_id=current_user.id,
        content=data.content,
        file_url=data.file_url,
    )
    db.add(submission)
    db.flush()

    if data.declaration is not None:
        # Recorded whatever it says. A student who declares they used AI where
        # the course forbids it is telling the truth about a rule they broke —
        # the work is accepted, the teacher sees it, and a person handles it.
        # Refusing at the door teaches the next student to tick the other box.
        db.add(
            SubmissionDeclaration(
                submission_id=submission.id,
                policy=policy,
                statement=data.declaration.statement
                + (f"\n\n{data.declaration.note}" if data.declaration.note else ""),
                ai_use=data.declaration.ai_use,
                ip=request.client.host if request and request.client else None,
            )
        )

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
    if progress.completed and progress.completion_type == "excused":
        # Excused, then submitted anyway. The work is real, so the row must say
        # so — otherwise lifting the exemption reopens a chapter the student
        # actually finished.
        progress.completion_type = "self"
        progress.completed_by = None
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
    assignment = _get_assignment_or_404(db, assignment_id)
    verify_chapter_owner(db, assignment.chapter_id, teacher)
    return (
        db.query(AssignmentSubmission)
        # Deactivated students keep their submission rows but drop out of
        # the teacher grading queue — same rule as the gradebook rosters
        # (#786).
        .join(User, User.id == AssignmentSubmission.student_id)
        .filter(
            AssignmentSubmission.assignment_id == assignment_id,
            User.deactivated_at.is_(None),
        )
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
    assignment = _get_assignment_or_404(db, assignment_id)

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
    assignment = _get_assignment_or_404(db, submission.assignment_id)
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

    apply_grade(
        db,
        submission=submission,
        assignment=assignment,
        grade=data.grade,
        feedback=data.feedback,
        new_status=data.status,
        teacher_id=teacher.id,
        source_locale=_course_source_locale_for_chapter(db, assignment.chapter_id),
        request=request,
    )
    return submission
