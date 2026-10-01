"""A student's own note on a lesson — see migration 20261001190000."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ChapterNote(Base):
    __tablename__ = "chapter_notes"
    __table_args__ = (Index("ix_chapter_notes_chapter_id", "chapter_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    chapter_id: Mapped[str] = mapped_column(String, ForeignKey("chapters.id", ondelete="CASCADE"), primary_key=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
