import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CourseEvent(Base):
    __tablename__ = "course_events"
    # event_date intentionally has no index — the calendar API loads
    # events by course_id (covered by ix_course_events_course_id) and
    # sorts in Python (`events.sort(key=lambda e: e.event_date)` in
    # calendar.py). No SQL ORDER BY event_date exists, so an index
    # there does no work.
    __table_args__ = (Index("ix_course_events_course_id", "course_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(String(30), default="other")
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
