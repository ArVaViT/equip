import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ChapterProgress(Base):
    __tablename__ = "chapter_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "chapter_id", name="uq_progress_user_chapter"),
        # Mirrors the production CHECK so the SQLite test DB (bootstrapped
        # from these models via ``Base.metadata.create_all``) rejects invalid
        # values too. A regression like completion_type="quiz" is caught in
        # tests without having to go through the prod DB to find out.
        CheckConstraint(
            "completion_type IN ('self', 'teacher', 'quiz', 'excused')",
            name="chapter_progress_completion_type_check",
        ),
        # ``uq_progress_user_chapter`` already provides a B-tree on
        # ``user_id`` via its leading column; keep only the chapter-side
        # index for the "all progress rows for chapter X" access pattern.
        Index("ix_chapter_progress_chapter_id", "chapter_id"),
        # Partial composite for _load_completed_progress: filters
        # `chapter_id IN (...) AND completed [AND user_id IN (...)]`.
        Index(
            "ix_chapter_progress_chapter_user_completed",
            "chapter_id",
            "user_id",
            postgresql_where=text("completed"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"))
    completed: Mapped[bool] = mapped_column(default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[uuid.UUID | None] = mapped_column()
    completion_type: Mapped[str] = mapped_column(String(20), default="self")
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
