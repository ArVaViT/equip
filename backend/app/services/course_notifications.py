"""What a teacher's course-level post needs before it can reach the class.

An announcement and a calendar event fan out the same way: every
enrolled student except the author, grouped by the language they read
in, each group told in its own words about a thing whose title also has
a version in that language — or does not yet.

The pieces live here so ``announcements.py`` and ``calendar.py`` share
one answer to each question. The ``create_notifications_bulk`` call
itself stays in the route, with the kind written as a literal: the
notification-kinds test walks call sites statically and refuses a kind
it cannot read off the source.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from app.core.i18n import t
from app.models.enrollment import Enrollment
from app.models.notification import Notification
from app.models.user import User
from app.schemas.locale import LocaleCode, normalize_locale
from app.services.content_versions import fetch_cv_entity_texts_with_fallback
from app.services.translation.resolve_for_display import fetch_course_titles_by_id

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

    from app.models.course import Course


def enrolled_recipients_by_locale(
    db: Session,
    *,
    course_id: str,
    exclude_user_id: uuid.UUID | str | None,
) -> dict[LocaleCode, list[uuid.UUID]]:
    """Enrolled students who should hear about a course post, grouped by
    the language they read in.

    The author is left out — they wrote it. Deactivated accounts keep
    their enrollment rows but receive nothing (#786 rule).
    """
    rows = (
        db.query(Enrollment.user_id, User.preferred_locale)
        .join(User, User.id == Enrollment.user_id)
        .filter(
            Enrollment.course_id == course_id,
            User.deactivated_at.is_(None),
        )
        .all()
    )
    out: dict[LocaleCode, list[uuid.UUID]] = {}
    for uid, raw_locale in rows:
        if exclude_user_id is not None and str(uid) == str(exclude_user_id):
            continue
        out.setdefault(normalize_locale(raw_locale), []).append(uid)
    return out


def course_title_for_locale(db: Session, course: Course, locale: LocaleCode) -> str:
    return fetch_course_titles_by_id(db, [course.id], display_locale=locale).get(course.id) or t(
        locale, "fallback.course"
    )


def entity_title_for_locale(
    db: Session,
    *,
    entity_type: Literal["announcement", "course_event"],
    entity_id: uuid.UUID | str,
    locale: LocaleCode,
    source_locale: LocaleCode,
    fallback_key: str,
) -> str:
    """The post's title as this recipient should read it.

    Three tiers, in order:

    1. A version in the recipient's language — the MT row the reconcile
       step wrote a moment ago, when it has already run.
    2. The author's own text, but only for a recipient who reads the
       language it was written in. On a published course a new post
       does not enter ``content_versions`` at all until every language
       has it (see ``services/staged_edits``); it waits in the staging
       table, and a same-language reader was being told about «an
       announcement» while the title sat one table over. Their language
       is the author's language, so the author's text is the right one.
    3. ``fallback_key`` — a reader of another language is not handed the
       author's language. A notification's text is frozen into their
       bell; a Russian title sent to a German reader stays there for
       good.
    """
    eid = str(entity_id)
    texts = fetch_cv_entity_texts_with_fallback(
        db,
        entity_type=entity_type,
        entity_ids=[eid],
        fields=["title"],
        display_locale=locale,
        source_locale=source_locale,
        include_author_edits=locale == source_locale,
    )
    return texts.get((eid, "title")) or t(locale, fallback_key)


def delete_notifications_about(
    db: Session,
    *,
    types: tuple[str, ...],
    link: str,
    meta_key: str,
    target_id: uuid.UUID | str,
) -> int:
    """Drop the notification rows a deleted post left in every recipient's
    bell.

    The rows point at the post only through ``meta[meta_key]``, which
    Postgres has no way to follow on its own. ``link`` was fixed at
    fan-out time, so the candidate set narrows in SQL by type + link and
    the ``meta`` match happens in Python — sidesteps the ``->>`` /
    ``json_extract`` dialect split while keeping the candidate count
    bounded by one course's enrollment.
    """
    target = str(target_id)
    candidates = db.query(Notification).filter(Notification.type.in_(types), Notification.link == link).all()
    stale_ids = [n.id for n in candidates if isinstance(n.meta, dict) and str(n.meta.get(meta_key)) == target]
    if not stale_ids:
        return 0
    db.query(Notification).filter(Notification.id.in_(stale_ids)).delete(synchronize_session=False)
    return len(stale_ids)
