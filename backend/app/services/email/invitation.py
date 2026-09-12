"""The invitation email.

An invitation is the first thing many people ever see of Equip, and for
a month it was a blue button on a white page that said "you have been
invited to Equip" without naming the school, the course, or the person
inviting. This builds the message the platform can actually stand
behind: what you are invited to, by whom, into which school, and what
it costs you to find out (one click, and the link's last day).

Everything here is resolved before it reaches the renderer, in the
language of the person doing the inviting — the invited person has no
account yet, so there is no preference of theirs to read.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.i18n import t
from app.models.course import Chapter, Course
from app.models.invitation import InvitationScope
from app.models.organization import Organization
from app.services.email.render import Fact, Message, render
from app.services.email.send import Delivery, send_email
from app.services.translation.resolve_for_display import fetch_course_titles_by_id

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy.orm import Session

    from app.models.invitation import Invitation
    from app.schemas.locale import LocaleCode

_BRAND = "Equip"


def _absolute(url: str | None) -> str | None:
    """A cover path as mail can fetch it.

    Course images are stored as ``/img/<bucket>/<key>`` — a path the app
    proxies. A mail client has no origin to resolve that against.
    """
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return f"{settings.FRONTEND_URL.rstrip('/')}{url}"


#: How each language writes a bare date. Not month names: that would be
#: forty-eight catalog entries, and Russian and Ukrainian would then
#: have to decline them ("19 сентября" is not "сентябрь"). A numeric
#: date says the same thing in every language and cannot be declined
#: wrongly. Day-first where the language reads day-first; ISO for
#: English, which is what the web app already prints.
_DATE_FORMAT: dict[str, str] = {
    "ru": "%d.%m.%Y",
    "uk": "%d.%m.%Y",
    "de": "%d.%m.%Y",
    "en": "%Y-%m-%d",
}


def _day(moment: datetime, locale: LocaleCode) -> str:
    """The link's last day, written the way this language writes dates."""
    return moment.date().strftime(_DATE_FORMAT.get(locale, "%Y-%m-%d"))


def _lesson_count(db: Session, course_id: str) -> int:
    return db.query(Chapter).filter(Chapter.course_id == course_id, Chapter.deleted_at.is_(None)).count()


def _course_title(db: Session, course_id: str, locale: LocaleCode) -> str | None:
    titles = fetch_course_titles_by_id(db, [course_id], display_locale=locale)
    return titles.get(course_id) or None


def build_invitation_message(
    db: Session,
    invitation: Invitation,
    *,
    accept_url: str,
    locale: LocaleCode,
    inviter_name: str | None,
) -> Message:
    """The invitation as a message, already in ``locale``.

    Split from sending so it can be rendered and read in a test without
    a provider, which is how the palette guard and the four-language
    check work.
    """
    role = t(locale, f"role.{invitation.role}")
    organization = db.query(Organization).filter(Organization.id == invitation.organization_id).first()
    org_name = organization.public_name if organization else None
    # Whoever is inviting has a name far more often than not; when they
    # do not, the school is the next most honest subject for the
    # sentence, and the platform is the last resort.
    inviter = inviter_name or org_name or _BRAND

    course: Course | None = None
    course_title: str | None = None
    if invitation.scope == InvitationScope.COURSE.value and invitation.course_id:
        course = db.query(Course).filter(Course.id == invitation.course_id).first()
        course_title = _course_title(db, invitation.course_id, locale) if course else None

    facts: list[Fact] = []
    if course is not None:
        lessons = _lesson_count(db, course.id)
        if lessons:
            facts.append(Fact(label=t(locale, "email.invitation.fact.lessons"), value=str(lessons)))
    facts.append(Fact(label=t(locale, "email.invitation.fact.role"), value=role))

    if course is not None and course_title:
        eyebrow = t(locale, "email.invitation.eyebrow.course")
        title = course_title
        lede = t(locale, "email.invitation.lede.course", inviter=inviter, org=org_name or _BRAND)
    elif org_name:
        eyebrow = t(locale, "email.invitation.eyebrow.organization")
        title = org_name
        lede = t(locale, "email.invitation.lede.organization", inviter=inviter, role=role)
    else:
        eyebrow = t(locale, "email.invitation.eyebrow.platform")
        title = _BRAND
        lede = t(locale, "email.invitation.lede.platform", inviter=inviter, role=role, brand=_BRAND)

    return Message(
        eyebrow=eyebrow,
        title=title,
        lede=lede,
        org_name=org_name,
        banner_url=_absolute(course.image_url) if course is not None else None,
        banner_alt=course_title,
        facts=tuple(facts),
        cta_label=t(locale, "email.invitation.cta"),
        cta_url=accept_url,
        preview=t(locale, "email.invitation.preview", title=title),
        notes=(
            t(locale, "email.invitation.expires", date=_day(invitation.expires_at, locale)),
            t(locale, "email.invitation.ignore"),
        ),
        footer=t(locale, "email.invitation.footer"),
    )


def invitation_subject(message: Message, locale: LocaleCode, scope: str) -> str:
    key = "email.invitation.subject.course" if scope == InvitationScope.COURSE.value else "email.invitation.subject"
    return t(locale, key, title=message.title, brand=_BRAND)


def send_invitation_email(
    db: Session,
    invitation: Invitation,
    *,
    accept_url: str,
    locale: LocaleCode,
    inviter_name: str | None = None,
) -> Delivery:
    """Render and send. Never raises — see ``send_email``."""
    message = build_invitation_message(
        db,
        invitation,
        accept_url=accept_url,
        locale=locale,
        inviter_name=inviter_name,
    )
    return send_email(
        to=invitation.email,
        subject=invitation_subject(message, locale, invitation.scope),
        html=render(message),
        kind="invitation",
    )
