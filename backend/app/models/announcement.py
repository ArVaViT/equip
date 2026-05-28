import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Announcement(Base):
    __tablename__ = "announcements"
    __table_args__ = (
        Index("ix_announcements_course_id", "course_id"),
        Index("ix_announcements_created_by", "created_by"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # Phase 5e5: title + content columns dropped — cv is the only store.
    course_id: Mapped[str | None] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"))
    created_by: Mapped[uuid.UUID] = mapped_column()
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Announcement id={self.id}>"
