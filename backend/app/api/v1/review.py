"""The week's review: a few questions from tests a student took a while ago.

See ``services/review_questions.py`` for what is offered and why. Practice
only — nothing written, nothing graded.
"""

from __future__ import annotations

import uuid  # noqa: TC003

from fastapi import APIRouter, Depends, Header, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session  # noqa: TC002

from app.api.dependencies import get_current_user, get_live_course_or_404, lookup_enrollment
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.models.course import Course, CourseStatus
from app.models.enrollment import Enrollment
from app.models.quiz import QuizOption, QuizQuestion
from app.models.user import User  # noqa: TC001
from app.schemas.locale import normalize_locale
from app.services.review_questions import pick_review_questions, question_may_be_reviewed
from app.services.translation.resolve_for_display import fetch_course_titles_by_id

router = APIRouter(prefix="/review", tags=["review"])


class ReviewOptionOut(BaseModel):
    id: str
    option_text: str


class ReviewQuestionOut(BaseModel):
    id: str
    question_text: str
    options: list[ReviewOptionOut]


class ReviewWaiting(BaseModel):
    course_id: str
    #: In the reader's language; ``None`` when the course has no title in it.
    course_title: str | None
    count: int


class ReviewAnswer(BaseModel):
    question_id: uuid.UUID
    option_id: uuid.UUID


class ReviewVerdict(BaseModel):
    correct: bool
    correct_option_id: str


def _not_found() -> Exception:
    return equip_error(ErrorCode.RESOURCE_NOT_FOUND, status_code=status.HTTP_404_NOT_FOUND, message="Not found")


@router.get("/course/{course_id}", response_model=list[ReviewQuestionOut])
def this_weeks_review(
    course_id: str,
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ReviewQuestionOut]:
    course = get_live_course_or_404(db, course_id)
    if lookup_enrollment(db, current_user.id, course.id) is None:
        return []
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Accept-Language"
    picked = pick_review_questions(
        db,
        user_id=current_user.id,
        course_id=course.id,
        display_locale=normalize_locale(accept_language, fallback="en"),
        source_locale=course.source_locale or "en",
    )
    return [
        ReviewQuestionOut(
            id=q.id,
            question_text=q.question_text,
            options=[ReviewOptionOut(id=o.id, option_text=o.option_text) for o in q.options],
        )
        for q in picked
    ]


@router.get("/me", response_model=list[ReviewWaiting])
def reviews_waiting(
    response: Response,
    accept_language: str | None = Header(default=None, alias="Accept-Language"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ReviewWaiting]:
    """Which of the reader's courses have a review this week, and how long it is — for the home page."""
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Accept-Language"
    locale = normalize_locale(accept_language, fallback="en")
    courses = (
        db.query(Course)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .filter(
            Enrollment.user_id == current_user.id,
            Course.status == CourseStatus.PUBLISHED,
            Course.deleted_at.is_(None),
        )
        .distinct()
        .all()
    )
    waiting = []
    for course in courses:
        picked = pick_review_questions(
            db,
            user_id=current_user.id,
            course_id=course.id,
            display_locale=locale,
            source_locale=course.source_locale or "en",
        )
        if picked:
            waiting.append((course.id, len(picked)))
    titles = fetch_course_titles_by_id(db, [c for c, _ in waiting], display_locale=locale) if waiting else {}
    return [ReviewWaiting(course_id=c, course_title=titles.get(c) or None, count=n) for c, n in waiting]


@router.post("/check", response_model=ReviewVerdict)
def check_review_answer(
    answer: ReviewAnswer,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewVerdict:
    """Right or wrong, and which was right — only for a test the student has already completed."""
    question = db.get(QuizQuestion, answer.question_id)
    if question is None or not question_may_be_reviewed(db, current_user.id, question):
        raise _not_found()
    options = db.query(QuizOption).filter(QuizOption.question_id == question.id).all()
    right = [o for o in options if o.is_correct]
    if len(right) != 1 or answer.option_id not in {o.id for o in options}:
        raise _not_found()
    return ReviewVerdict(correct=right[0].id == answer.option_id, correct_option_id=str(right[0].id))
