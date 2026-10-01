"""The "your certificate has a decision" email.

A certificate is what a student finishes a course for, and the decision on
it is taken by a director the student may never have met, days after they
asked. Until now the only news was under the bell. This is the message that
reaches them outside the app: issued — with the number and where anyone can
check it — or not approved, with the way back to the course.

Course mail of the kind ``certificate_decided``: it goes through
``course_mail.send_course_mail``, so the student can turn it off in the
profile or from the link at its foot. Sent once per decision, after the
decision is committed: ``certificate_service.admin_approve`` and ``reject``
each move the certificate out of a state they refuse to act on twice.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.i18n import t
from app.models.course import Course
from app.models.user import User
from app.services.email.course_mail import send_course_mail
from app.services.email.render import Fact, Message
from app.services.translation.resolve_for_display import fetch_course_titles_by_id

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.certificate import Certificate
    from app.schemas.locale import LocaleCode
    from app.services.email.send import Delivery

logger = logging.getLogger(__name__)


def build_certificate_message(
    *,
    locale: LocaleCode,
    course_title: str,
    issued: bool,
    certificate_number: str | None,
    verify_url: str | None,
    action_url: str,
) -> Message:
    """The message, already in ``locale``. Split from sending so a test can read it."""
    facts: list[Fact] = []
    if issued and certificate_number:
        facts.append(Fact(label=t(locale, "email.cert.fact.number"), value=certificate_number))
        if verify_url:
            facts.append(Fact(label=t(locale, "email.cert.fact.verify"), value=verify_url))
    state = "issued" if issued else "rejected"
    return Message(
        eyebrow=course_title,
        title=t(locale, f"email.cert.title.{state}"),
        lede=t(locale, f"email.cert.lede.{state}"),
        facts=tuple(facts),
        cta_label=t(locale, f"email.cert.cta.{state}"),
        cta_url=action_url,
        preview=t(locale, f"email.cert.preview.{state}", course=course_title),
        notes=(t(locale, "email.cert.why"),),
    )


def send_certificate_email(db: Session, *, cert: Certificate, locale: LocaleCode, issued: bool) -> Delivery | None:
    """Tell the student by mail, unless they turned this kind off. Never raises: the decision stands either way."""
    try:
        student = db.get(User, cert.user_id)
        if student is None:
            return None
        live_title = (
            fetch_course_titles_by_id(db, [cert.course_id], display_locale=locale).get(cert.course_id)
            if cert.course_id
            else None
        )
        course_title = (
            live_title or cert.course_title or cert.archived_course_title or t(locale, "fallback.your_course")
        )
        base = settings.FRONTEND_URL.rstrip("/")
        # A course since moved to the bin has no page to go back to.
        course = db.get(Course, cert.course_id) if cert.course_id else None
        course_open = course is not None and course.deleted_at is None
        number = cert.certificate_number if issued else None
        message = build_certificate_message(
            locale=locale,
            course_title=course_title,
            issued=issued,
            certificate_number=number,
            verify_url=f"{base}/verify/{number}" if number else None,
            action_url=(
                f"{base}/certificates/{cert.id}"
                if issued
                else f"{base}/courses/{cert.course_id}"
                if course_open
                else f"{base}/certificates"
            ),
        )
        subject = t(locale, f"email.cert.subject.{'issued' if issued else 'rejected'}", course=course_title)
    except Exception:
        logger.exception("certificate email: could not build the message for certificate %s", cert.id)
        return None
    return send_course_mail(person=student, kind="certificate_decided", locale=locale, message=message, subject=subject)
