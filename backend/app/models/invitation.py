import enum
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class InvitationRole(enum.StrEnum):
    TEACHER = "teacher"
    STUDENT = "student"


class InvitationStatus(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


def _default_expires_at() -> datetime:
    return datetime.now(UTC) + timedelta(days=7)


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = (
        # Mirror the prod CHECK constraints (see the migration) so the
        # SQLite test path and the Postgres schema-smoke job enforce the
        # same value domains.
        CheckConstraint("role IN ('teacher', 'student')", name="chk_invitations_role"),
        CheckConstraint("status IN ('pending', 'accepted', 'revoked')", name="chk_invitations_status"),
        Index("ix_invitations_email_role", "email", "role", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column()
    role: Mapped[str] = mapped_column()
    # ``unique=True`` already creates a B-tree index for token lookups.
    token: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default=InvitationStatus.PENDING.value)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_default_expires_at)

    inviter: Mapped["User | None"] = relationship(foreign_keys=[invited_by])

    def __repr__(self) -> str:
        return f"<Invitation id={self.id} email={self.email!r} role={self.role!r} status={self.status!r}>"
