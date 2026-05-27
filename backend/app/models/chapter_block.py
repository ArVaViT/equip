import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# The single source of truth for ``block_type`` values. Mirrors the
# Postgres CHECK constraint ``chapter_blocks_block_type_check`` (created
# in supabase migration ``20260521175824_add_check_constraints.sql``).
# Keeping the literal here means a 4-way mirror change starts in one
# place: this tuple, the Pydantic ``schemas.chapter_block.BLOCK_TYPES``,
# the TS ``frontend/src/components/editor/blocks/types.ts``, and a
# Postgres ALTER on the CHECK.
BLOCK_TYPES: tuple[str, ...] = ("text", "quiz", "assignment", "file")


class ChapterBlock(Base):
    __tablename__ = "chapter_blocks"
    __table_args__ = (
        Index("ix_chapter_blocks_chapter_id_order", "chapter_id", "order_index"),
        # Declared here so the SQLAlchemy schema-smoke CI job sees the
        # constraint that prod's CHECK already enforces. Previously the
        # model lied — Mapped[str] with no constraint declaration — and
        # the smoke test couldn't catch a future widening that broke
        # the Pydantic Literal mirror.
        CheckConstraint(
            f"block_type IN ({', '.join(repr(v) for v in BLOCK_TYPES)})",
            name="chapter_blocks_block_type_check",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    chapter_id: Mapped[str] = mapped_column(ForeignKey("chapters.id", ondelete="CASCADE"))
    block_type: Mapped[str] = mapped_column(String(20))
    order_index: Mapped[int] = mapped_column(default=0)
    content: Mapped[str | None] = mapped_column(Text)
    quiz_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("quizzes.id", ondelete="SET NULL"))
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("assignments.id", ondelete="SET NULL"))
    # Persist only the bucket + object path. Signed URLs are minted on
    # demand by the client against the current Supabase secret, so JWT-secret
    # rotation can never break chapter file links.
    file_bucket: Mapped[str | None] = mapped_column(String(50))
    file_path: Mapped[str | None] = mapped_column(Text)
    file_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
