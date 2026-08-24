"""Quiz CRUD endpoints (teacher + student read-through).

Every route here attaches to the shared ``router`` in ``_router.py``.
"""

import uuid
from uuid import UUID

from fastapi import Depends, Header, Query, Response, status
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import (
    get_current_user,
    require_teacher,
    verify_chapter_access,
    verify_chapter_owner,
)
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.course import Course
from app.models.quiz import Quiz, QuizExtraAttempt, QuizOption, QuizQuestion
from app.models.user import User
from app.schemas.locale import LocaleCode, normalize_locale
from app.schemas.quiz import (
    QuizCreate,
    QuizResponse,
    QuizStudentResponse,
    QuizUpdate,
)
from app.services.content_versions import (
    delete_entities_cv_rows,
    delete_entity_cv_rows,
    dual_write_entity_content,
)
from app.services.translation.pipeline_hooks import (
    reconcile_entity_if_course_published,
    run_course_translation_pipeline_if_published,
)
from app.services.translation.resolve_for_display import (
    build_localized_quiz_student_response,
    build_quiz_response_from_cv,
    resolve_chapter_locale_context,
)

from ._deps import course_source_locale_for_chapter, get_quiz_or_404, verify_quiz_owner
from ._router import router

_TRANSLATABLE_QUIZ_FIELDS = ("title", "description")
_TRANSLATABLE_QUESTION_FIELDS = ("question_text",)
_TRANSLATABLE_OPTION_FIELDS = ("option_text",)


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
    # below.
    ctx = resolve_chapter_locale_context(db, chapter_id=chapter_id, current_user=current_user)
    if source:
        if not ctx.is_owner_or_admin:
            raise equip_error(
                ErrorCode.AUTH_FORBIDDEN,
                status_code=status.HTTP_403_FORBIDDEN,
                message="Only the course owner or an admin can request source-language content",
                context={"resource_type": "quiz", "chapter_id": chapter_id},
            )
        # Title / question_text / option_text columns dropped.
        # The student response is the same shape source==display surfaces,
        # so re-use the localize path with display=source. ``prefer_human``
        # makes the any-locale fallback prefer human rows so the editor
        # never shows an MT row as authoritative source content.
        resp = build_localized_quiz_student_response(
            db, quiz, display_locale=ctx.source_locale, source_locale=ctx.source_locale, prefer_human=True
        )
    else:
        display_locale: LocaleCode = normalize_locale(accept_language)
        resp = build_localized_quiz_student_response(
            db, quiz, display_locale=display_locale, source_locale=ctx.source_locale
        )
        _refuse_untranslated_quiz(resp, quiz_id=str(quiz.id), locale=display_locale)
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


def _refuse_untranslated_quiz(resp: QuizStudentResponse, *, quiz_id: str, locale: str) -> None:
    """Do not hand a student a graded quiz they cannot read.

    Since the spare language was removed, a quiz with no rows in the
    reader's language resolves to empty strings — and empty strings
    render. The student would be shown a blank question with blank
    options, and this one is graded: they answer nothing and the
    attempt counts.

    The Daily Challenge takes the same position for the same reason
    (``daily_challenge.not_translated``). A missing translation is a
    wait, not a failure, and the reader is told which it is.
    """
    if not resp.questions:
        return
    unreadable = [
        q
        for q in resp.questions
        if not (q.question_text or "").strip() or any(not (o.option_text or "").strip() for o in q.options)
    ]
    if not unreadable:
        return
    raise equip_error(
        ErrorCode.QUIZ_NOT_TRANSLATED,
        status_code=status.HTTP_409_CONFLICT,
        message="This quiz is not available in your language yet",
        context={"resource_type": "quiz", "resource_id": quiz_id, "locale": locale},
    )


@router.get("/{quiz_id}", response_model=QuizResponse)
def get_quiz_detail(
    quiz_id: UUID,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    quiz = get_quiz_or_404(db, quiz_id, load_questions=True)
    verify_quiz_owner(db, quiz, teacher.id)
    return build_quiz_response_from_cv(
        db, quiz, source_locale=normalize_locale(course_source_locale_for_chapter(db, quiz.chapter_id))
    )


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

    # Two pass lines exist and they must not drift apart (D3):
    #
    #   quizzes.passing_score  — the chapter-completion gate, per quiz;
    #   courses.pass_threshold — the course result line.
    #
    # A quiz defaulting to a hardcoded 70 inside a course that passes at 80
    # produces the trap where a student clears every quiz, reaches progress
    # 100, and still cannot pass the course. New quizzes inherit the course's
    # line; a teacher who wants a different one says so explicitly.
    passing_score = data.passing_score
    if passing_score is None:
        course = db.query(Course).filter(Course.id == course_id).first()
        passing_score = int(course.pass_threshold) if course is not None else 70

    quiz_id_val = uuid.uuid4()
    quiz = Quiz(
        id=quiz_id_val,
        chapter_id=data.chapter_id,
        quiz_type=data.quiz_type,
        max_attempts=max_attempts,
        passing_score=passing_score,
    )
    db.add(quiz)

    questions_with_options: list[tuple[QuizQuestion, str, list[tuple[QuizOption, str]]]] = []
    for q_data in data.questions:
        question_id = uuid.uuid4()
        question = QuizQuestion(
            id=question_id,
            quiz_id=quiz_id_val,
            question_type=q_data.question_type,
            order_index=q_data.order_index,
            points=q_data.points,
            min_words=q_data.min_words,
        )
        db.add(question)
        question_options: list[tuple[QuizOption, str]] = []
        for o_data in q_data.options:
            opt = QuizOption(
                question_id=question_id,
                is_correct=o_data.is_correct,
                order_index=o_data.order_index,
            )
            db.add(opt)
            question_options.append((opt, o_data.option_text))
        questions_with_options.append((question, q_data.question_text, question_options))

    db.flush()
    fallback_locale = course_source_locale_for_chapter(db, data.chapter_id)
    dual_write_entity_content(
        db,
        entity_type="quiz",
        entity_id=str(quiz.id),
        fallback_locale=fallback_locale,
        authored_by=teacher.id,
        texts={"title": data.title, "description": data.description},
    )
    for question, q_text, options in questions_with_options:
        dual_write_entity_content(
            db,
            entity_type="quiz_question",
            entity_id=str(question.id),
            fallback_locale=fallback_locale,
            authored_by=teacher.id,
            texts={"question_text": q_text},
        )
        for opt, o_text in options:
            dual_write_entity_content(
                db,
                entity_type="quiz_option",
                entity_id=str(opt.id),
                fallback_locale=fallback_locale,
                authored_by=teacher.id,
                texts={"option_text": o_text},
            )
    db.commit()
    reloaded = get_quiz_or_404(db, quiz_id_val, load_questions=True)
    run_course_translation_pipeline_if_published(db, course_id)
    return build_quiz_response_from_cv(db, reloaded, source_locale=normalize_locale(fallback_locale))


@router.put("/{quiz_id}", response_model=QuizResponse)
def update_quiz(
    quiz_id: UUID,
    data: QuizUpdate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    quiz = get_quiz_or_404(db, quiz_id)
    verify_quiz_owner(db, quiz, teacher.id)

    patch = data.model_dump(exclude_unset=True)
    # Title + description live in cv. Pop them off the patch
    # so they don't try to setattr on the (now-text-less) ORM row.
    text_patch: dict[str, str | None] = {}
    if "title" in patch:
        text_patch["title"] = patch.pop("title")
    if "description" in patch:
        text_patch["description"] = patch.pop("description")
    for field, value in patch.items():
        setattr(quiz, field, value)

    if quiz.quiz_type == "exam" and quiz.max_attempts is None:
        quiz.max_attempts = 1

    db.flush()
    source_locale = course_source_locale_for_chapter(db, quiz.chapter_id)
    if text_patch:
        dual_write_entity_content(
            db,
            entity_type="quiz",
            entity_id=str(quiz.id),
            fallback_locale=source_locale,
            authored_by=teacher.id,
            only_fields=set(text_patch.keys()),
            texts=text_patch,
        )
    db.commit()
    reloaded = get_quiz_or_404(db, quiz.id, load_questions=True)
    reconcile_entity_if_course_published(db, "quiz", reloaded)
    return build_quiz_response_from_cv(db, reloaded, source_locale=normalize_locale(source_locale))


@router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_quiz(
    quiz_id: UUID,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    quiz = get_quiz_or_404(db, quiz_id, load_questions=True)
    verify_quiz_owner(db, quiz, teacher.id)
    # cv has no FK back; the quiz tree (quiz → questions →
    # options) is hard-deleted via cascade on the entity tables but
    # nothing cascades on cv. Drop the cv rows for every level
    # before db.delete(quiz) so the cascade leaves zero orphans.
    # Bulk IN-list deletes (one per entity type) instead of one DELETE
    # per row — a 50-question quiz used to issue 200+ statements here.
    delete_entities_cv_rows(
        db,
        entity_type="quiz_option",
        entity_ids=[option.id for question in quiz.questions for option in question.options],
    )
    delete_entities_cv_rows(
        db,
        entity_type="quiz_question",
        entity_ids=[question.id for question in quiz.questions],
    )
    delete_entity_cv_rows(db, entity_type="quiz", entity_id=quiz.id)
    db.delete(quiz)
    db.commit()
