"""The record that somebody agreed to a specific text at a specific moment.

Before this, acceptance lived in ``localStorage`` under
``equip.privacy.accepted.<userId>``. Clearing a browser erased it; a second
device never had it; and nothing anywhere could answer "did this person agree,
and to what". That is the entire job of a consent record, and the platform was
not doing it.

Same principle as the certificate letterhead and the submission declaration:
what somebody agreed to has to survive the thing they agreed to being changed.
So this stores the version and the hash of the text as served, not a foreign key
into a documents table that a later edit would silently rewrite.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LegalAcceptance(Base):
    """One person accepting one version of one document."""

    __tablename__ = "legal_acceptances"
    __table_args__ = (
        # One row per person per version. Re-accepting the same version is a
        # no-op rather than a second row: a double-click is not new consent.
        UniqueConstraint("user_id", "document_slug", "version", name="uq_legal_acceptances_user_doc_version"),
        Index("ix_legal_acceptances_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    document_slug: Mapped[str] = mapped_column(Text)
    version: Mapped[str] = mapped_column(Text)
    #: Which translation they actually read. Both share a version, but a
    #: student who read the Russian text agreed to the Russian text.
    locale: Mapped[str] = mapped_column(Text)
    #: SHA-256 of the body as served, so "you agreed to this" stays checkable.
    content_sha256: Mapped[str] = mapped_column(Text)
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    #: Kept for the same reason as on a submission declaration, and named in
    #: the privacy policy itself: it is evidence that the acceptance happened,
    #: and it is used for nothing else.
    ip: Mapped[str | None] = mapped_column(Text)
