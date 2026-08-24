"""Teacher grading of open-ended quiz answers (and their pending queue)."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_teacher
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.core.metrics import increment, timing
from app.models.quiz import QuizAnswer, QuizAttempt, QuizQuestion
from app.models.user import User
from app.schemas.locale import normalize_locale
from app.schemas.quiz import (
    PendingAnswerInfo,
    QuizAnswerGradeRequest,
    QuizAnswerResult,
)
from app.services import quiz_service
from app.services.content_versions import fetch_cv_entity_texts_with_fallback

from ._deps import course_source_locale_for_chapter, get_quiz_or_404, verify_quiz_owner
from ._router import router


@router.get("/{quiz_id}/pending-answers", response_model=list[PendingAnswerInfo])
def list_pending_answers(
    quiz_id: UUID,
    response: Response,
    include_graded: bool = Query(
        False,
        description="If true, return already-graded open-ended answers too.",
    ),
    skip: int = Query(0, ge=0, description="Pagination offset."),
    limit: int = Query(
        200,
        ge=1,
        le=500,
        description="Max rows per page (caps response size; default 200, max 500).",
    ),
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Flat list of open-ended answers for the teacher's grading queue.

    Pagination is bounded — an essay-heavy course over a busy semester
    can accumulate thousands of pending answers, and the previous
    unbounded ``query.all()`` was an OOM hazard on a serverless worker.
    Defaults preserve the unpaginated shape for any existing client that
    omits the params.

    An answer is considered *pending* when ``graded_at IS NULL``.
    """
    quiz = get_quiz_or_404(db, quiz_id)
    verify_quiz_owner(db, quiz, teacher.id)

    query = (
        db.query(QuizAnswer, QuizQuestion, QuizAttempt, User)
        .join(QuizQuestion, QuizQuestion.id == QuizAnswer.question_id)
        .join(QuizAttempt, QuizAttempt.id == QuizAnswer.attempt_id)
        .join(User, User.id == QuizAttempt.user_id)
        .filter(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.completed_at.isnot(None),
            QuizQuestion.question_type.in_(quiz_service.MANUAL_GRADED_QUESTION_TYPES),
            QuizAnswer.text_answer.isnot(None),
            # Deactivated students keep their attempts but drop out of the
            # grading queue — same rule as the gradebook rosters (#786).
            User.deactivated_at.is_(None),
        )
        .order_by(QuizAttempt.completed_at.desc(), QuizQuestion.order_index.asc())
    )
    if not include_graded:
        # ``graded_at IS NULL`` is the authoritative "still pending"
        # signal. The previous heuristic ``(grader_comment IS NULL AND
        # points_earned == 0)`` silently kept rows in the queue when a
        # teacher legitimately graded an open-ended answer as 0 with no
        # comment — the row would re-appear on every page reload.
        query = query.filter(QuizAnswer.graded_at.is_(None))

    pending_rows = query.offset(skip).limit(limit).all()
    # ``quiz_questions.question_text`` column dropped — bulk-fetch
    # from cv for the rendering pass (any-locale fallback covers source-only
    # rows from a non-default course locale).
    question_ids = list({str(q.id) for _, q, _, _ in pending_rows})
    # The teacher's own language, like every other surface. This read was
    # pinned to English, so a German teacher marked German essays against
    # English questions — and where a course had no English at all, against
    # nothing. ``source_then_any`` because a marker has to be able to see the
    # question whatever language it exists in: showing them a blank would be
    # hiding the work they are being asked to judge.
    response.headers["Vary"] = "Accept-Language"
    question_texts = (
        fetch_cv_entity_texts_with_fallback(
            db,
            entity_type="quiz_question",
            entity_ids=question_ids,
            fields=["question_text"],
            display_locale=normalize_locale(accept_language or teacher.preferred_locale),
            source_locale=normalize_locale(course_source_locale_for_chapter(db, quiz.chapter_id)),
            fallback="source_then_any",
        )
        if question_ids
        else {}
    )

    results: list[PendingAnswerInfo] = []
    for answer, question, attempt, student in pending_rows:
        results.append(
            PendingAnswerInfo(
                answer_id=answer.id,
                attempt_id=attempt.id,
                question_id=question.id,
                question_text=question_texts.get((str(question.id), "question_text")) or "",
                question_type=question.question_type,
                max_points=int(question.points),
                min_words=question.min_words,
                text_answer=answer.text_answer,
                points_earned=int(answer.points_earned),
                grader_comment=answer.grader_comment,
                student_id=student.id,
                student_name=student.full_name,
                student_email=student.email,
                submitted_at=attempt.completed_at,
            )
        )
    return results


@router.patch("/answers/{answer_id}", response_model=QuizAnswerResult)
def grade_answer(
    answer_id: UUID,
    data: QuizAnswerGradeRequest,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Teacher grades a single open-ended answer.

    Rules:
    * The associated question must be ``short_answer`` or ``essay``;
      auto-graded answers cannot be edited (they're scored
      deterministically).
    * ``points_earned`` is clamped by the question's ``points`` cap.
    * On success we re-aggregate ``attempt.score`` + ``attempt.passed``
      and, if ``passed`` flipped from False → True, mark the chapter
      as ``quiz``-completed.
    """
    answer = db.query(QuizAnswer).filter(QuizAnswer.id == answer_id).first()
    if not answer:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Answer not found",
            context={"resource_type": "quiz_answer", "resource_id": str(answer_id)},
        )

    question = db.query(QuizQuestion).filter(QuizQuestion.id == answer.question_id).first()
    if not question:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Question not found",
            context={"resource_type": "quiz_question", "resource_id": str(answer.question_id)},
        )
    if question.question_type not in quiz_service.MANUAL_GRADED_QUESTION_TYPES:
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message="Only open-ended answers (short_answer / essay) can be graded manually",
            context={
                "resource_type": "quiz_answer",
                "answer_id": str(answer_id),
                "question_type": question.question_type,
            },
        )

    # ``FOR UPDATE`` on the attempt row so two teachers grading two
    # different answers from the same attempt serialize on the lock.
    # Without it, both teachers SELECT the attempt at the same score,
    # ``recompute_attempt_grade`` sums the answer rows from each one's
    # snapshot (missing the other's still-uncommitted update), and the
    # second commit overwrites the first with a stale total. SQLite
    # (test path) treats ``with_for_update`` as a no-op so single-test
    # behaviour is unchanged; Postgres takes a row lock that serializes
    # the recompute + write of ``attempt.score`` / ``attempt.passed``.
    attempt = db.query(QuizAttempt).filter(QuizAttempt.id == answer.attempt_id).with_for_update().first()
    if not attempt:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Attempt not found",
            context={"resource_type": "quiz_attempt", "resource_id": str(answer.attempt_id)},
        )

    quiz = get_quiz_or_404(db, attempt.quiz_id)
    verify_quiz_owner(db, quiz, teacher.id)

    if data.points_earned > int(question.points):
        raise equip_error(
            ErrorCode.VALIDATION_FAILED,
            status_code=status.HTTP_400_BAD_REQUEST,
            message=f"points_earned ({data.points_earned}) exceeds question cap ({question.points})",
            context={
                "resource_type": "quiz_answer",
                "answer_id": str(answer_id),
                "points_earned": data.points_earned,
                "max_points": int(question.points),
            },
        )

    answer.points_earned = data.points_earned
    answer.grader_comment = data.grader_comment
    # Flip ``is_correct`` to a ternary-ish flag that the UI can
    # interpret: ``True`` when the teacher awarded full credit,
    # ``False`` when they awarded zero, ``None`` for partial credit.
    if data.points_earned == int(question.points):
        answer.is_correct = True
    elif data.points_earned == 0:
        answer.is_correct = False
    else:
        answer.is_correct = None
    # Stamping ``graded_at`` is the one signal the pending-answer queue
    # consults. Re-grading the same row simply refreshes the timestamp.
    was_pending = answer.graded_at is None
    answer.graded_at = datetime.now(UTC)
    # The teacher's id was already here — it tags the throughput metric two
    # screens down — it just never reached the row that holds the judgement.
    answer.graded_by = teacher.id

    newly_completed_course_id = quiz_service.recompute_attempt_grade(db, attempt, quiz)
    db.commit()
    db.refresh(answer)

    # Emit the chapter-completion metric only AFTER commit, and only when this
    # re-grade actually flipped the chapter to complete (fail→pass) — pre-commit
    # emission double-counts on a rollback.
    if newly_completed_course_id is not None:
        increment(
            "equip.engagement.chapter_completed_total",
            chapter_id=str(quiz.chapter_id),
            course_id=newly_completed_course_id,
            completion_type="quiz",
        )

    # ``equip.grading.*`` metrics feed the Teacher Load dashboard.
    # Only counts the first time this answer transitioned out of the
    # pending state — re-grades don't double-count toward throughput.
    if was_pending:
        increment(
            "equip.grading.graded_total",
            teacher_id=str(teacher.id),
            quiz_id=str(quiz.id),
        )
        # ``attempt.completed_at`` is the closest signal we have to
        # "when the student submitted this answer" — QuizAnswer rows
        # share a single timestamp with the attempt as a whole.
        if attempt.completed_at is not None:
            time_to_grade_ms = (answer.graded_at - attempt.completed_at).total_seconds() * 1000.0
            timing(
                "equip.grading.time_to_grade.p50",
                time_to_grade_ms,
                teacher_id=str(teacher.id),
                quiz_id=str(quiz.id),
            )

    return QuizAnswerResult(
        id=answer.id,
        question_id=answer.question_id,
        selected_option_id=answer.selected_option_id,
        text_answer=answer.text_answer,
        is_correct=answer.is_correct,
        points_earned=int(answer.points_earned),
        grader_comment=answer.grader_comment,
        correct_option_id=None,
    )
