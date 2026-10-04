"""An organization — the thing a course, a cohort and a certificate belong to.

Not "school". A Bible school is one kind of organization that uses Equip;
a church's training programme and a mission's internal course are others,
and none of them should have to read the platform's word for themselves.

Membership is a row, not a column (decided 2026-10-03, reversing the
one-organization-per-account decision of 2026-08-26). The earlier decision
wrote down the signal that would change it — "the first person who asks" —
and the director of UCOAT asked: he had to give up directing to be able
to teach, because the role sat on the account and the account sat in one
place. ``OrganizationMember`` holds one role per (person, organization);
``profiles.role`` mirrors the highest of them (see ``app.models.user``).
``profiles.organization_id`` is deprecated and goes in the last phase of
the same plan.

See ``engineering/organizations-engineering-plan.md`` in equipbible-docs
and migration ``20261003165050_an_account_belongs_to_several_organizations``.
"""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'verified', 'suspended')",
            name="organizations_status_check",
        ),
        # Not mirrored, like ``slug`` below: the 280-character limit on
        # ``description`` uses ``char_length`` and the https rule on
        # ``website_url`` is a regex, neither of which SQLite has. The API
        # schema refuses both before they reach the database.
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    #: The URL and the certificate both carry this. Immutable once a
    #: certificate has been issued against it — the document points here.
    #:
    #: Its shape — lowercase, digits, single hyphens — is enforced by a
    #: regex CHECK in Postgres and by the create schema in the API. It is
    #: deliberately not declared here: the test database is SQLite, which
    #: has no ``~`` operator, and a constraint that cannot be built is
    #: worse than one declared in the two places that can enforce it.
    slug: Mapped[str] = mapped_column(unique=True)

    #: What a certificate prints, and the scarce thing this platform
    #: defends: an organization's name is how a student's employer decides
    #: whether the document means anything.
    public_name: Mapped[str] = mapped_column(unique=True)
    legal_name: Mapped[str | None] = mapped_column()
    country: Mapped[str | None] = mapped_column()

    #: pending → approved → verified, and suspended from any of them.
    #: An approved organization has the whole inward-facing product; a
    #: verified one is also listed publicly and may issue certificates.
    status: Mapped[str] = mapped_column(default="approved", server_default="approved")

    # ``use_alter`` because these close a cycle: an organization names the
    # people who created and verified it, and those people belong to an
    # organization. Postgres does not mind — the tables are created in
    # order and the constraints added after — but SQLAlchemy has to be
    # told, or building the schema from the models (which is how the test
    # database is built) cannot find an order that works.
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL", use_alter=True, name="organizations_created_by_fkey")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL", use_alter=True, name="organizations_verified_by_fkey")
    )

    #: What the verification rested on — a domain, a registry entry, a
    #: reference from another verified organization. A column rather than
    #: a note, so one query can answer "which organizations rest on a
    #: proof we have stopped trusting".
    verification_basis: Mapped[str | None] = mapped_column()

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    #: What the organization says about itself on its public page. One
    #: text in the organization's own language, like ``public_name`` —
    #: deliberately not run through the translation pipeline (see
    #: ``resolve_for_display._organizations_of``). At most 280 characters:
    #: a paragraph that fits a card and an ``og:description``.
    description: Mapped[str | None] = mapped_column()
    #: A file in the public ``organization-logos`` bucket (arrives with the
    #: page, phase 4); served through the ``/img`` proxy like avatars.
    logo_url: Mapped[str | None] = mapped_column()
    #: https only, enforced in Postgres and by the API schema. The page
    #: links to it, and a "verified" page linking to plain http is the
    #: platform vouching for a downgrade.
    website_url: Mapped[str | None] = mapped_column()
    #: The director's switch for the one number on the page that is about
    #: people rather than about the organization. The page also hides the
    #: count below a floor, whatever this says — four members next to a
    #: director's name is nearly a list of people.
    show_member_count: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))

    members: Mapped[list["OrganizationMember"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class MembershipRole(enum.StrEnum):
    """The role a person holds inside one organization.

    ``director ⊇ teacher ⊇ student``, the same reach ordering ``higher_role``
    uses. Platform ``admin`` is deliberately absent: it is not a role in an
    organization, it is a role over the platform, and the two were split on
    purpose (``20260826120000_a_director_is_not_a_platform_admin``).
    """

    DIRECTOR = "director"
    TEACHER = "teacher"
    STUDENT = "student"


class MembershipStatus(enum.StrEnum):
    """``suspended`` rather than deleted: who brought this person in, and
    when, is kept — as ``deactivated_at`` keeps an account."""

    ACTIVE = "active"
    SUSPENDED = "suspended"


class MembershipSource(enum.StrEnum):
    """How the person got here — the answer to "and how did they get in"."""

    #: A named invitation to this address, accepted.
    INVITATION = "invitation"
    #: A reusable link a director handed out (phase 6).
    JOIN_LINK = "join_link"
    #: Appointed by platform staff (a director) or placed by a director
    #: (a student added to a cohort of a closed course).
    APPOINTMENT = "appointment"
    #: Carried over from ``profiles.organization_id`` by the migration, or
    #: by the test fixtures that stand in for it.
    MIGRATION = "migration"


#: Reach order inside one organization, least to most. Used to decide what
#: an invitation or an appointment may change a membership *to*: never
#: down. Platform ``admin`` is not here on purpose — see ``MembershipRole``.
MEMBERSHIP_RANK: dict[str, int] = {
    MembershipRole.STUDENT.value: 0,
    MembershipRole.TEACHER.value: 1,
    MembershipRole.DIRECTOR.value: 2,
}

#: The membership roles that put somebody on an organization's staff side:
#: its cohorts, its closed courses as an author, its invitations. The
#: platform-wide twin is ``app.models.user.TEACHING_ROLES``.
STAFF_ROLES: frozenset[str] = frozenset({MembershipRole.DIRECTOR.value, MembershipRole.TEACHER.value})


class OrganizationMember(Base):
    """One person in one organization, in one role.

    One role per pair rather than a set: the application already treats
    the roles as nested (``TEACHING_ROLES`` includes the director), and a
    set would admit "director but not teacher", a state the product does
    not distinguish.

    Written only by the backend (an invitation accepted, a director
    appointed, a student placed in a cohort of a closed course). The
    ``profiles.role`` mirror is kept by a trigger in Postgres and repeated
    by ``app.services.memberships`` for the SQLite test database.
    """

    __tablename__ = "organization_members"
    __table_args__ = (
        CheckConstraint("role IN ('director', 'teacher', 'student')", name="organization_members_role_check"),
        CheckConstraint("status IN ('active', 'suspended')", name="organization_members_status_check"),
        CheckConstraint(
            "joined_via IN ('invitation', 'join_link', 'appointment', 'migration')",
            name="organization_members_joined_via_check",
        ),
        # The primary key answers "where does this person belong"; this
        # answers the organization's questions — its directors, its member
        # count — without reading the suspended rows.
        Index(
            "ix_organization_members_org_role",
            "organization_id",
            "role",
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column()
    status: Mapped[str] = mapped_column(default=MembershipStatus.ACTIVE.value, server_default="active")
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    invited_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("profiles.id", ondelete="SET NULL"))
    joined_via: Mapped[str] = mapped_column()

    user: Mapped["User"] = relationship(back_populates="memberships", foreign_keys=[user_id])
    organization: Mapped[Organization] = relationship(back_populates="members")

    @property
    def is_active(self) -> bool:
        return self.status == MembershipStatus.ACTIVE.value

    def __repr__(self) -> str:
        return (
            f"<OrganizationMember user={self.user_id} organization={self.organization_id} "
            f"role={self.role!r} status={self.status!r}>"
        )
