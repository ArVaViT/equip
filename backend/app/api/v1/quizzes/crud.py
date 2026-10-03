"""Quiz CRUD endpoints (teacher + student read-through).

Every route here attaches to the shared ``router`` in ``_router.py``.
"""

import uuid
from uuid import UUID

from fastapi import Depends, Header, Query, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import (
    get_current_user,
    require_teacher,
    verify_chapter_access,
    verify_chapter_owner,
)
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.chapter_block import ChapterBlock
from app.models.course import Course
from app.models.quiz import Quiz, QuizAttempt, QuizExtraAttempt, QuizOption, QuizQuestion
from app.models.user import User
from app.schemas.locale import LocaleCode, normalize_locale
from app.schemas.quiz import (
    QuizBody,
    QuizCreate,
    QuizEditorResponse,
    QuizReplace,
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
        source_resp = build_localized_quiz_student_response(
            db, quiz, display_locale=ctx.source_locale, source_locale=ctx.source_locale, prefer_human=True
        )
        # The owner edits the answer key too. Returned as a response of its
        # own: the route's ``response_model`` is the student shape and would
        # strip ``is_correct`` on the way out. No extra attempts either —
        # those are the reader's, and the editor shows the quiz's own limit.
        correct = {o.id: bool(o.is_correct) for q in quiz.questions for o in q.options}
        editor = QuizEditorResponse.model_validate(source_resp.model_dump())
        for question in editor.questions:
            for option in question.options:
                option.is_correct = correct.get(option.id, False)
        return JSONResponse(content=jsonable_encoder(editor), headers={"Vary": "Accept-Language"})
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


def _build_quiz_tree(
    db: Session,
    *,
    chapter_id: str,
    course_id: str,
    data: QuizBody,
    teacher: User,
) -> tuple[Quiz, str | None]:
    """Add the quiz, its questions and options, and their source text.

    Shared by create and replace so the two cannot drift: a replacement is
    a creation with the old quiz's chapter. Flushed, not committed — the
    caller decides what else belongs in the transaction. Returns the quiz
    and the course's source locale (the fallback the text was written with).
    """
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
        chapter_id=chapter_id,
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
    fallback_locale = course_source_locale_for_chapter(db, chapter_id)
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
    return quiz, fallback_locale


def _delete_quiz_tree(db: Session, quiz: Quiz) -> None:
    """Remove a quiz with its questions, options and their text. Not committed.

    cv has no FK back; the quiz tree (quiz → questions → options) is
    hard-deleted via cascade on the entity tables but nothing cascades on
    cv. Drop the cv rows for every level before db.delete(quiz) so the
    cascade leaves zero orphans. Bulk IN-list deletes (one per entity
    type) instead of one DELETE per row — a 50-question quiz used to issue
    200+ statements here. ``quiz.questions`` and their options must be
    loaded.
    """
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


def _refuse_unless_attempts_may_go(db: Session, quiz: Quiz, *, force: bool) -> None:
    """409 with the number of attempts unless the caller has seen it and said ``force``.

    ``quiz_attempts.quiz_id`` is ``ON DELETE CASCADE``: deleting the quiz
    deletes the class's graded work with it, and the editor used to do
    exactly that on every save — create the corrected quiz, delete the old
    one — so fixing a typo cost every attempt. Refuse unless the caller has
    seen the number and said so explicitly.
    """
    attempt_count = db.query(func.count(QuizAttempt.id)).filter(QuizAttempt.quiz_id == quiz.id).scalar() or 0
    if attempt_count and not force:
        raise equip_error(
            ErrorCode.QUIZ_HAS_ATTEMPTS,
            status_code=status.HTTP_409_CONFLICT,
            message=(
                f"This quiz has {attempt_count} attempt(s); deleting it would delete them all. "
                "Repeat with ?force=true to delete the quiz together with every attempt."
            ),
            context={"resource_type": "quiz", "resource_id": str(quiz.id), "attempt_count": attempt_count},
        )


@router.post("", response_model=QuizResponse, status_code=status.HTTP_201_CREATED)
def create_quiz(
    data: QuizCreate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    _, course_id = verify_chapter_owner(db, data.chapter_id, teacher)
    # One quiz per chapter is what every reader assumes: students are
    # handed the chapter's ``.first()`` quiz, the grade sheet counts every
    # quiz in the chapter. A second one was possible all the same, and the
    # editor's two-step rebuild left one behind whenever the delete was
    # refused (2026-10-03). Refused here, naming the quiz that exists; a
    # rebuild goes through ``POST /quizzes/{id}/replace``. The check is in
    # the application, not a unique index, so a chapter that already has
    # two keeps working until it is cleaned up by hand.
    existing_id = db.query(Quiz.id).filter(Quiz.chapter_id == data.chapter_id).scalar()
    if existing_id is not None:
        raise equip_error(
            ErrorCode.QUIZ_ALREADY_EXISTS,
            status_code=status.HTTP_409_CONFLICT,
            message="This chapter already has a quiz; edit it or replace it instead of adding a second one",
            context={
                "resource_type": "quiz",
                "chapter_id": data.chapter_id,
                "existing_quiz_id": str(existing_id),
            },
        )
    quiz, fallback_locale = _build_quiz_tree(
        db, chapter_id=data.chapter_id, course_id=course_id, data=data, teacher=teacher
    )
    db.commit()
    reloaded = get_quiz_or_404(db, quiz.id, load_questions=True)
    run_course_translation_pipeline_if_published(db, course_id)
    return build_quiz_response_from_cv(db, reloaded, source_locale=normalize_locale(fallback_locale))


@router.post("/{quiz_id}/replace", response_model=QuizResponse, status_code=status.HTTP_201_CREATED)
def replace_quiz(
    quiz_id: UUID,
    data: QuizReplace,
    force: bool = Query(
        False,
        description=(
            "Replace even though students have attempted the old quiz. Every attempt "
            "and grade on it goes with it; without this flag the request is refused "
            "with 409 and the number of attempts."
        ),
    ),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Put a new quiz in the old one's place, in one transaction.

    A quiz whose shape changed — a question or an option added or removed
    — cannot be corrected in place, because deleting an option blanks the
    answers that pointed at it. The editor rebuilt it as two requests,
    ``POST /quizzes`` then ``DELETE /quizzes/{old}``, and when the delete
    was refused (a student finished an attempt between the two) the
    chapter kept both quizzes: students were shown one, the grade sheet
    counted both (2026-10-03). Here the refusal comes first and nothing is
    written; otherwise the new quiz is built, every chapter block that
    pointed at the old quiz is pointed at the new one, and the old quiz
    goes — or none of it happens.
    """
    # ``FOR UPDATE``: a submit in flight holds the same row lock
    # (``attempts.py``), so the attempt count below and the delete at the
    # end sit on one side of that submit or the other — never counting
    # zero and then cascading away an attempt that committed in between.
    old = get_quiz_or_404(db, quiz_id, load_questions=True, for_update=True)
    _, course_id = verify_chapter_owner(db, old.chapter_id, teacher)
    _refuse_unless_attempts_may_go(db, old, force=force)

    chapter_id = old.chapter_id
    quiz, fallback_locale = _build_quiz_tree(db, chapter_id=chapter_id, course_id=course_id, data=data, teacher=teacher)
    # ``chapter_blocks.quiz_id`` is ``ON DELETE SET NULL``: left alone, the
    # lesson's quiz block would forget its quiz the moment the old one went.
    db.query(ChapterBlock).filter(ChapterBlock.quiz_id == old.id).update(
        {ChapterBlock.quiz_id: quiz.id}, synchronize_session=False
    )
    _delete_quiz_tree(db, old)
    db.commit()
    reloaded = get_quiz_or_404(db, quiz.id, load_questions=True)
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
    force: bool = Query(
        False,
        description=(
            "Delete even though students have attempted this quiz. Every attempt "
            "and grade on it goes with it; without this flag the request is "
            "refused with 409 and the number of attempts."
        ),
    ),
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    # Locked for the same reason as in ``replace_quiz``: the count and the
    # delete must not straddle a submit that is committing an attempt.
    quiz = get_quiz_or_404(db, quiz_id, load_questions=True, for_update=True)
    verify_quiz_owner(db, quiz, teacher.id)
    _refuse_unless_attempts_may_go(db, quiz, force=force)
    _delete_quiz_tree(db, quiz)
    db.commit()
