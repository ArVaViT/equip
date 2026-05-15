from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_teacher, verify_chapter_owner, verify_course_owner
from app.core.database import get_db
from app.models.chapter_progress import ChapterProgress
from app.models.course import Chapter, Module
from app.models.enrollment import Enrollment
from app.models.user import User
from app.services.course_service import sync_enrollment_progress
from app.services.student_progress_service import build_course_student_progress

router = APIRouter(prefix="/progress", tags=["progress"])


@router.get("/course/{course_id}/my-progress")
def get_my_chapter_progress(
    course_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    enrolled = (
        db.query(Enrollment).filter(Enrollment.user_id == current_user.id, Enrollment.course_id == course_id).first()
    )
    if not enrolled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enrolled in this course",
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


@router.put("/chapter/{chapter_id}/student/{student_id}/complete")
def teacher_complete_chapter(
    chapter_id: str,
    student_id: UUID,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    _chapter, course_id = verify_chapter_owner(db, chapter_id, teacher)

    enrolled = db.query(Enrollment).filter(Enrollment.user_id == student_id, Enrollment.course_id == course_id).first()
    if not enrolled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student is not enrolled in this course",
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
    try:
        db.commit()
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
        # If the winner is already complete just acknowledge it. If
        # not (it raced but lost on a different field), reapply this
        # teacher's intent — they explicitly asked for completion.
        if not winner.completed:
            winner.completed = True
            winner.completed_at = datetime.now(UTC)
            winner.completed_by = teacher.id
            winner.completion_type = "teacher"
            sync_enrollment_progress(db, student_id, course_id)
            db.commit()
    return {
        "message": "Chapter marked as complete by teacher",
        "chapter_id": chapter_id,
        "student_id": str(student_id),
    }


@router.put("/chapter/{chapter_id}/student/{student_id}/incomplete")
def teacher_uncomplete_chapter(
    chapter_id: str,
    student_id: UUID,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    _chapter, course_id = verify_chapter_owner(db, chapter_id, teacher)

    enrolled = db.query(Enrollment).filter(Enrollment.user_id == student_id, Enrollment.course_id == course_id).first()
    if not enrolled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student is not enrolled in this course",
        )

    progress = (
        db.query(ChapterProgress)
        .filter(ChapterProgress.user_id == student_id, ChapterProgress.chapter_id == chapter_id)
        .first()
    )
    if not progress or not progress.completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Chapter is not completed",
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
    return {
        "message": "Chapter completion removed",
        "chapter_id": chapter_id,
        "student_id": str(student_id),
    }
