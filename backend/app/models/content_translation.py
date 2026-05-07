"""ORM mapping for ``content_translations``.

The table is intentionally polymorphic-by-string: ``entity_type`` plus
``entity_id`` (TEXT) lets us cover everything from UUID-keyed
``chapter_blocks`` to string-keyed ``courses`` without a polymorphic FK or a
table per content type. The trade-off is no DB-level cascade — purging an
entity also requires deleting its translations, which is handled in the
service layer (see ``app/services/translation``).

CHECK-constrained vocabularies (entity_type, field, locale, status, origin)
are mirrored as Python ``Literal`` types so static analysis catches typos
before they reach Postgres.
"""

import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

TranslationEntityType = Literal[
    "chapter_block",
    "course",
    "module",
    "chapter",
    "quiz",
    "quiz_question",
    "quiz_option",
    "assignment",
    "announcement",
    "course_event",
    "cohort",
]
TranslationField = Literal[
    "content",
    "title",
    "description",
    "question_text",
    "option_text",
    "instructions",
]
TranslationStatus = Literal["ok", "stale", "failed"]
TranslationOrigin = Literal["mt", "human"]


class ContentTranslation(Base):
    __tablename__ = "content_translations"
    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "field", "locale", name="content_translations_unique"),
        Index("ix_content_translations_entity", "entity_type", "entity_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(Text)
    field: Mapped[str] = mapped_column(String(40))
    locale: Mapped[str] = mapped_column(String(8))
    text: Mapped[str] = mapped_column(Text)
    # Hash of the source text at translation time — when the source mutates
    # we flip ``status`` to ``stale`` and re-queue the row instead of blowing
    # the translation away.
    source_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="ok", server_default="ok")
    # ``origin = 'human'`` rows are never overwritten by the auto-pipeline.
    origin: Mapped[str] = mapped_column(String(16), default="mt", server_default="mt")
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<ContentTranslation entity={self.entity_type}:{self.entity_id} "
            f"field={self.field} locale={self.locale} status={self.status}>"
        )
