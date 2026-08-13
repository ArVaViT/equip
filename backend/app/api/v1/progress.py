from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    lookup_enrollment,
    require_teacher,
    verify_chapter_owner,
    verify_course_owner,
)
from app.constants import GRADABLE_CHAPTER_TYPES
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.core.metrics import increment
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Module
from app.models.enrollment import Enrollment
from app.models.user import User
from app.services.audit_service import log_action
from app.services.course_service import sync_enrollment_progress
from app.services.domain_access import resolve_chapter_course_id
from app.services.student_progress_service import (
    build_course_gradebook_matrix,
    build_course_student_progress,
    build_student_chapter_detail,
)

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("/course/{course_id}/my-progress")
def get_my_chapter_progress(
    course_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enrolled = lookup_enrollment(db, current_user.id, course_id)
    if not enrolled:
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Not enrolled in this course",
            context={"resource_type": "progress", "course_id": course_id},
        )

    completed = (
        db.query(ChapterProgress.chapter_id)
        .join(Chapter, Chapter.id == ChapterProgress.chapter_id)
        .join(Module, Module.id == Chapter.module_id)
        .filter(
            Module.course_id == course_id,
            Module.deleted_at.is_(None),
            Chapter.deleted_at.is_(None),
            ChapterProgress.user_id == current_user.id,
            ChapterProgress.completed == True,
        )
        .all()
    )
    return [str(c[0]) for c in completed]


@router.get("/course/{course_id}/students")
def get_course_student_progress(
    course_id: str,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    course = verify_course_owner(db, course_id, teacher)
    return build_course_student_progress(db, course, course_id)


@router.get("/course/{course_id}/gradebook")
def get_course_gradebook_matrix(
    course_id: str,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Full students x chapters matrix for the gradebook spreadsheet.

    Separate from the slim ``/students`` list because the gradebook renders
    every student against every chapter at once, so it needs the per-chapter
    breakdown for the whole roster.
    """
    course = verify_course_owner(db, course_id, teacher)
    return build_course_gradebook_matrix(db, course, course_id)


@router.get("/course/{course_id}/students/{student_id}/detail")
def get_student_progress_detail(
    course_id: str,
    student_id: UUID,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Per-chapter breakdown + quiz/assignment results for ONE student.

    Backs the progress-board row expansion: the list endpoint returns only
    lightweight per-student summaries, so the heavy per-chapter detail is
    pulled lazily here when a teacher expands a row.
    """
    course = verify_course_owner(db, course_id, teacher)
    enrolled = db.query(Enrollment).filter(Enrollment.user_id == student_id, Enrollment.course_id == course_id).first()
    if not enrolled:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Student is not enrolled in this course",
            context={"resource_type": "enrollment", "course_id": course_id},
        )
    return build_student_chapter_detail(db, course, course_id, str(student_id))


@router.put("/chapter/{chapter_id}/read")
def mark_chapter_read(
    chapter_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The student says they have read this chapter.

    Reading is the core act of this product and, until now, the one act it did
    not record. Quizzes and assignments complete their chapters by being done;
    a reading chapter had no way to be finished at all, by anybody but a
    teacher marking it on the student's behalf.

    **Explicit, not inferred from scrolling.** A scroll heuristic guesses, and
    guesses wrongly in both directions — a student who skims to the bottom is
    credited, one who reads carefully on a phone and closes the tab is not.
    An explicit control is one request, it is honest, and it leaves the
    student deciding what they have read.

    Only non-gradable chapters: a quiz is finished by taking it, and letting a
    student declare it read would be a way around the work.
    """
    chapter = db.query(Chapter).filter(Chapter.id == chapter_id, Chapter.deleted_at.is_(None)).first()
    if chapter is None:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Chapter not found",
            context={"resource_type": "chapter", "chapter_id": chapter_id},
        )
    if chapter.chapter_type in GRADABLE_CHAPTER_TYPES:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="This chapter is finished by doing the work in it, not by marking it read.",
            context={"resource_type": "chapter", "chapter_id": chapter_id, "chapter_type": chapter.chapter_type},
        )

    course_id = resolve_chapter_course_id(db, chapter_id)
    enrolled = (
        db.query(Enrollment).filter(Enrollment.user_id == current_user.id, Enrollment.course_id == course_id).first()
    )
    if not enrolled:
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="You must be enrolled in this course",
            context={"resource_type": "progress", "course_id": course_id},
        )

    progress = (
        db.query(ChapterProgress)
        .filter(ChapterProgress.user_id == current_user.id, ChapterProgress.chapter_id == chapter_id)
        .first()
    )
    if progress is not None and progress.completed:
        # Idempotent: pressing it twice is the same statement made twice, and
        # the second press must not overwrite when it was first read.
        return {"chapter_id": chapter_id, "completed": True, "completed_at": progress.completed_at}

    if progress is None:
        progress = ChapterProgress(user_id=current_user.id, chapter_id=chapter_id)
        db.add(progress)
    progress.completed = True
    #: `self`, never `teacher` — the record has to say who decided, because a
    #: chapter a teacher ticked and one a student read are different facts.
    progress.completion_type = "self"
    progress.completed_at = datetime.now(UTC)
    db.commit()
    db.refresh(progress)
    return {"chapter_id": chapter_id, "completed": True, "completed_at": progress.completed_at}


@router.put("/chapter/{chapter_id}/student/{student_id}/complete")
def teacher_complete_chapter(
    chapter_id: str,
    student_id: UUID,
    request: Request,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    _chapter, course_id = verify_chapter_owner(db, chapter_id, teacher)

    enrolled = db.query(Enrollment).filter(Enrollment.user_id == student_id, Enrollment.course_id == course_id).first()
    if not enrolled:
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Student is not enrolled in this course",
            context={"resource_type": "progress"},
        )

    progress = (
        db.query(ChapterProgress)
        .filter(ChapterProgress.user_id == student_id, ChapterProgress.chapter_id == chapter_id)
        .first()
    )
    if progress and progress.completed:
        return {
            "message": "Already completed",
            "chapter_id": chapter_id,
            "student_id": str(student_id),
        }

    created_new = False
    if not progress:
        progress = ChapterProgress(
            user_id=student_id,
            chapter_id=chapter_id,
        )
        db.add(progress)
        created_new = True
    progress.completed = True
    progress.completed_at = datetime.now(UTC)
    progress.completed_by = teacher.id
    progress.completion_type = "teacher"
    sync_enrollment_progress(db, student_id, course_id)
    # Emit only AFTER a successful commit that actually flipped the row.
    # Emitting before commit double-counted: on the concurrent-completion
    # race below the loser rolls back but would already have fired the
    # metric, and the winner fires it too — two increments for one real
    # completion, contradicting the documented idempotency.
    committed_flip = False
    try:
        db.commit()
        committed_flip = True
    except IntegrityError:
        # Concurrent (teacher_complete + student-side autocomplete, or
        # two co-teachers clicking together) just committed a row for
        # the same (user, chapter). The unique constraint
        # ``uq_progress_user_chapter`` raises here; treat it as
        # idempotent rather than surfacing a 500.
        if not created_new:
            raise
        db.rollback()
        winner = (
            db.query(ChapterProgress)
            .filter(
                ChapterProgress.user_id == student_id,
                ChapterProgress.chapter_id == chapter_id,
            )
            .first()
        )
        if not winner:
            raise
        # If the winner is already complete just acknowledge it (no emit —
        # the request that flipped it already counted). If not, reapply
        # this teacher's intent — they explicitly asked for completion.
        if not winner.completed:
            winner.completed = True
            winner.completed_at = datetime.now(UTC)
            winner.completed_by = teacher.id
            winner.completion_type = "teacher"
            sync_enrollment_progress(db, student_id, course_id)
            db.commit()
            committed_flip = True
    if committed_flip:
        increment(
            "equip.engagement.chapter_completed_total",
            chapter_id=str(chapter_id),
            course_id=str(course_id),
            completion_type="teacher",
        )
        # `enrollment.progress` is the whole certificate gate, so marking every
        # gradable chapter complete by hand takes a student from nothing to
        # eligible. That is a bigger decision than editing a displayed grade,
        # which has been audited all along; until now the only trace of it was
        # `completed_by`, which the inverse route clears.
        log_action(
            db,
            user_id=teacher.id,
            action="chapter_completed_by_teacher",
            resource_type="chapter_progress",
            resource_id=str(chapter_id),
            details={"student_id": str(student_id), "course_id": str(course_id)},
            request=request,
        )
    return {
        "message": "Chapter marked as complete by teacher",
        "chapter_id": chapter_id,
        "student_id": str(student_id),
    }


@router.put("/chapter/{chapter_id}/student/{student_id}/incomplete")
def teacher_uncomplete_chapter(
    chapter_id: str,
    student_id: UUID,
    request: Request,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    _chapter, course_id = verify_chapter_owner(db, chapter_id, teacher)

    enrolled = db.query(Enrollment).filter(Enrollment.user_id == student_id, Enrollment.course_id == course_id).first()
    if not enrolled:
        raise equip_error(
            ErrorCode.AUTH_FORBIDDEN,
            status_code=status.HTTP_403_FORBIDDEN,
            message="Student is not enrolled in this course",
            context={"resource_type": "progress"},
        )

    progress = (
        db.query(ChapterProgress)
        .filter(ChapterProgress.user_id == student_id, ChapterProgress.chapter_id == chapter_id)
        .first()
    )
    if not progress or not progress.completed:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Chapter is not completed",
            context={"resource_type": "chapter_progress"},
        )
    if progress.completion_type == "excused":
        # An exemption holds the chapter and the grade together (D6). Undoing
        # the completion here would leave the work out of the grade while the
        # student's progress dropped below 100 — the certificate blocked and no
        # sign of why. The exemption is the thing to remove; it undoes both.
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_409_CONFLICT,
            message="This chapter is complete because the student was excused from the work. Remove the exemption instead.",
            context={"resource_type": "chapter_progress"},
        )
    progress.completed = False
    progress.completed_at = None
    progress.completed_by = None
    # Preserve whatever ``completion_type`` the row already had; the column
    # is NOT NULL in Postgres so we cannot clear it, and rewriting it to
    # ``"self"`` unconditionally destroys the signal of how the chapter
    # was originally completed (quiz/teacher/self).
    sync_enrollment_progress(db, student_id, course_id)
    db.commit()
    # Taking a completion back moves the same gate the other way, and it clears
    # `completed_by` on the way — so without this entry the record of who
    # granted it in the first place disappears with it.
    log_action(
        db,
        user_id=teacher.id,
        action="chapter_completion_removed_by_teacher",
        resource_type="chapter_progress",
        resource_id=str(chapter_id),
        details={"student_id": str(student_id), "course_id": str(course_id)},
        request=request,
    )
    return {
        "message": "Chapter completion removed",
        "chapter_id": chapter_id,
        "student_id": str(student_id),
    }
