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
    #: The person got what the invitation offered without using its link --
    #: enrolled on the course, joined the organization, signed up. Set by the
    #: database (``public.fulfil_pending_invitations`` and its triggers), never
    #: by the application: see migration 20260917023526 for why the rule lives
    #: there. Distinct from ``accepted`` so the sender can tell "used the link"
    #: from "came in another way".
    FULFILLED = "fulfilled"


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
        CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'fulfilled')",
            name="chk_invitations_status",
        ),
        CheckConstraint(
            "(status = 'fulfilled') = (fulfilled_at IS NOT NULL)",
            name="chk_invitations_fulfilled_at_matches_status",
        ),
        CheckConstraint("scope IN ('platform', 'organization', 'course')", name="chk_invitations_scope"),
        # The scope and its target agree in both directions.
        CheckConstraint(
            "(scope = 'course' AND course_id IS NOT NULL) OR (scope <> 'course' AND course_id IS NULL)",
            name="chk_invitations_course_matches_scope",
        ),
        # An attestation with no attester answers "who said so" with silence,
        # which is the one question the record is kept to answer.
        CheckConstraint(
            "(age_attested_at IS NULL) = (age_attested_by IS NULL)",
            name="chk_invitations_age_attested_together",
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: When the person arrived without the link (status ``fulfilled``).
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_default_expires_at)
    #: When the inviter said this person is thirteen or older, and who said it.
    #:
    #: A school administrator can bring somebody in who is too young to sign
    #: up for themselves — that is the whole point of an invitation, and the
    #: product rule from 2026-09-17 is that the floor for it is thirteen.
    #: Below that the platform does not want an account at all: COPPA turns a
    #: known under-13 into verifiable parental consent, a records-access duty
    #: and a deletion duty, and none of that is a thing nine teachers should
    #: be running.
    #:
    #: No date of birth. The platform does not need one, and asking would
    #: collect a piece of personal data about a child in order to protect
    #: children. What it needs is a person who knows the family saying so,
    #: and a record of who that was — which is these two columns.
    #:
    #: Nullable because every invitation written before this existed has no
    #: answer, and inventing one would be the opposite of a record. Both
    #: columns move together (``chk_invitations_age_attested_together``): an
    #: attestation with no attester is an assertion nobody made.
    age_attested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    age_attested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL"), default=None
    )

    inviter: Mapped["User | None"] = relationship(foreign_keys=[invited_by])

    def __repr__(self) -> str:
        return (
            f"<Invitation id={self.id} email={self.email!r} role={self.role!r} "
            f"scope={self.scope!r} status={self.status!r}>"
        )
