"""The "your work has an answer" email.

A teacher reading an essay is the one thing Equip does that the free
seminary-course sites do not, and until 2026-09-30 the student only found
out if they happened to open the app and look under the bell: 14 of 61
notifications in production had ever been read. This is the message that
reaches a student who is not in the app — the mark, or the fact that the
work came back for another draft, and one link to the lesson where the
feedback is.

Written in the student's language, like the notification beside it. No
gendered verbs in any language: the sentences are about the work ("has
been read and marked"), not about the teacher who did it.

Course mail of the kind ``work_returned``: it goes through
``course_mail.send_course_mail``, so the student can turn it off in the
profile or from the link at its foot, as the privacy policy promises. One
mail per decision: ``submission_grading.apply_grade`` sends it only when the
work's status changes, not on every save of a rubric.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.i18n import t
from app.models.course import Chapter
from app.models.user import User
from app.services.email.course_mail import send_course_mail
from app.services.email.render import Fact, Message
from app.services.translation.resolve_for_display import fetch_course_titles_by_id

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session

    from app.models.assignment import Assignment, AssignmentSubmission
    from app.schemas.locale import LocaleCode
    from app.services.email.send import Delivery

logger = logging.getLogger(__name__)

_BRAND = "Equip"


def build_graded_message(
    *,
    locale: LocaleCode,
    assignment_title: str,
    course_title: str | None,
    grade: int,
    max_score: int,
    returned: bool,
    teacher_name: str | None,
    lesson_url: str,
) -> Message:
    """The message, already in ``locale``. Split from sending so a test can read it."""
    facts: list[Fact] = []
    if not returned:
        facts.append(
            Fact(
                label=t(locale, "email.graded.fact.grade"),
                value=t(locale, "email.graded.fact.grade_value", grade=str(grade), max=str(max_score)),
            )
        )
    if teacher_name:
        facts.append(Fact(label=t(locale, "email.graded.fact.teacher"), value=teacher_name))
    return Message(
        eyebrow=course_title or _BRAND,
        title=assignment_title,
        lede=t(locale, "email.graded.lede.returned" if returned else "email.graded.lede.graded"),
        facts=tuple(facts),
        cta_label=t(locale, "email.graded.cta"),
        cta_url=lesson_url,
        preview=t(locale, "email.graded.preview", title=assignment_title),
        notes=(t(locale, "email.graded.why"),),
    )


def graded_subject(locale: LocaleCode, *, assignment_title: str, returned: bool) -> str:
    key = "email.graded.subject.returned" if returned else "email.graded.subject.graded"
    return t(locale, key, title=assignment_title)


def send_graded_email(
    db: Session,
    *,
    submission: AssignmentSubmission,
    assignment: Assignment,
    assignment_title: str,
    locale: LocaleCode,
    teacher_id: UUID,
    grade: int,
    returned: bool,
) -> Delivery | None:
    """Tell the student by mail, unless they turned this kind off. Never raises: the mark is saved either way.

    ``None`` when there is nobody to write to (no address, a deactivated
    account) or the lookups failed; a ``Delivery`` otherwise.
    """
    try:
        student = db.get(User, submission.student_id)
        if student is None:
            return None
        chapter = db.get(Chapter, assignment.chapter_id)
        course_id = chapter.course_id if chapter else None
        course_title = (
            fetch_course_titles_by_id(db, [course_id], display_locale=locale).get(course_id) if course_id else None
        )
        teacher = db.get(User, teacher_id)
        teacher_name = (teacher.full_name if teacher else None) or None
        base = settings.FRONTEND_URL.rstrip("/")
        lesson_url = f"{base}/courses/{course_id}/chapters/{assignment.chapter_id}" if course_id else f"{base}/"
        message = build_graded_message(
            locale=locale,
            assignment_title=assignment_title,
            course_title=course_title or None,
            grade=grade,
            max_score=assignment.max_score,
            returned=returned,
            teacher_name=teacher_name,
            lesson_url=lesson_url,
        )
    except Exception:
        logger.exception("graded email: could not build the message for submission %s", submission.id)
        return None
    return send_course_mail(
        person=student,
        kind="work_returned",
        locale=locale,
        message=message,
        subject=graded_subject(locale, assignment_title=assignment_title, returned=returned),
        # "Olena Koval via Equip": a person the student knows, as the
        # invitation does. Replies are not routed to the teacher: their
        # address is theirs to give.
        sender_name=teacher_name,
    )
