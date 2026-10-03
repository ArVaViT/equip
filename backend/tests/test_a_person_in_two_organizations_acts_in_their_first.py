"""A person in two organizations, whose client names neither, acts in the first they joined.

``acting_organization`` answers "which organization does this request
act inside" for the routes that have no object yet — a course, a cohort,
an invitation being created, the organization's settings being read. With
one membership the answer is obvious; with two it has to come from the
``X-Organization-Id`` header, and no client sends one yet. So on
2026-10-03 a platform admin who sat in UCOAT as its teacher and in a
second school as its director met ``400 organization.ambiguous`` on every
create — and so would a teacher of A who directs B.

Until the header ships (phase 4, with the column), the deprecated
``profiles.organization_id`` breaks the tie: it names the first
organization the person joined, which is where the previous release filed
everything. It is picked only from the candidates the role check already
admitted, so it opens nothing the person could not have asked for by name.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException

from app.api.dependencies import acting_organization
from app.models.organization import MembershipRole, MembershipSource, Organization, OrganizationMember
from app.models.user import User, UserRole

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

A_ID = uuid.UUID("aaaa0000-0000-0000-0000-00000000000a")
B_ID = uuid.UUID("bbbb0000-0000-0000-0000-00000000000b")


def _person(db: Session, role: str, *memberships: tuple[uuid.UUID, str], default: uuid.UUID | None) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        full_name="Somebody",
        role=role,
        organization_id=default,
    )
    db.add(user)
    db.add_all(
        OrganizationMember(
            user_id=user.id,
            organization_id=organization_id,
            role=membership_role,
            joined_via=MembershipSource.MIGRATION.value,
        )
        for organization_id, membership_role in memberships
    )
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def two_schools(db: Session, nobody_belongs_anywhere: None) -> None:
    db.add_all(
        [
            Organization(id=A_ID, slug="school-a", public_name="School A"),
            Organization(id=B_ID, slug="school-b", public_name="School B"),
        ]
    )
    db.commit()


def _ambiguous(db: Session, user: User, role: str = MembershipRole.TEACHER.value) -> None:
    with pytest.raises(HTTPException) as refused:
        acting_organization(db, user, None, role=role)
    assert refused.value.status_code == 400
    assert refused.value.detail["code"] == "organization.ambiguous"


class TestAnAdminInTwoOrganizations:
    def test_acts_in_the_one_the_column_names(self, db: Session, two_schools: None) -> None:
        admin = _person(db, UserRole.ADMIN.value, (A_ID, "teacher"), (B_ID, "director"), default=A_ID)
        assert acting_organization(db, admin, None) == A_ID
        assert acting_organization(db, admin, None, role=MembershipRole.DIRECTOR.value) == A_ID

    def test_is_still_asked_when_the_column_is_empty(self, db: Session, two_schools: None) -> None:
        admin = _person(db, UserRole.ADMIN.value, (A_ID, "teacher"), (B_ID, "teacher"), default=None)
        _ambiguous(db, admin)

    def test_the_header_still_wins(self, db: Session, two_schools: None) -> None:
        admin = _person(db, UserRole.ADMIN.value, (A_ID, "teacher"), (B_ID, "teacher"), default=A_ID)
        assert acting_organization(db, admin, B_ID) == B_ID


class TestATeacherOfAWhoDirectsB:
    def test_teaches_in_the_one_the_column_names(self, db: Session, two_schools: None) -> None:
        person = _person(db, UserRole.DIRECTOR.value, (A_ID, "teacher"), (B_ID, "director"), default=A_ID)
        assert acting_organization(db, person, None, role=MembershipRole.TEACHER.value) == A_ID

    def test_directs_only_where_they_direct(self, db: Session, two_schools: None) -> None:
        # A is the column, but A is not a candidate for a director's action:
        # the one organization they direct answers, as before.
        person = _person(db, UserRole.DIRECTOR.value, (A_ID, "teacher"), (B_ID, "director"), default=A_ID)
        assert acting_organization(db, person, None, role=MembershipRole.DIRECTOR.value) == B_ID

    def test_a_column_naming_a_place_they_left_breaks_no_tie(self, db: Session, two_schools: None) -> None:
        # The column still says A; the person has since been suspended
        # there and teaches in two others. A is not a candidate, so the
        # request is ambiguous, not quietly filed under a place they are
        # no longer in.
        c_id = uuid.uuid4()
        db.add(Organization(id=c_id, slug="school-c", public_name="School C"))
        db.commit()
        person = _person(db, UserRole.TEACHER.value, (B_ID, "teacher"), (c_id, "teacher"), default=A_ID)
        db.add(
            OrganizationMember(
                user_id=person.id,
                organization_id=A_ID,
                role="teacher",
                status="suspended",
                joined_via=MembershipSource.MIGRATION.value,
            )
        )
        db.commit()
        _ambiguous(db, person)
