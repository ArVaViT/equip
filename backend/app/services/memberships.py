"""Who belongs where, in which role — the one module that reads ``organization_members``.

Until 2026-10-03 the answer to "which organization is this person in" was a
column, ``profiles.organization_id``, and every route compared against it
by hand (``organization_of``). The column is now deprecated: a person is a
member of several organizations, in a role held per organization, and the
three questions a route can ask are answered here and nowhere else:

* ``belongs_to`` — any active role. Opens an ``institute`` course, its
  cohort list, self-enrolment on it.
* ``teaches_in`` — teacher or director. Creates and clones courses there,
  writes invitations onto its courses.
* ``directs`` — director. Cohorts, ведомости, invitations at large, the
  certificate queue, the organization's settings.

Platform staff pass all three, for the reason every gate on this platform
gives: they administer every organization by definition — not because the
roles are the same thing (``20260826120000_a_director_is_not_a_platform_admin``).

A test greps the application for a read of ``profiles.organization_id`` and
fails on one outside this file: a new route that compares against the old
column by habit is how two sources of truth come to disagree. The one write
of the column left is ``grant_membership`` below, and it is temporary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.organization import (
    MEMBERSHIP_RANK,
    STAFF_ROLES,
    MembershipRole,
    MembershipStatus,
    OrganizationMember,
)
from app.models.user import User, UserRole

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session


def active_memberships(db: Session, user_id: UUID) -> list[OrganizationMember]:
    """Every organization this person is in right now, highest role first."""
    rows = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.user_id == user_id, OrganizationMember.status == MembershipStatus.ACTIVE.value)
        .all()
    )
    return sorted(rows, key=lambda m: -MEMBERSHIP_RANK.get(m.role, -1))


def membership_of(db: Session, user_id: UUID, organization_id: UUID | None) -> OrganizationMember | None:
    """The active membership of ``user_id`` in ``organization_id``, or ``None``.

    ``None`` for a ``None`` organization, by construction rather than by the
    caller remembering: a certificate issued before organizations existed
    has no organization, and that must never read as "the same one".
    """
    if organization_id is None:
        return None
    return (
        db.query(OrganizationMember)
        .filter(
            OrganizationMember.user_id == user_id,
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.status == MembershipStatus.ACTIVE.value,
        )
        .first()
    )


def _holds_at_least(membership: OrganizationMember | None, role: str) -> bool:
    return membership is not None and MEMBERSHIP_RANK.get(membership.role, -1) >= MEMBERSHIP_RANK[role]


def belongs_to(db: Session, user: User | None, organization_id: UUID | None) -> bool:
    """Active member in any role — or platform staff."""
    if user is None:
        return False
    if user.role == UserRole.ADMIN.value:
        return True
    return membership_of(db, user.id, organization_id) is not None


def teaches_in(db: Session, user: User | None, organization_id: UUID | None) -> bool:
    """Active teacher or director there — or platform staff."""
    if user is None:
        return False
    if user.role == UserRole.ADMIN.value:
        return True
    return _holds_at_least(membership_of(db, user.id, organization_id), MembershipRole.TEACHER.value)


def directs(db: Session, user: User | None, organization_id: UUID | None) -> bool:
    """Active director there — or platform staff."""
    if user is None:
        return False
    if user.role == UserRole.ADMIN.value:
        return True
    return _holds_at_least(membership_of(db, user.id, organization_id), MembershipRole.DIRECTOR.value)


def organizations_where(db: Session, user: User, *, at_least: str) -> list[OrganizationMember]:
    """The active memberships in which this person holds ``at_least`` the role.

    Platform staff get every membership they have, whatever its role: an
    admin who sits in UCOAT as a teacher still administers UCOAT, and the
    membership is only there to say *where* they sit by default.
    """
    rows = active_memberships(db, user.id)
    if user.role == UserRole.ADMIN.value:
        return rows
    return [m for m in rows if _holds_at_least(m, at_least)]


def mirror_role(db: Session, user: User) -> None:
    """``profiles.role`` := the highest active membership role.

    The same rule as ``mirror_profile_role()`` in Postgres, which runs from a
    trigger on every membership write and is the one production relies on.
    Repeated here because the test database is SQLite and has no trigger,
    and because a backend that reads the role it just changed should not
    have to go back to the database to see it. Both compute the same value,
    so running twice changes nothing.

    ``admin`` is never touched: platform staff are not a membership role,
    and the only thing that moves somebody in or out of it is the admin route.
    """
    if user.role == UserRole.ADMIN.value:
        return
    rows = active_memberships(db, user.id)
    mirrored = rows[0].role if rows else MembershipRole.STUDENT.value
    if user.role != mirrored:
        user.role = mirrored


def grant_membership(
    db: Session,
    *,
    user: User,
    organization_id: UUID,
    role: str,
    joined_via: str,
    invited_by: UUID | None = None,
) -> tuple[OrganizationMember, bool]:
    """Put ``user`` in ``organization_id`` as ``role``, or raise them to it.

    Idempotent and monotonic within the organization: an existing row keeps
    the higher of its role and the offered one — a director accepting a
    student invitation onto one of their own courses stays a director — and
    a suspended row is reactivated, because whoever is granting now has
    decided the person belongs. Nothing about any *other* organization
    changes: that is the whole point of the table.

    Returns ``(membership, created)`` so the caller can audit "joined" apart
    from "was already there". Flushes, does not commit.

    Transitional: while ``profiles.organization_id`` still exists, the first
    organization a person joins is written there too, so that rolling the
    backend back to the previous release leaves everyone with exactly one
    membership working. Goes with the column.
    """
    if role not in MEMBERSHIP_RANK:
        raise ValueError(f"not a membership role: {role!r}")
    membership = (
        db.query(OrganizationMember)
        .filter(OrganizationMember.user_id == user.id, OrganizationMember.organization_id == organization_id)
        .first()
    )
    created = membership is None
    if membership is None:
        membership = OrganizationMember(
            user_id=user.id,
            organization_id=organization_id,
            role=role,
            status=MembershipStatus.ACTIVE.value,
            joined_via=joined_via,
            invited_by=invited_by,
        )
        db.add(membership)
    else:
        if MEMBERSHIP_RANK[role] > MEMBERSHIP_RANK.get(membership.role, -1):
            membership.role = role
        membership.status = MembershipStatus.ACTIVE.value
    if user.organization_id is None:
        user.organization_id = organization_id
    db.flush()
    mirror_role(db, user)
    db.flush()
    return membership, created


def is_staff_role(role: str) -> bool:
    return role in STAFF_ROLES
