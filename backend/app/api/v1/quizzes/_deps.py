from uuid import UUID

from fastapi import status
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import verify_chapter_owner
from app.core.errors import ErrorCode, equip_error
from app.models.quiz import Quiz, QuizQuestion


def verify_quiz_owner(db: Session, quiz: Quiz, teacher_id) -> None:
    """Teacher-owned-chapter check lifted into the `quizzes` package.

    Wraps ``verify_chapter_owner`` so callers don't need to reach into
    ``quiz.chapter_id`` each time.
    """
    verify_chapter_owner(db, quiz.chapter_id, teacher_id)


def get_quiz_or_404(
    db: Session,
    quiz_id: UUID,
    *,
    load_questions: bool = False,
    for_update: bool = False,
) -> Quiz:
    """Fetch a quiz or raise the canonical 404.

    Consolidates the quiz-fetch-or-404 boilerplate duplicated across the
    ``quizzes`` route modules. The error envelope (code / status /
    message / context) is byte-identical to the hand-written call sites
    it replaced, so the HTTP contract is unchanged.

    ``load_questions`` eager-loads ``questions`` → ``options`` (the
    shape the detail / delete / submit paths need); ``for_update`` adds
    ``FOR UPDATE`` so concurrent writers serialize on the row (SQLite,
    the test path, treats it as a no-op).
    """
    query = db.query(Quiz)
    if load_questions:
        query = query.options(selectinload(Quiz.questions).selectinload(QuizQuestion.options))
    query = query.filter(Quiz.id == quiz_id)
    if for_update:
        query = query.with_for_update()
    quiz = query.first()
    if not quiz:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message="Quiz not found",
            context={"resource_type": "quiz", "resource_id": str(quiz_id)},
        )
    return quiz
