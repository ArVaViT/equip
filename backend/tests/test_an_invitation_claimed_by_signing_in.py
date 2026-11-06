"""An invitation is accepted by signing in under its address, link or not.

``POST /invitations/claim``. Until 2026-11 the link was the only way in: a
person who read the email and came to the site on their own -- signed up on
``/register``, signed in with Google, or already had an account -- was left a
bare student, and the invitation sat pending until it expired. Every teacher
invited in October 2026 ended up there.

Pinned here: a proven address claims what the link would have given, with the
same checks the link gets; an unproven one claims nothing; and a sign-in with
nothing pending costs no call to Supabase Auth.

Supabase Auth itself is ``tests/_fake_gotrue`` (installed by ``conftest``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.main import app
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.invitation import Invitation, InvitationScope, InvitationStatus
from app.models.organization import OrganizationMember
from app.models.user import User, UserRole
from tests.conftest import ADMIN_ID, TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

    from tests._fake_gotrue import FakeGoTrue

CLAIM = "/api/v1/invitations/claim"
EMAIL = "came-on-their-own@example.com"
COURSE_ID = "acts-1"


def _signed_in_as(db: Session, user: User) -> Iterator[TestClient]:
    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc


@pytest.fixture()
def person(db: Session, admin: User, gotrue: FakeGoTrue) -> User:
    """Somebody who signed up by themselves: a confirmed student in no school."""
    return gotrue.add_account(db, email=EMAIL, confirmed=True)


@pytest.fixture()
def as_person(db: Session, person: User) -> Iterator[TestClient]:
    yield from _signed_in_as(db, person)


def _invitation(
    db: Session,
    *,
    role: str = UserRole.TEACHER.value,
    scope: str = InvitationScope.ORGANIZATION.value,
    course_id: str | None = None,
    email: str = EMAIL,
    **extra: object,
) -> Invitation:
    invitation = Invitation(
        email=email,
        role=role,
        scope=scope,
        course_id=course_id,
        invited_by=ADMIN_ID,
        organization_id=TEST_ORGANIZATION_ID,
        **extra,
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation


def _membership(db: Session, user: User) -> OrganizationMember | None:
    return (
        db.query(OrganizationMember)
        .filter(OrganizationMember.user_id == user.id, OrganizationMember.organization_id == TEST_ORGANIZATION_ID)
        .first()
    )


class TestAProvenAddressClaims:
    def test_a_teacher_invitation_makes_a_teacher_of_whoever_came_on_their_own(
        self, as_person: TestClient, db: Session, person: User
    ) -> None:
        invitation = _invitation(db)

        response = as_person.post(CLAIM)

        assert response.status_code == 200, response.text
        [claimed] = response.json()
        assert claimed["role"] == UserRole.TEACHER.value
        assert claimed["scope"] == InvitationScope.ORGANIZATION.value
        assert claimed["organization_name"]
        db.refresh(invitation)
        assert invitation.status == InvitationStatus.ACCEPTED.value
        assert invitation.accepted_at is not None
        membership = _membership(db, person)
        assert membership is not None
        assert membership.role == UserRole.TEACHER.value
        db.refresh(person)
        assert person.role == UserRole.TEACHER.value

    def test_a_course_invitation_seats_them_on_the_course(
        self, as_person: TestClient, db: Session, person: User
    ) -> None:
        db.add(
            Course(
                id=COURSE_ID,
                status="published",
                access_mode="public",
                created_by=ADMIN_ID,
                source_locale="en",
                organization_id=TEST_ORGANIZATION_ID,
            )
        )
        db.commit()
        _invitation(db, role=UserRole.STUDENT.value, scope=InvitationScope.COURSE.value, course_id=COURSE_ID)

        response = as_person.post(CLAIM)

        assert response.status_code == 200, response.text
        [claimed] = response.json()
        assert claimed["enrolled_course_id"] == COURSE_ID
        assert (
            db.query(Enrollment).filter(Enrollment.user_id == person.id, Enrollment.course_id == COURSE_ID).first()
            is not None
        )

    def test_claiming_twice_grants_once(self, as_person: TestClient, db: Session) -> None:
        _invitation(db)

        assert len(as_person.post(CLAIM).json()) == 1
        assert as_person.post(CLAIM).json() == []


class TestNothingIsClaimed:
    def test_by_an_address_nobody_confirmed(self, db: Session, admin: User, gotrue: FakeGoTrue) -> None:
        unconfirmed = gotrue.add_account(db, email=EMAIL, confirmed=False)
        invitation = _invitation(db)

        for tc in _signed_in_as(db, unconfirmed):
            response = tc.post(CLAIM)

        assert response.status_code == 200
        assert response.json() == []
        db.refresh(invitation)
        assert invitation.status == InvitationStatus.PENDING.value
        assert _membership(db, unconfirmed) is None

    def test_when_the_account_now_holds_another_address(
        self, as_person: TestClient, db: Session, person: User, gotrue: FakeGoTrue
    ) -> None:
        # The profile still says the invited address; Supabase Auth, which
        # is what proves an address, holds a different one.
        account = gotrue.accounts[person.id]
        account.email = "somebody-else@example.com"
        invitation = _invitation(db)

        assert as_person.post(CLAIM).json() == []
        db.refresh(invitation)
        assert invitation.status == InvitationStatus.PENDING.value

    def test_from_an_expired_invitation(self, as_person: TestClient, db: Session, person: User) -> None:
        invitation = _invitation(db, expires_at=datetime.now(UTC) - timedelta(minutes=1))

        assert as_person.post(CLAIM).json() == []
        db.refresh(invitation)
        assert invitation.status == InvitationStatus.PENDING.value
        assert _membership(db, person) is None

    def test_from_a_withdrawn_invitation(self, as_person: TestClient, db: Session, person: User) -> None:
        _invitation(db, status=InvitationStatus.REVOKED.value)

        assert as_person.post(CLAIM).json() == []
        assert _membership(db, person) is None

    def test_from_an_invitation_to_somebody_else(self, as_person: TestClient, db: Session, person: User) -> None:
        _invitation(db, email="another@example.com")

        assert as_person.post(CLAIM).json() == []
        assert _membership(db, person) is None

    def test_and_auth_is_not_asked_when_nothing_is_pending(self, as_person: TestClient, gotrue: FakeGoTrue) -> None:
        gotrue.calls.clear()

        assert as_person.post(CLAIM).json() == []
        assert gotrue.calls == []
