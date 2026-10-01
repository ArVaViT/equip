"""A few questions from what a student finished a while ago — the week's review.

Bible knowledge is a matter of coming back to it. Once a week the course page
offers a handful of questions from tests the student took at least a week
ago, the ones they got wrong first. Practice only: nothing here is an
attempt, nothing reaches a grade.

What is never offered, and why:

* **An exam's questions** — an exam does not show its answers even after it
  is taken (``quiz_service``: ``show_correct``), and a review that checks
  answers would.
* **A test the student has not completed** — checking an answer reveals the
  right one; offered only where the results screen already did.
* **A question with no single right option** (open answers, or a broken one
  with none or two), or **without its text in the reader's language** —
  nobody is served a language they did not choose.

The set is chosen once per ISO week per student and course, so reopening the
page shows the same questions until Monday.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy.orm import selectinload

from app.models.course import Chapter
from app.models.quiz import Quiz, QuizAnswer, QuizAttempt, QuizQuestion
from app.services.content_versions import fetch_cv_entity_texts_with_fallback

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

REVIEW_SIZE = 5
#: Only material from at least this long ago: last week's test is not review.
REVIEW_AFTER = timedelta(days=7)
_CHOICE_TYPES = frozenset({"multiple_choice", "true_false"})


@dataclass(frozen=True)
class ReviewOption:
    id: str
    option_text: str


@dataclass(frozen=True)
class ReviewQuestion:
    id: str
    question_text: str
    options: tuple[ReviewOption, ...]


def _completed_quizzes(db: Session, user_id: uuid.UUID, course_id: str, *, before: datetime) -> dict[str, QuizAttempt]:
    """The student's latest completed attempt per ordinary (non-exam) quiz of the course, finished before ``before``."""
    rows = (
        db.query(QuizAttempt)
        .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
        .join(Chapter, Chapter.id == Quiz.chapter_id)
        .filter(
            QuizAttempt.user_id == user_id,
            QuizAttempt.completed_at.isnot(None),
            Chapter.course_id == course_id,
            Chapter.deleted_at.is_(None),
            Quiz.quiz_type == "quiz",
        )
        .all()
    )
    latest: dict[str, QuizAttempt] = {}
    for attempt in rows:
        key = str(attempt.quiz_id)
        if key not in latest or (attempt.completed_at or before) > (latest[key].completed_at or before):
            latest[key] = attempt
    return {
        quiz_id: a
        for quiz_id, a in latest.items()
        if a.completed_at is not None
        and (a.completed_at if a.completed_at.tzinfo else a.completed_at.replace(tzinfo=UTC)) <= before
    }


def question_may_be_reviewed(db: Session, user_id: uuid.UUID, question: QuizQuestion) -> bool:
    """Whether checking an answer to ``question`` reveals nothing new to this student."""
    quiz = db.get(Quiz, question.quiz_id)
    if quiz is None or quiz.quiz_type != "quiz":
        return False
    return (
        db.query(QuizAttempt.id)
        .filter(QuizAttempt.user_id == user_id, QuizAttempt.quiz_id == quiz.id, QuizAttempt.completed_at.isnot(None))
        .first()
        is not None
    )


def pick_review_questions(
    db: Session,
    *,
    user_id: uuid.UUID,
    course_id: str,
    display_locale: str,
    source_locale: str,
    now: datetime | None = None,
) -> list[ReviewQuestion]:
    moment = now or datetime.now(UTC)
    attempts = _completed_quizzes(db, user_id, course_id, before=moment - REVIEW_AFTER)
    if not attempts:
        return []
    questions = (
        db.query(QuizQuestion)
        .options(selectinload(QuizQuestion.options))
        .filter(QuizQuestion.quiz_id.in_([a.quiz_id for a in attempts.values()]))
        .all()
    )
    questions = [
        q for q in questions if q.question_type in _CHOICE_TYPES and sum(1 for o in q.options if o.is_correct) == 1
    ]
    if not questions:
        return []

    wrong = {
        str(question_id)
        for (question_id,) in db.query(QuizAnswer.question_id).filter(
            QuizAnswer.attempt_id.in_([a.id for a in attempts.values()]),
            QuizAnswer.is_correct.is_(False),
        )
    }
    question_texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="quiz_question",
        entity_ids=[str(q.id) for q in questions],
        fields=["question_text"],
        display_locale=display_locale,
        source_locale=source_locale,
        fallback="none",
    )
    option_texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type="quiz_option",
        entity_ids=[str(o.id) for q in questions for o in q.options],
        fields=["option_text"],
        display_locale=display_locale,
        source_locale=source_locale,
        fallback="none",
    )

    complete: list[ReviewQuestion] = []
    for q in questions:
        text = question_texts.get((str(q.id), "question_text"))
        options = [
            (o, option_texts.get((str(o.id), "option_text"))) for o in sorted(q.options, key=lambda o: o.order_index)
        ]
        if not text or any(not t for _, t in options):
            continue
        complete.append(
            ReviewQuestion(
                id=str(q.id),
                question_text=text,
                options=tuple(ReviewOption(id=str(o.id), option_text=t or "") for o, t in options),
            )
        )

    # Stable for the week: the same student and course see the same set
    # until Monday, wrong answers first.
    year, week, _ = moment.isocalendar()
    seed = hashlib.sha256(f"{user_id}:{course_id}:{year}-{week}".encode()).hexdigest()
    shuffled = sorted(complete, key=lambda q: hashlib.sha256(f"{seed}:{q.id}".encode()).hexdigest())
    shuffled.sort(key=lambda q: q.id not in wrong)
    picked = shuffled[:REVIEW_SIZE]
    # Options in a fresh order, so the right one is not always where it was.
    rng = random.Random(seed)  # ordering for practice, not security
    return [
        ReviewQuestion(id=q.id, question_text=q.question_text, options=tuple(rng.sample(q.options, len(q.options))))
        for q in picked
    ]
