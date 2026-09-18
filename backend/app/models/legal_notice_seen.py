"""The record that somebody was *told* about a change — not that they agreed.

The documents now distinguish two kinds of edit. A material change asks for a
fresh acceptance and lands in ``legal_acceptances``. Everything else — a
correction, a plainer sentence, a shortened retention window, a new right — is
published and announced, and nobody signs anything.

Announcing it needs somewhere to remember that it was announced, and that
somewhere must not be ``legal_acceptances``: a row there asserts agreement, and
asserting agreement to a change nobody was asked about is how a consent table
stops meaning anything. Hence a second, smaller table, holding a weaker claim.

No IP. An acceptance and a submission declaration record one because the
privacy policy names those two moments and because they may one day have to be
proved. Closing a banner is neither.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LegalNoticeSeen(Base):
    """One person having been told about one version of one document."""

    __tablename__ = "legal_notices_seen"
    __table_args__ = (
        # One row per person per version. A double-click is not a second
        # telling, and two rows would leave two answers to "when were they
        # told" with no way to choose between them.
        UniqueConstraint("user_id", "document_slug", "version", name="uq_legal_notices_seen_user_doc_version"),
        Index("ix_legal_notices_seen_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    document_slug: Mapped[str] = mapped_column(Text)
    #: The version they were told about — the current one at that moment.
    version: Mapped[str] = mapped_column(Text)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
