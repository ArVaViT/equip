"""Quiz CRUD endpoints (teacher + student read-through).

Every route here attaches to the shared ``router`` in ``_router.py``.
"""

import uuid
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import (
    get_current_user,
    require_teacher,
    verify_chapter_access,
    verify_chapter_owner,
)
from app.core.database import get_db
from app.models.quiz import Quiz, QuizExtraAttempt, QuizOption, QuizQuestion
from app.models.user import User
from app.schemas.locale import LocaleCode, normalize_locale
from app.schemas.quiz import (
    QuizCreate,
    QuizResponse,
    QuizStudentResponse,
    QuizUpdate,
)
from app.services.translation.pipeline_hooks import (
    reconcile_entity_if_course_published,
    run_course_translation_pipeline_if_published,
)
from app.services.translation.resolve_for_display import (
    build_localized_quiz_student_response,
    resolve_chapter_locale_context,
)

from ._deps import verify_quiz_owner
from ._router import router


@router.get("/chapter/{chapter_id}", response_model=QuizStudentResponse | None)
def get_chapter_quiz(
    chapter_id: str,
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    source: bool = Query(
        False,
        description=(
            "Bypass the translation overlay and return source-language columns "
            "(``title``, ``description``, ``question_text``, ``option_text``). "
            "Owner / admin only — used by the quiz editor."
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    verify_chapter_access(db, chapter_id, current_user)
    response.headers["Vary"] = "Accept-Language"
    quiz = (
        db.query(Quiz)
        .options(selectinload(Quiz.questions).selectinload(QuizQuestion.options))
        .filter(Quiz.chapter_id == chapter_id)
        .first()
    )
    if not quiz:
        return None

    # One chapter→module→course join covers the locale + access decisions
    # below. Previously source=true paid 1 round-trip and source=false
    # paid 2, all to the same join.
    ctx = resolve_chapter_locale_context(db, chapter_id=chapter_id, current_user=current_user)
    if source:
        if not ctx.is_owner_or_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the course owner or an admin can request source-language content",
            )
        resp = QuizStudentResponse.model_validate(quiz)
    else:
        display_locale: LocaleCode = normalize_locale(accept_language)
        if ctx.apply_overlay:
            resp = build_localized_quiz_student_response(
                db, quiz, display_locale=display_locale, source_locale=ctx.source_locale
            )
        else:
            resp = QuizStudentResponse.model_validate(quiz)
    if resp.max_attempts is not None:
        extra = (
            db.query(QuizExtraAttempt)
            .filter(
                QuizExtraAttempt.quiz_id == quiz.id,
                QuizExtraAttempt.user_id == current_user.id,
            )
            .first()
        )
        if extra:
            resp.max_attempts = resp.max_attempts + extra.extra_attempts
    return resp


@router.get("/{quiz_id}", response_model=QuizResponse)
def get_quiz_detail(
    quiz_id: UUID,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    quiz = (
        db.query(Quiz)
        .options(selectinload(Quiz.questions).selectinload(QuizQuestion.options))
        .filter(Quiz.id == quiz_id)
        .first()
    )
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    verify_quiz_owner(db, quiz, teacher.id)
    return quiz


@router.post("", response_model=QuizResponse, status_code=status.HTTP_201_CREATED)
def create_quiz(
    data: QuizCreate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    _, course_id = verify_chapter_owner(db, data.chapter_id, teacher)
    max_attempts = data.max_attempts
    if data.quiz_type == "exam" and max_attempts is None:
        max_attempts = 1

    quiz_id_val = uuid.uuid4()
    quiz = Quiz(
        id=quiz_id_val,
        chapter_id=data.chapter_id,
        title=data.title,
        description=data.description,
        quiz_type=data.quiz_type,
        max_attempts=max_attempts,
        passing_score=data.passing_score,
    )
    db.add(quiz)

    for q_data in data.questions:
        question_id = uuid.uuid4()
        db.add(
            QuizQuestion(
                id=question_id,
                quiz_id=quiz_id_val,
                question_text=q_data.question_text,
                question_type=q_data.question_type,
                order_index=q_data.order_index,
                points=q_data.points,
                # ``min_words`` is only meaningful for ``essay``; it's
                # intentionally persisted as-is for every type so that
                # switching a question to ``essay`` later keeps the hint.
                min_words=q_data.min_words,
            )
        )
        for o_data in q_data.options:
            db.add(
                QuizOption(
                    question_id=question_id,
                    option_text=o_data.option_text,
                    is_correct=o_data.is_correct,
                    order_index=o_data.order_index,
                )
            )

    db.commit()
    reloaded = (
        db.query(Quiz)
        .options(selectinload(Quiz.questions).selectinload(QuizQuestion.options))
        .filter(Quiz.id == quiz_id_val)
        .first()
    )
    if reloaded is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    # Create flow seeds the quiz + every question + every option in one go.
    # Full-tree pipeline is cheaper here than N+1 per-entity reconcile calls
    # because the course gets loaded once and every child re-walks once.
    run_course_translation_pipeline_if_published(db, course_id)
    return reloaded


@router.put("/{quiz_id}", response_model=QuizResponse)
def update_quiz(
    quiz_id: UUID,
    data: QuizUpdate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    verify_quiz_owner(db, quiz, teacher.id)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(quiz, field, value)

    if quiz.quiz_type == "exam" and quiz.max_attempts is None:
        quiz.max_attempts = 1

    db.commit()
    reloaded = (
        db.query(Quiz)
        .options(selectinload(Quiz.questions).selectinload(QuizQuestion.options))
        .filter(Quiz.id == quiz.id)
        .first()
    )
    if reloaded is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    # ``update_quiz`` only mutates the quiz row itself; questions + options
    # have their own endpoints. Per-entity reconcile is enough.
    reconcile_entity_if_course_published(db, "quiz", reloaded)
    return reloaded


@router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quiz(
    quiz_id: UUID,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz not found")
    verify_quiz_owner(db, quiz, teacher.id)
    db.delete(quiz)
    db.commit()
    # No reconcile after delete — content_translations rows cascade via FK.
