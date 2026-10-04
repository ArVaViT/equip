"""The hour-before reminder for a live class or an exam.

A student who put the class in their head on Monday has to be told on
Saturday evening. The bell is where they already look, and the
notification carries the meeting link, so "join" is one tap from the
reminder itself. Mail is deliberately not part of this: reminders by
mail wait for the reader's consent (see the product plan), and a bell
that says "in an hour" asks for nothing.

Run every five minutes by Vercel Cron; each event is reminded once
(``course_events.reminded_at``), and moving the event clears the stamp
so the new time gets its own reminder.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.models.course import Course, CourseStatus
from app.models.course_event import CourseEvent
from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

#: How far ahead a class is "starting soon".
REMIND_WITHIN = timedelta(hours=1)

#: The kinds that are attended at a time. A deadline is not "starting".
REMINDED_KINDS = ("live_session", "exam")


def send_due_reminders(db: Session, *, now: datetime | None = None) -> int:
    """Remind the class of every event starting within the hour; return how many events.

    An event that already started without a reminder (the cron was down)
    is left alone: "starting within the hour" about a class in progress
    is wrong, and the class has the join button on the calendar anyway.
    """
    # Imported here: the notifier lives with the routes that also call it.
    from app.api.v1.calendar import notify_students_about_event

    now = now or datetime.now(UTC)
    due = (
        db.query(CourseEvent, Course)
        .join(Course, Course.id == CourseEvent.course_id)
        .filter(
            CourseEvent.reminded_at.is_(None),
            CourseEvent.event_type.in_(REMINDED_KINDS),
            CourseEvent.event_date > now,
            CourseEvent.event_date <= now + REMIND_WITHIN,
            Course.deleted_at.is_(None),
            Course.status == CourseStatus.PUBLISHED,
        )
        .order_by(CourseEvent.event_date)
        .all()
    )
    for event, course in due:
        # Stamped first and committed by the notifier: a crash mid-fan-out
        # costs one reminder, never a second copy of it every five minutes.
        event.reminded_at = now
        author = db.get(User, event.created_by)
        notify_students_about_event(db, course=course, event=event, author=author, rescheduled=False, reminder=True)
    if due:
        logger.info("event_reminders.sent", extra={"events": len(due)})
    return len(due)
