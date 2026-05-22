"""Quiz business logic.

Extracted from ``app/api/v1/quizzes.py`` so the router modules stay
thin. Anything that isn't strictly "parse HTTP, call a service,
serialize the response" lives here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.api.dependencies import resolve_chapter_course_id
from app.models.chapter_progress import ChapterProgress
from app.models.quiz import (
    Quiz,
    QuizAnswer,
    QuizAttempt,
    QuizExtraAttempt,
    QuizOption,
    QuizQuestion,
)
from app.schemas.quiz import QuizAnswerResult

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

AUTO_GRADED_QUESTION_TYPES = ("multiple_choice", "true_false")
MANUAL_GRADED_QUESTION_TYPES = ("short_answer", "essay")


def ensure_attempts_available(db: Session, quiz: Quiz, user_id: UUID) -> None:
    """Raise 403 if the student has used every allowed attempt on ``quiz``."""
    if quiz.max_attempts is None:
        return
    used_attempts = (
        db.query(QuizAttempt)
        .filter(
            QuizAttempt.quiz_id == quiz.id,
            QuizAttempt.user_id == user_id,
            QuizAttempt.completed_at.isnot(None),
        )
        .count()
    )
    extra = (
        db.query(QuizExtraAttempt)
        .filter(
            QuizExtraAttempt.quiz_id == quiz.id,
            QuizExtraAttempt.user_id == user_id,
        )
        .first()
    )
    total_allowed = quiz.max_attempts + (extra.extra_attempts if extra else 0)
    if used_attempts >= total_allowed:
        detail = "Exam attempts limit reached" if quiz.quiz_type == "exam" else "Maximum attempts reached"
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def index_quiz_options(
    quiz: Quiz,
) -> tuple[dict[str, QuizOption], dict[str, UUID]]:
    """Build ``{option_id: option}`` + ``{question_id: correct_option_id}`` maps.

    Options were already eager-loaded on ``quiz``, so this is just a
    fan-out over already-in-memory rows.
    """
    options_by_id: dict[str, QuizOption] = {}
    correct_option_map: dict[str, UUID] = {}
    for q in quiz.questions:
        for o in q.options:
            options_by_id[str(o.id)] = o
            if o.is_correct:
                correct_option_map[str(o.question_id)] = o.id
    return options_by_id, correct_option_map


def grade_auto_answer(
    question: QuizQuestion,
    selected_option_id: UUID | None,
    options_by_id: dict[str, QuizOption],
) -> tuple[bool, int]:
    """Return ``(is_correct, points_earned)`` for an auto-gradable answer."""
    if question.question_type not in AUTO_GRADED_QUESTION_TYPES or not selected_option_id:
        return False, 0
    option = options_by_id.get(str(selected_option_id))
    if option and option.question_id == question.id and option.is_correct:
        return True, int(question.points)
    return False, 0


def _add_answer_row(
    db: Session,
    *,
    attempt_id: UUID,
    question_id: UUID,
    selected_option_id: UUID | None,
    text_answer: str | None,
    is_correct: bool,
    points_earned: int,
    graded_at: datetime | None,
    correct_option_id: UUID | None,
) -> QuizAnswerResult:
    """Insert one ``QuizAnswer`` and return its matching ``QuizAnswerResult``.

    Both the "student submitted this" and "student skipped this"
    branches need to write a row with identical column shape and emit a
    response payload with identical column shape. This collapses the
    duplicate ORM/Pydantic construction down to one place so a future
    column addition only has to be made twice (model + schema) instead
    of four times (model + schema, x submitted, x skipped).
    """
    # Pre-generate the PK so we can build the result row without
    # round-tripping a flush per answer. ``submit_quiz`` commits once
    # at the end, which flushes everything.
    answer_id = uuid.uuid4()
    db.add(
        QuizAnswer(
            id=answer_id,
            attempt_id=attempt_id,
            question_id=question_id,
            selected_option_id=selected_option_id,
            text_answer=text_answer,
            is_correct=is_correct,
            points_earned=points_earned,
            graded_at=graded_at,
        )
    )
    return QuizAnswerResult(
        id=answer_id,
        question_id=question_id,
        selected_option_id=selected_option_id,
        text_answer=text_answer,
        is_correct=is_correct,
        points_earned=points_earned,
        correct_option_id=correct_option_id,
    )


def persist_answers(
    db: Session,
    attempt: QuizAttempt,
    quiz: Quiz,
    submitted: list,
    questions_map: dict[UUID, QuizQuestion],
    options_by_id: dict[str, QuizOption],
    correct_option_map: dict[str, UUID],
) -> tuple[int, list[QuizAnswerResult]]:
    """Write ``QuizAnswer`` rows for submitted AND unanswered questions.

    Returns ``(total_score, answer_results)``. Exam attempts do not leak
    the correct option back to the student.
    """
    show_correct = quiz.quiz_type != "exam"
    total_score = 0
    answer_results: list[QuizAnswerResult] = []
    answered: set[Any] = set()
    now = datetime.now(UTC)

    def correct_for(question_id: Any) -> UUID | None:
        return correct_option_map.get(str(question_id)) if show_correct else None

    for ans in submitted:
        question = questions_map.get(ans.question_id)
        if not question:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown question_id: {ans.question_id}",
            )
        answered.add(question.id)
        is_correct, points_earned = grade_auto_answer(question, ans.selected_option_id, options_by_id)
        total_score += points_earned
        # Auto-gradable answers are scored deterministically right now,
        # so they get ``graded_at`` stamped at submit. Open-ended
        # answers (essay / short_answer) keep ``graded_at = NULL`` until
        # a teacher hits PATCH /quizzes/answers/{id} — the pending
        # queue uses that NULL as its single source of truth for "this
        # answer still needs a human".
        auto_graded_at = now if question.question_type in AUTO_GRADED_QUESTION_TYPES else None
        answer_results.append(
            _add_answer_row(
                db,
                attempt_id=attempt.id,
                question_id=ans.question_id,
                selected_option_id=ans.selected_option_id,
                text_answer=ans.text_answer,
                is_correct=is_correct,
                points_earned=points_earned,
                graded_at=auto_graded_at,
                correct_option_id=correct_for(ans.question_id),
            )
        )

    # Record a zeroed answer for every question the student skipped. This
    # keeps ``max_score`` honest and makes the results screen render
    # every row, not just the ones the student touched.
    #
    # Auto-gradable skips are final at 0. Open-ended skips have no
    # ``text_answer`` so they never enter the pending queue (the query
    # requires ``text_answer IS NOT NULL``), but stamping ``graded_at``
    # for them too keeps ``graded_at IS NULL`` strictly equivalent to
    # "an essay/short_answer with text awaiting review".
    for q in quiz.questions:
        if q.id in answered:
            continue
        answer_results.append(
            _add_answer_row(
                db,
                attempt_id=attempt.id,
                question_id=q.id,
                selected_option_id=None,
                text_answer=None,
                is_correct=False,
                points_earned=0,
                graded_at=now,
                correct_option_id=correct_for(q.id),
            )
        )
    return total_score, answer_results


def upsert_passed_chapter_progress(db: Session, user_id: UUID, chapter_id: str) -> None:
    """Mark the chapter as ``quiz``-completed for the student (idempotent).

    Race-safe: a concurrent teacher-mark-complete or assignment-submit
    for the same ``(user, chapter)`` may also be inserting a progress
    row. We wrap the INSERT in a SAVEPOINT so the unique-constraint
    collision aborts only the savepoint — not the caller's transaction
    — and re-fetch the winner row to apply the "completed = true"
    update on top of it.
    """
    cp = (
        db.query(ChapterProgress)
        .filter(
            ChapterProgress.user_id == user_id,
            ChapterProgress.chapter_id == chapter_id,
        )
        .first()
    )
    if not cp:
        try:
            with db.begin_nested():
                cp = ChapterProgress(user_id=user_id, chapter_id=chapter_id)
                db.add(cp)
                db.flush()
        except IntegrityError:
            cp = (
                db.query(ChapterProgress)
                .filter(
                    ChapterProgress.user_id == user_id,
                    ChapterProgress.chapter_id == chapter_id,
                )
                .first()
            )
            if cp is None:
                raise
    if not cp.completed:
        cp.completed = True
        cp.completed_at = datetime.now(UTC)
        cp.completion_type = "quiz"


def recompute_attempt_grade(db: Session, attempt: QuizAttempt, quiz: Quiz) -> None:
    """Re-aggregate ``score`` / ``passed`` from the persisted answer rows.

    Called after every manual grade update so the attempt stays in sync
    without the teacher having to touch a "recompute" button. If
    ``passed`` flipped ``False`` → ``True`` the chapter is marked done
    and the enrollment progress is re-synced.
    """
    # Imported lazily to avoid a service ↔ service import cycle at module
    # load time.
    from app.services.course_service import sync_enrollment_progress

    rows = db.query(QuizAnswer).filter(QuizAnswer.attempt_id == attempt.id).all()
    attempt.score = sum(int(r.points_earned or 0) for r in rows)
    # ``max_score`` is already the full potential from submit(); we don't
    # recompute it here because question.points might legally change
    # later (rare) and we want the attempt to reflect the grading state,
    # not the current quiz definition.
    was_passed = bool(attempt.passed)
    max_score = int(attempt.max_score or 0)
    percentage = (attempt.score / max_score * 100) if max_score > 0 else 0
    attempt.passed = max_score > 0 and percentage >= quiz.passing_score

    if attempt.passed and not was_passed:
        upsert_passed_chapter_progress(db, attempt.user_id, str(quiz.chapter_id))
        course_id = resolve_chapter_course_id(db, quiz.chapter_id)
        sync_enrollment_progress(db, attempt.user_id, course_id)
