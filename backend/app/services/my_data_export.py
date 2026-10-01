"""Everything Equip keeps about a person, for that person to download.

A reader in Germany has the right to a copy of their data (GDPR Art. 15 and
20), and any reader is owed the plain answer to "what do you have on me?".
This gathers the rows that are *about* the caller — their profile, where
they enrolled, what they read, every test and answer, every piece of work
with its marks and feedback, certificates, reviews, the daily question,
notifications, and which legal documents they accepted — into one JSON
document.

Only the caller's own rows, filtered by their id on every table: nothing
another student wrote, and no course content beyond the ids it refers to.
Who marked a piece of work appears as the marker's id, as it does in the
caller's own views, not as their profile.

Deleting an account is not here: it is a separate decision with its own
consequences for certificates and grade sheets.
"""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import inspect

from app.models.assignment import AssignmentSubmission
from app.models.certificate import Certificate
from app.models.chapter_progress import ChapterProgress
from app.models.daily_challenge import DailyChallengeAttempt, DailyChallengeStreak
from app.models.enrollment import Enrollment
from app.models.grade_exemption import GradeExemption
from app.models.legal_acceptance import LegalAcceptance
from app.models.legal_notice_seen import LegalNoticeSeen
from app.models.notification import Notification
from app.models.quiz import QuizAnswer, QuizAttempt, QuizExtraAttempt
from app.models.review import CourseReview
from app.models.rubric import RubricMark
from app.models.student_grade import StudentGrade

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User

FORMAT_VERSION = 1


def _plain(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return (value if value.tzinfo else value.replace(tzinfo=UTC)).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, enum.Enum):
        return value.value
    return value


def _row(obj: Any) -> dict[str, Any]:
    """Every mapped column of a row, as JSON-ready values."""
    return {attr.key: _plain(getattr(obj, attr.key)) for attr in inspect(obj).mapper.column_attrs}


def _rows(objs: list[Any]) -> list[dict[str, Any]]:
    return [_row(o) for o in objs]


def export_my_data(db: Session, user: User, *, now: datetime | None = None) -> dict[str, Any]:
    uid = user.id
    attempts = db.query(QuizAttempt).filter(QuizAttempt.user_id == uid).all()
    attempt_ids = [a.id for a in attempts]
    submissions = db.query(AssignmentSubmission).filter(AssignmentSubmission.student_id == uid).all()
    submission_ids = [s.id for s in submissions]
    return {
        "format": "equip-my-data",
        "format_version": FORMAT_VERSION,
        "exported_at": _plain(now or datetime.now(UTC)),
        "profile": _row(user),
        "enrollments": _rows(db.query(Enrollment).filter(Enrollment.user_id == uid).all()),
        "lessons_completed": _rows(db.query(ChapterProgress).filter(ChapterProgress.user_id == uid).all()),
        "quiz_attempts": _rows(attempts),
        "quiz_answers": _rows(db.query(QuizAnswer).filter(QuizAnswer.attempt_id.in_(attempt_ids)).all())
        if attempt_ids
        else [],
        "quiz_extra_attempts": _rows(db.query(QuizExtraAttempt).filter(QuizExtraAttempt.user_id == uid).all()),
        "assignment_submissions": _rows(submissions),
        "rubric_marks": _rows(db.query(RubricMark).filter(RubricMark.submission_id.in_(submission_ids)).all())
        if submission_ids
        else [],
        "grades": _rows(db.query(StudentGrade).filter(StudentGrade.student_id == uid).all()),
        "grade_exemptions": _rows(db.query(GradeExemption).filter(GradeExemption.student_id == uid).all()),
        "certificates": _rows(db.query(Certificate).filter(Certificate.user_id == uid).all()),
        "course_reviews": _rows(db.query(CourseReview).filter(CourseReview.user_id == uid).all()),
        "daily_challenge_attempts": _rows(
            db.query(DailyChallengeAttempt).filter(DailyChallengeAttempt.user_id == uid).all()
        ),
        "daily_challenge_streak": _rows(
            db.query(DailyChallengeStreak).filter(DailyChallengeStreak.user_id == uid).all()
        ),
        "notifications": _rows(db.query(Notification).filter(Notification.user_id == uid).all()),
        "legal_acceptances": _rows(db.query(LegalAcceptance).filter(LegalAcceptance.user_id == uid).all()),
        "legal_notices_seen": _rows(db.query(LegalNoticeSeen).filter(LegalNoticeSeen.user_id == uid).all()),
    }
