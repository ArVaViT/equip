"""An organization — the thing a course, a cohort and a certificate belong to.

Not "school". A Bible school is one kind of organization that uses Equip;
a church's training programme and a mission's internal course are others,
and none of them should have to read the platform's word for themselves.

One organization per account, decided 2026-08-26: a person is a member of
exactly one, through ``profiles.organization_id``, in whatever role they
hold there. The cost of that choice is written down where it can be found
— a teacher who genuinely teaches in two organizations needs two accounts
— along with the signal that would change it: the first person who asks,
not the first one we imagine.

See ``engineering/organizations-engineering-plan.md`` in equipbible-docs.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'verified', 'suspended')",
            name="organizations_status_check",
        ),
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
