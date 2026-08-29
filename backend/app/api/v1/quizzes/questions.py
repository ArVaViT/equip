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
  corrected one at a time.

Edited text goes through the same path as every other authored string:
``dual_write_entity_content`` writes the source row, and
``reconcile_entity_if_course_published`` asks for the other languages —
so a corrected question does not sit in Russian while the German class
reads the old one.
"""

from uuid import UUID

from fastapi import Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import require_teacher
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.quiz import QuizAnswer, QuizOption, QuizQuestion
from app.models.user import User
from app.schemas.locale import normalize_locale
from app.schemas.quiz import QuizOptionUpdate, QuizQuestionUpdate, QuizResponse
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

    new_type = patch.get("question_type")
    if new_type is not None and new_type != question.question_type and _answered(db, question_id):
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
                "resource_id": str(question_id),
                "current_type": question.question_type,
                "requested_type": new_type,
            },
        )

    for field, value in patch.items():
        setattr(question, field, value)

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
