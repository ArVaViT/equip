"""Editing a question a class has already seen.

Until now a quiz was immutable below its own title: ``POST /quizzes``
took the whole tree at once, ``PUT /{quiz_id}`` reached the title, type,
attempt cap and pass mark, and nothing reached a question or an option.
A teacher who spotted a typo in a question had exactly one route —
delete the quiz and build it again — and ``ON DELETE CASCADE`` takes
``quiz_attempts`` with it. Fixing one word cost every student's graded
work, which in a Bible school with a transcript is not a fix at all.

What an edit here can and cannot disturb:

* **Wording, ordering, points, ``min_words``** are always allowed. A
  finished attempt stores its own ``score``/``max_score`` and each
  answer stores its own ``is_correct``/``points_earned``, so nothing
  already graded is re-scored by an edit. The next attempt uses the new
  wording, which is the point.
* **``is_correct``** is allowed for the same reason, and is how a
  teacher fixes an answer key that was wrong. Attempts already graded
  keep the verdict they were given; a teacher who wants them re-judged
  regrades them, which is a decision, not a side effect.
* **``question_type``** is refused once anybody has answered the
  question. An essay already written does not become a multiple choice,
  and the answer row would sit under a question it no longer fits.
* **The option list** is not editable as a list. Deleting an option
  nulls ``quiz_answers.selected_option_id`` (``ON DELETE SET NULL``) and
  the graded attempt stops saying what the student chose. Options are
  corrected, never added or removed, here.
* **The shape after the edit** must be one creation would accept. The
  per-row routes below checked nothing, so a question could be left with
  no right answer, two of them, or a choice type and no options at all
  (2026-10-03). The editor now saves a question whole
  (``PUT /quizzes/questions/{id}``: fields and every option in one
  request, validated together, applied in one transaction); the per-row
  routes stay for callers that send one field, and refuse (422) an edit
  that leaves the question unanswerable.

Edited text goes through the same path as every other authored string:
``dual_write_entity_content`` writes the source row, and
``reconcile_entity_if_course_published`` asks for the other languages —
so a corrected question does not sit in Russian while the German class
reads the old one.
"""

from uuid import UUID

from fastapi import Depends, status
from fastapi.exceptions import RequestValidationError
from pydantic_core import PydanticCustomError
from sqlalchemy.orm import Session, selectinload

from app.api.dependencies import require_teacher
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.quiz import QuizAnswer, QuizOption, QuizQuestion
from app.models.user import User
from app.schemas.locale import normalize_locale
from app.schemas.quiz import (
    QuizOptionUpdate,
    QuizQuestionSave,
    QuizQuestionUpdate,
    QuizResponse,
    validate_answerable,
)
from app.services.content_versions import dual_write_entity_content
from app.services.translation.pipeline_hooks import reconcile_entity_if_course_published
from app.services.translation.resolve_for_display import build_quiz_response_from_cv

from ._deps import course_source_locale_for_chapter, get_quiz_or_404, verify_quiz_owner
from ._router import router


def _question_or_404(db: Session, question_id: UUID) -> QuizQuestion:
    question = db.query(QuizQuestion).filter(QuizQuestion.id == question_id).first()
    if question is None:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"Quiz question '{question_id}' not found",
            context={"resource_type": "quiz_question", "resource_id": str(question_id)},
        )
    return question


def _answered(db: Session, question_id: UUID) -> bool:
    return db.query(QuizAnswer.id).filter(QuizAnswer.question_id == question_id).first() is not None


def _refuse_type_change_if_answered(db: Session, question: QuizQuestion, new_type: str | None) -> None:
    if new_type is None or new_type == question.question_type or not _answered(db, question.id):
        return
    raise equip_error(
        ErrorCode.QUIZ_QUESTION_ALREADY_ANSWERED,
        status_code=status.HTTP_409_CONFLICT,
        message=(
            "This question has already been answered, so its type cannot change. "
            "Wording, points and ordering can still be corrected; for a different "
            "kind of question, add a new one."
        ),
        context={
            "resource_type": "quiz_question",
            "resource_id": str(question.id),
            "current_type": question.question_type,
            "requested_type": new_type,
        },
    )


def _refuse_if_unanswerable(db: Session, question: QuizQuestion) -> None:
    """Undo a per-row edit that leaves the question in a shape creation refuses.

    Checked on the in-memory rows before anything is committed, and the
    session is rolled back on refusal, so the row the request touched is
    exactly as it was. The error is the same list pydantic would have
    produced at creation (``type`` is what the client translates), under
    the body's field so the reader is told «mark one option as correct»
    rather than shown a stack trace.
    """
    try:
        validate_answerable(question.question_type, question.options)
    except PydanticCustomError as exc:
        db.rollback()
        raise RequestValidationError(
            [
                {
                    "type": exc.type,
                    "loc": ("body", "options" if question.options else "question_type"),
                    "msg": exc.message(),
                    "input": None,
                    "ctx": exc.context or {},
                }
            ]
        ) from exc


def _quiz_response(db: Session, quiz_id: UUID) -> QuizResponse:
    """Reload the whole quiz the way create and update return it.

    One question edited in isolation would be a shape no other quiz
    route returns, and the caller almost always wants to re-render the
    quiz anyway.
    """
    reloaded = get_quiz_or_404(db, quiz_id, load_questions=True)
    source_locale = course_source_locale_for_chapter(db, reloaded.chapter_id)
    return build_quiz_response_from_cv(db, reloaded, source_locale=normalize_locale(source_locale))


@router.patch("/questions/{question_id}", response_model=QuizResponse)
def update_quiz_question(
    question_id: UUID,
    data: QuizQuestionUpdate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Correct one question in place, keeping every attempt on it."""
    question = _question_or_404(db, question_id)
    quiz = get_quiz_or_404(db, question.quiz_id)
    verify_quiz_owner(db, quiz, teacher.id)

    patch = data.model_dump(exclude_unset=True)
    text = patch.pop("question_text", None)
    _refuse_type_change_if_answered(db, question, patch.get("question_type"))

    for field, value in patch.items():
        setattr(question, field, value)
    _refuse_if_unanswerable(db, question)

    db.flush()
    if text is not None:
        source_locale = course_source_locale_for_chapter(db, quiz.chapter_id)
        dual_write_entity_content(
            db,
            entity_type="quiz_question",
            entity_id=str(question.id),
            fallback_locale=source_locale,
            authored_by=teacher.id,
            only_fields={"question_text"},
            texts={"question_text": text},
        )
    db.commit()

    db.refresh(question)
    reconcile_entity_if_course_published(db, "quiz_question", question)
    return _quiz_response(db, quiz.id)


@router.patch("/options/{option_id}", response_model=QuizResponse)
def update_quiz_option(
    option_id: UUID,
    data: QuizOptionUpdate,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Correct one answer option in place.

    Including the answer key: an option that was marked correct by
    mistake is fixed here rather than by rebuilding the quiz.
    """
    option = db.query(QuizOption).filter(QuizOption.id == option_id).first()
    if option is None:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"Quiz option '{option_id}' not found",
            context={"resource_type": "quiz_option", "resource_id": str(option_id)},
        )
    question = _question_or_404(db, option.question_id)
    quiz = get_quiz_or_404(db, question.quiz_id)
    verify_quiz_owner(db, quiz, teacher.id)

    patch = data.model_dump(exclude_unset=True)
    text = patch.pop("option_text", None)
    for field, value in patch.items():
        setattr(option, field, value)
    _refuse_if_unanswerable(db, question)

    db.flush()
    if text is not None:
        source_locale = course_source_locale_for_chapter(db, quiz.chapter_id)
        dual_write_entity_content(
            db,
            entity_type="quiz_option",
            entity_id=str(option.id),
            fallback_locale=source_locale,
            authored_by=teacher.id,
            only_fields={"option_text"},
            texts={"option_text": text},
        )
    db.commit()

    db.refresh(option)
    reconcile_entity_if_course_published(db, "quiz_option", option)
    return _quiz_response(db, quiz.id)


@router.put("/questions/{question_id}", response_model=QuizResponse)
def save_quiz_question(
    question_id: UUID,
    data: QuizQuestionSave,
    teacher: User = Depends(require_teacher),
    db: Session = Depends(get_db),
):
    """Save a question and all of its options in one request.

    The body is the question as it should read afterwards, validated the
    way creation validates it before a row is touched: so the right answer
    moves from one option to another in a single step, and there is no
    request in which the question has none. Option ids must be exactly
    the question's own — nothing is added or removed in place, which is
    what keeps every stored answer pointing at the option the student
    chose. A body whose option set differs from the server's is a stale
    editor (someone rebuilt the quiz meanwhile) and is refused with 409
    so it reloads rather than writes over the newer quiz.
    """
    question = (
        db.query(QuizQuestion)
        .options(selectinload(QuizQuestion.options))
        .filter(QuizQuestion.id == question_id)
        .first()
    )
    if question is None:
        raise equip_error(
            ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            message=f"Quiz question '{question_id}' not found",
            context={"resource_type": "quiz_question", "resource_id": str(question_id)},
        )
    quiz = get_quiz_or_404(db, question.quiz_id)
    verify_quiz_owner(db, quiz, teacher.id)

    stored = {option.id: option for option in question.options}
    sent = {option.id for option in data.options}
    if sent != set(stored):
        raise equip_error(
            ErrorCode.QUIZ_OPTIONS_CHANGED,
            status_code=status.HTTP_409_CONFLICT,
            message=(
                "The options sent are not this question's options: the quiz was changed "
                "elsewhere since it was loaded. Reload it; to change its shape, replace it."
            ),
            context={
                "resource_type": "quiz_question",
                "resource_id": str(question_id),
                "unknown_option_ids": sorted(str(i) for i in sent - set(stored)),
                "missing_option_ids": sorted(str(i) for i in set(stored) - sent),
            },
        )
    _refuse_type_change_if_answered(db, question, data.question_type)

    question.question_type = data.question_type
    question.order_index = data.order_index
    question.points = data.points
    question.min_words = data.min_words
    for sent_option in data.options:
        option = stored[sent_option.id]
        option.is_correct = sent_option.is_correct
        option.order_index = sent_option.order_index
    db.flush()

    # Text goes through the same path as every other authored string.
    # ``dual_write`` is idempotent on identical text, so sending the whole
    # question every time does not stack versions on unchanged rows.
    source_locale = course_source_locale_for_chapter(db, quiz.chapter_id)
    dual_write_entity_content(
        db,
        entity_type="quiz_question",
        entity_id=str(question.id),
        fallback_locale=source_locale,
        authored_by=teacher.id,
        only_fields={"question_text"},
        texts={"question_text": data.question_text},
    )
    for sent_option in data.options:
        dual_write_entity_content(
            db,
            entity_type="quiz_option",
            entity_id=str(sent_option.id),
            fallback_locale=source_locale,
            authored_by=teacher.id,
            only_fields={"option_text"},
            texts={"option_text": sent_option.option_text},
        )
    db.commit()

    db.refresh(question)
    reconcile_entity_if_course_published(db, "quiz_question", question)
    for option in question.options:
        reconcile_entity_if_course_published(db, "quiz_option", option)
    return _quiz_response(db, quiz.id)
