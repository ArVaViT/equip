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


class InvitationScope(enum.StrEnum):
    """What accepting the invitation grants.

    Stored rather than inferred from which target column is set: a
    course invitation whose course has been deleted must stay a course
    invitation and fail, not quietly become an organization invitation
    and hand somebody a membership nobody offered them.
    """

    #: An account and nothing else.
    PLATFORM = "platform"
    #: Membership of the inviting organization, plus the role.
    ORGANIZATION = "organization"
    #: Membership, the role, and enrolment on ``course_id``.
    COURSE = "course"


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
        CheckConstraint("scope IN ('platform', 'organization', 'course')", name="chk_invitations_scope"),
        # The scope and its target agree in both directions.
        CheckConstraint(
            "(scope = 'course' AND course_id IS NOT NULL) OR (scope <> 'course' AND course_id IS NULL)",
            name="chk_invitations_course_matches_scope",
        ),
        Index("ix_invitations_email_role", "email", "role", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column()
    role: Mapped[str] = mapped_column()
    scope: Mapped[str] = mapped_column(default=InvitationScope.ORGANIZATION.value, server_default="organization")
    #: The course an accepted invitation enrols into. CASCADE on the
    #: course: an invitation to a deleted course leads nowhere, and a
    #: dangling row would answer the preview route with a course that
    #: does not exist.
    course_id: Mapped[str | None] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), default=None)
    # ``unique=True`` already creates a B-tree index for token lookups.
    token: Mapped[str] = mapped_column(unique=True)
    status: Mapped[str] = mapped_column(default=InvitationStatus.PENDING.value)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_default_expires_at)

    inviter: Mapped["User | None"] = relationship(foreign_keys=[invited_by])

    def __repr__(self) -> str:
        return (
            f"<Invitation id={self.id} email={self.email!r} role={self.role!r} "
            f"scope={self.scope!r} status={self.status!r}>"
        )
