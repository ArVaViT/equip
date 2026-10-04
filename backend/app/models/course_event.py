import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CourseEvent(Base):
    __tablename__ = "course_events"
    # event_date intentionally has no index — the calendar API loads
    # events by course_id (covered by ix_course_events_course_id) and
    # sorts in Python (`events.sort(key=lambda e: e.event_date)` in
    # calendar.py). No SQL ORDER BY event_date exists, so an index
    # there does no work.
    __table_args__ = (
        Index("ix_course_events_course_id", "course_id"),
        Index(
            "ix_course_events_series_id",
            "series_id",
            postgresql_where=text("series_id IS NOT NULL"),
            sqlite_where=text("series_id IS NOT NULL"),
        ),
        Index(
            "ix_course_events_unreminded",
            "event_date",
            postgresql_where=text("reminded_at IS NULL"),
            sqlite_where=text("reminded_at IS NULL"),
        ),
        CheckConstraint(
            "duration_minutes IS NULL OR (duration_minutes >= 1 AND duration_minutes <= 1440)",
            name="course_events_duration_minutes_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    # Title + description columns dropped — cv is the only
    # store. Reads go through fetch_cv_entity_texts_with_fallback;
    # writes through dual_write_entity_content(texts={...}).
    event_type: Mapped[str] = mapped_column(String(30), default="other")
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Where the live session happens. Not in cv with the title and the
    # description, because it is not text: an address is the same string
    # in every language, and running it through the translation pipeline
    # would invite a model to "fix" a URL. Validated to http(s) before it
    # is written — see app/core/meeting_url.py.
    meeting_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # Where to watch it afterwards, once the teacher has a recording. The
    # same kind of value as ``meeting_url`` and validated by the same rule.
    recording_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # How long it lasts. ``None`` for a moment rather than a span — a
    # deadline — and for events written before the column existed, which
    # the readers treat as an hour, the length they always guessed.
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Occurrences of one weekly series share this id. Each occurrence is
    # its own row, so one lesson can move, be cancelled or carry its own
    # recording; the id is what "this and the following" edits act on.
    series_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    # When the hour-before reminder went out — at most once per event.
    # Moving the event clears it, so the new time is announced again.
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
