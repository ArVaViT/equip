"""Quiz attempts: student submit + teacher/student attempt listing."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import (
    get_current_user,
    require_teacher,
    resolve_chapter_course_id,
    verify_chapter_access,
)
from app.core.database import get_db
from app.models.enrollment import Enrollment
from app.models.quiz import Quiz, QuizAttempt, QuizQuestion
from app.models.user import User
from app.schemas.quiz import QuizAttemptResponse, QuizSubmitRequest
from app.services import quiz_service
from app.services.course_service import sync_enrollment_progress

from ._deps import verify_quiz_owner
from ._router import router


@router.post(
    "/{quiz_id}/submit",
    response_model=QuizAttemptResponse,
    summary="Submit a quiz attempt (student)",
    responses={
        200: {"description": "Attempt persisted with per-answer feedback"},
        403: {
            "description": "Student is not enrolled, or has used all allowed attempts "
            "(``max_attempts`` + any ``quiz_extra_attempts`` grant)."
        },
        404: {"description": "Quiz not found"},
    },
)
def submit_quiz(
    quiz_id: UUID,
    data: QuizSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Submit one quiz attempt and persist the per-answer feedback.

    Concurrency: the ``Quiz`` row is locked ``FOR UPDATE`` so two
    parallel submits from the same student serialize on the lock —
    ``ensure_attempts_available`` re-counts inside the lock and the
    second request gets 403 if the first one consumed the last
    attempt.

    Scoring: auto-gradable question types (``multiple_choice``,
    ``true_false``) score immediately; manual types
    (``short_answer``, ``essay``) persist with ``points_earned = 0``
    and need a teacher to grade them later via
    ``PATCH /quizzes/answers/{answer_id}``. The returned ``passed``
    flag therefore stays ``False`` for any quiz with at least one
    manual question until the teacher grades enough of them to clear
    ``passing_score``. Exam attempts deliberately don't leak the
    ``correct_option_id`` back to the student.
    """
    quiz = (
        db.query(Quiz)
        .options(selectinload(Quiz.questions).selectinload(QuizQuestion.options))
        .filter(Quiz.id == quiz_id)
        .with_for_update()
        .first()
    )
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")

    course_id = resolve_chapter_course_id(db, quiz.chapter_id)
    enrolled = (
        db.query(Enrollment)
        .filter(
            Enrollment.user_id == current_user.id,
            Enrollment.course_id == course_id,
        )
        .first()
    )
    if not enrolled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You must be enrolled in this course to submit quizzes",
        )

    quiz_service.ensure_attempts_available(db, quiz, current_user.id)

    attempt = QuizAttempt(quiz_id=quiz_id, user_id=current_user.id)
    db.add(attempt)
    db.flush()

    questions_map: dict[UUID, QuizQuestion] = {q.id: q for q in quiz.questions}
    options_by_id, correct_option_map = quiz_service.index_quiz_options(quiz)
    # ``max_score`` is the full potential score including open-ended
    # questions so that students can't be auto-passed on half-graded
    # work (e.g. auto 4/4 on MCQ + pending 20-point essay would
    # otherwise report 100%). When the teacher later grades the essay
    # the ``passed`` flag is recomputed in ``grade_answer``.
    max_score = sum(q.points for q in quiz.questions)

    total_score, answer_results = quiz_service.persist_answers(
        db, attempt, quiz, data.answers, questions_map, options_by_id, correct_option_map
    )

    attempt.score = total_score
    attempt.max_score = max_score
    percentage = (total_score / max_score * 100) if max_score > 0 else 0
    # A quiz with only manual questions will have ``percentage == 0``
    # on submit and therefore will not auto-pass; ``passed`` stays
    # ``False`` until the teacher grades at least enough manual
    # answers to clear ``passing_score``.
    attempt.passed = max_score > 0 and percentage >= quiz.passing_score
    attempt.completed_at = datetime.now(UTC)

    if attempt.passed:
        quiz_service.upsert_passed_chapter_progress(db, current_user.id, str(quiz.chapter_id))
        sync_enrollment_progress(db, current_user.id, course_id)

    db.commit()
    db.refresh(attempt)
    assert attempt.started_at is not None

    return QuizAttemptResponse(
        id=attempt.id,
        quiz_id=attempt.quiz_id,
        user_id=attempt.user_id,
        score=attempt.score,
        max_score=attempt.max_score,
        passed=attempt.passed,
        started_at=attempt.started_at,
        completed_at=attempt.completed_at,
        answers=answer_results,
    )


@router.get("/{quiz_id}/attempts", response_model=list[QuizAttemptResponse])
def get_quiz_attempts(
    quiz_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    verify_quiz_owner(db, quiz, teacher.id)
    return (
        db.query(QuizAttempt)
        .options(selectinload(QuizAttempt.answers))
        .filter(QuizAttempt.quiz_id == quiz_id)
        .order_by(QuizAttempt.started_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@router.get("/{quiz_id}/my-attempts", response_model=list[QuizAttemptResponse])
def get_my_quiz_attempts(
    quiz_id: UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    verify_chapter_access(db, quiz.chapter_id, current_user)

    return (
        db.query(QuizAttempt)
        .options(selectinload(QuizAttempt.answers))
        .filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.user_id == current_user.id,
        )
        .order_by(QuizAttempt.started_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
