"""Accepting an invitation grants everything it promised, and nothing else.

Until 2026-09-12 acceptance wrote one field — the role — and stopped.
The invited teacher ended up with a role and no school: 403 from
``organization_of`` on every organizational route and an empty
catalogue. The invited student could not reach an institute course for
the same reason. And a director who accepted a student invitation was
demoted by it, because the write was unconditional.

Since 2026-10-03 what acceptance grants is a *membership*: a row in
``organization_members`` for the inviting organization, in the offered
role, never lowered within that organization — and nothing about any other
organization the person is in. ``profiles.role`` follows as the mirror of
the highest membership.

These tests pin the writes that land together, the ones that must not
happen, and the order in which refusals come — a person who meets a 404
must still hold their invitation afterwards.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_optional_user
from app.core.database import get_db
from app.main import app
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.invitation import Invitation, InvitationScope, InvitationStatus
from app.models.organization import MembershipSource, Organization, OrganizationMember
from app.models.user import User, UserRole
from app.services.invitation_service import accept_invitation, create_or_resend_invitation
from tests.conftest import ADMIN_ID, TEST_ORGANIZATION_ID, leave_every_organization

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

INVITATIONS_PREFIX = "/api/v1/invitations"
INVITEE_ID = uuid.UUID("eeeeeeee-1111-2222-3333-eeeeeeeeeeee")
INVITEE_EMAIL = "newcomer@example.com"
OTHER_ORGANIZATION_ID = uuid.UUID("dddddddd-9999-9999-9999-dddddddddddd")


def _course(db: Session, course_id: str = "preaching-1", *, organization_id: uuid.UUID | None = None) -> Course:
    course = Course(
        id=course_id,
        status="published",
        access_mode="public",
        created_by=ADMIN_ID,
        source_locale="en",
        organization_id=organization_id or TEST_ORGANIZATION_ID,
    )
    db.add(course)
    db.commit()
    return course


def _invitee(db: Session, *, role: str = UserRole.STUDENT.value, organization_id: uuid.UUID | None = None) -> User:
    """An account under the invited address: homeless, or a member of exactly
    ``organization_id`` in ``role``.

    conftest's ``before_flush`` listener files every new user under the
    test organization, which is right for the tests it was written for and
    wrong for these: an invitee who is already in the school would make
    "accepting grants membership" pass without the code doing anything.
    So the listener's work is undone, which is also the true shape of a
    person who just signed up — ``handle_new_user`` sets nothing — and the
    one membership the test wants is written by hand.
    """
    user = User(
        id=INVITEE_ID,
        email=INVITEE_EMAIL,
        full_name="Newcomer",
        role=role,
    )
    db.add(user)
    db.commit()
    leave_every_organization(db, INVITEE_ID)
    if organization_id is not None:
        db.add(
            OrganizationMember(
                user_id=INVITEE_ID,
                organization_id=organization_id,
                # Platform staff hold no membership role; they sit somewhere as a teacher.
                role=UserRole.TEACHER.value if role == UserRole.ADMIN.value else role,
                joined_via=MembershipSource.MIGRATION.value,
            )
        )
        db.query(User).filter(User.id == INVITEE_ID).update({User.organization_id: organization_id})
        db.commit()
    db.refresh(user)
    assert user.organization_id == organization_id
    return user


def _memberships(db: Session) -> dict[uuid.UUID, str]:
    """``{organization_id: role}`` of the invitee's active memberships."""
    return {
        m.organization_id: m.role
        for m in db.query(OrganizationMember).filter(
            OrganizationMember.user_id == INVITEE_ID, OrganizationMember.status == "active"
        )
    }


def _invitation(
    db: Session,
    *,
    scope: str = InvitationScope.ORGANIZATION.value,
    course_id: str | None = None,
    role: str = UserRole.STUDENT.value,
    organization_id: uuid.UUID | None = None,
) -> Invitation:
    invitation = Invitation(
        email=INVITEE_EMAIL,
        role=role,
        scope=scope,
        course_id=course_id,
        token=uuid.uuid4().hex,
        invited_by=ADMIN_ID,
        organization_id=organization_id or TEST_ORGANIZATION_ID,
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation


def _accept(db: Session, invitation: Invitation) -> Invitation:
    return accept_invitation(
        db,
        token=invitation.token,
        current_user_id=INVITEE_ID,
        current_user_email=INVITEE_EMAIL,
    )


class TestWhatAcceptingGrants:
    def test_an_organization_invitation_puts_the_person_in_the_school(self, db: Session, admin: User) -> None:
        _invitee(db)
        invitation = _invitation(db)

        _accept(db, invitation)

        assert _memberships(db) == {TEST_ORGANIZATION_ID: UserRole.STUDENT.value}
        membership = db.query(OrganizationMember).filter(OrganizationMember.user_id == INVITEE_ID).one()
        assert (membership.joined_via, membership.invited_by) == (MembershipSource.INVITATION.value, ADMIN_ID)
        # The deprecated column is still written for the first organization,
        # so a rollback to the previous backend finds the person in place.
        assert db.query(User).filter(User.id == INVITEE_ID).one().organization_id == TEST_ORGANIZATION_ID
        assert invitation.status == InvitationStatus.ACCEPTED.value

    def test_a_course_invitation_seats_them_on_the_course(self, db: Session, admin: User) -> None:
        _invitee(db)
        course = _course(db)
        invitation = _invitation(db, scope=InvitationScope.COURSE.value, course_id=course.id)

        _accept(db, invitation)

        enrollment = db.query(Enrollment).filter(Enrollment.user_id == INVITEE_ID).one()
        assert enrollment.course_id == course.id
        assert enrollment.progress == 0
        assert _memberships(db) == {TEST_ORGANIZATION_ID: UserRole.STUDENT.value}

    def test_a_platform_invitation_grants_no_membership(self, db: Session, admin: User) -> None:
        # The scope that exists for "you should have an account here",
        # with no school behind it yet.
        _invitee(db)
        invitation = _invitation(db, scope=InvitationScope.PLATFORM.value)

        _accept(db, invitation)

        assert _memberships(db) == {}
        assert db.query(User).filter(User.id == INVITEE_ID).one().organization_id is None

    def test_the_role_moves_up(self, db: Session, admin: User) -> None:
        _invitee(db, role=UserRole.STUDENT.value)
        invitation = _invitation(db, role=UserRole.TEACHER.value)

        _accept(db, invitation)

        assert _memberships(db) == {TEST_ORGANIZATION_ID: UserRole.TEACHER.value}
        assert db.query(User).filter(User.id == INVITEE_ID).one().role == UserRole.TEACHER.value

    def test_a_student_already_there_is_raised_to_teacher(self, db: Session, admin: User) -> None:
        """A second invitation into the same organization raises the one
        row; it does not add a second."""
        _invitee(db, role=UserRole.STUDENT.value, organization_id=TEST_ORGANIZATION_ID)
        invitation = _invitation(db, role=UserRole.TEACHER.value)

        _accept(db, invitation)

        assert _memberships(db) == {TEST_ORGANIZATION_ID: UserRole.TEACHER.value}
        assert db.query(User).filter(User.id == INVITEE_ID).one().role == UserRole.TEACHER.value

    def test_the_role_never_moves_down(self, db: Session, admin: User) -> None:
        # A director accepting a student invitation to one of their own
        # courses used to be demoted to student by it.
        _invitee(db, role=UserRole.DIRECTOR.value, organization_id=TEST_ORGANIZATION_ID)
        course = _course(db)
        invitation = _invitation(
            db,
            scope=InvitationScope.COURSE.value,
            course_id=course.id,
            role=UserRole.STUDENT.value,
        )

        _accept(db, invitation)

        user = db.query(User).filter(User.id == INVITEE_ID).one()
        assert user.role == UserRole.DIRECTOR.value
        assert _memberships(db) == {TEST_ORGANIZATION_ID: UserRole.DIRECTOR.value}
        # ...and the rest of the invitation still happened.
        assert db.query(Enrollment).filter(Enrollment.user_id == INVITEE_ID).count() == 1

    @pytest.mark.parametrize("role", [UserRole.DIRECTOR.value, UserRole.TEACHER.value])
    def test_a_higher_role_elsewhere_gains_a_second_membership(self, db: Session, admin: User, role: str) -> None:
        """A director or teacher of school B offered a student seat in school
        A is now a student of A *and* still what they were in B. While an
        account sat in one organization this had to be refused (2026-10-03,
        ``invitation.other_school``): keeping the role carried it into A,
        dropping it cost them B. Neither happens now — the roles live in the
        rows, and ``profiles.role`` reads the highest.
        """
        db.add(Organization(id=OTHER_ORGANIZATION_ID, slug="other-school", public_name="Other School"))
        db.commit()
        _invitee(db, role=role, organization_id=OTHER_ORGANIZATION_ID)
        invitation = _invitation(db, role=UserRole.STUDENT.value)

        _accept(db, invitation)

        assert _memberships(db) == {OTHER_ORGANIZATION_ID: role, TEST_ORGANIZATION_ID: UserRole.STUDENT.value}
        user = db.query(User).filter(User.id == INVITEE_ID).one()
        assert user.role == role, "the platform-wide role is the highest membership, not the latest"
        # The deprecated column names the first organization and is not moved.
        assert user.organization_id == OTHER_ORGANIZATION_ID
        assert invitation.status == InvitationStatus.ACCEPTED.value

    def test_a_student_of_another_school_is_now_in_both(self, db: Session, admin: User) -> None:
        db.add(Organization(id=OTHER_ORGANIZATION_ID, slug="other-school", public_name="Other School"))
        db.commit()
        _invitee(db, organization_id=OTHER_ORGANIZATION_ID)
        invitation = _invitation(db, role=UserRole.STUDENT.value)

        _accept(db, invitation)

        assert _memberships(db) == {
            OTHER_ORGANIZATION_ID: UserRole.STUDENT.value,
            TEST_ORGANIZATION_ID: UserRole.STUDENT.value,
        }
        assert db.query(User).filter(User.id == INVITEE_ID).one().role == UserRole.STUDENT.value

    def test_a_director_of_this_school_keeps_directing(self, db: Session, admin: User) -> None:
        _invitee(db, role=UserRole.DIRECTOR.value, organization_id=TEST_ORGANIZATION_ID)
        invitation = _invitation(db, role=UserRole.STUDENT.value)

        _accept(db, invitation)

        assert db.query(User).filter(User.id == INVITEE_ID).one().role == UserRole.DIRECTOR.value

    def test_staff_keep_their_role_wherever_they_sit(self, db: Session, admin: User) -> None:
        db.add(Organization(id=OTHER_ORGANIZATION_ID, slug="other-school", public_name="Other School"))
        db.commit()
        _invitee(db, role=UserRole.ADMIN.value, organization_id=OTHER_ORGANIZATION_ID)
        invitation = _invitation(db, role=UserRole.STUDENT.value)

        _accept(db, invitation)

        assert db.query(User).filter(User.id == INVITEE_ID).one().role == UserRole.ADMIN.value
        # Staff sit in organizations like anyone else; the platform role is not a membership.
        assert _memberships(db) == {
            OTHER_ORGANIZATION_ID: UserRole.TEACHER.value,
            TEST_ORGANIZATION_ID: UserRole.STUDENT.value,
        }


class TestWhatAcceptingRefuses:
    def test_a_vanished_course_does_not_burn_the_invitation(self, db: Session, admin: User) -> None:
        """The refusal comes before anything is written.

        A course can be deleted in the seven days a token is alive. The
        person clicking the link must meet a 404 *and still hold the
        invitation* — otherwise a teacher's cleanup silently consumes
        somebody's only way in.
        """
        _invitee(db)
        course = _course(db)
        invitation = _invitation(db, scope=InvitationScope.COURSE.value, course_id=course.id)

        course.deleted_at = datetime.now(UTC)
        db.commit()

        with pytest.raises(Exception) as exc:
            _accept(db, invitation)
        assert getattr(exc.value, "status_code", None) == 404

        db.rollback()
        still = db.query(Invitation).filter(Invitation.id == invitation.id).one()
        assert still.status == InvitationStatus.PENDING.value
        assert still.accepted_at is None
        assert db.query(Enrollment).filter(Enrollment.user_id == INVITEE_ID).count() == 0

    def test_a_second_click_loses(self, db: Session, admin: User) -> None:
        _invitee(db)
        course = _course(db)
        invitation = _invitation(db, scope=InvitationScope.COURSE.value, course_id=course.id)

        _accept(db, invitation)
        with pytest.raises(Exception) as exc:
            _accept(db, invitation)
        assert getattr(exc.value, "status_code", None) == 409

        # And the enrolment is not doubled by the attempt.
        assert db.query(Enrollment).filter(Enrollment.user_id == INVITEE_ID).count() == 1

    def test_a_course_from_another_school_cannot_be_offered(self, db: Session, admin: User) -> None:
        db.add(Organization(id=OTHER_ORGANIZATION_ID, slug="other-school", public_name="Other School"))
        db.commit()
        foreign = _course(db, "foreign-course", organization_id=OTHER_ORGANIZATION_ID)

        with pytest.raises(Exception) as exc:
            create_or_resend_invitation(
                db,
                email=INVITEE_EMAIL,
                role=UserRole.STUDENT.value,
                invited_by=ADMIN_ID,
                organization_id=TEST_ORGANIZATION_ID,
                scope=InvitationScope.COURSE.value,
                course_id=foreign.id,
            )
        # 404, not 403: whether that course exists is not this school's
        # business to learn.
        assert getattr(exc.value, "status_code", None) == 404


class TestTheDedupKeyKnowsTheSchool:
    def test_two_schools_can_invite_the_same_person(self, db: Session, admin: User) -> None:
        """The lookup used to match ``(email, role)`` globally.

        The second school got the first school's row back and mailed out
        its token — an invitation into a school nobody had offered.
        """
        db.add(Organization(id=OTHER_ORGANIZATION_ID, slug="other-school", public_name="Other School"))
        db.commit()

        first, first_is_new = create_or_resend_invitation(
            db,
            email=INVITEE_EMAIL,
            role=UserRole.STUDENT.value,
            invited_by=ADMIN_ID,
            organization_id=TEST_ORGANIZATION_ID,
        )
        second, second_is_new = create_or_resend_invitation(
            db,
            email=INVITEE_EMAIL,
            role=UserRole.STUDENT.value,
            invited_by=ADMIN_ID,
            organization_id=OTHER_ORGANIZATION_ID,
        )

        assert first_is_new and second_is_new
        assert first.id != second.id
        assert first.token != second.token
        assert second.organization_id == OTHER_ORGANIZATION_ID

    def test_one_school_inviting_twice_to_the_same_course_resends(self, db: Session, admin: User) -> None:
        course = _course(db)
        first, first_is_new = create_or_resend_invitation(
            db,
            email=INVITEE_EMAIL,
            role=UserRole.STUDENT.value,
            invited_by=ADMIN_ID,
            organization_id=TEST_ORGANIZATION_ID,
            scope=InvitationScope.COURSE.value,
            course_id=course.id,
        )
        second, second_is_new = create_or_resend_invitation(
            db,
            email=INVITEE_EMAIL,
            role=UserRole.STUDENT.value,
            invited_by=ADMIN_ID,
            organization_id=TEST_ORGANIZATION_ID,
            scope=InvitationScope.COURSE.value,
            course_id=course.id,
        )

        assert first_is_new is True
        assert second_is_new is False
        assert first.id == second.id
        # A resend keeps the original token and clock, so a link already
        # shared stays the one that works.
        assert first.token == second.token

    def test_two_courses_are_two_invitations(self, db: Session, admin: User) -> None:
        first_course = _course(db, "preaching-1")
        second_course = _course(db, "teaching-1")

        first, _ = create_or_resend_invitation(
            db,
            email=INVITEE_EMAIL,
            role=UserRole.STUDENT.value,
            invited_by=ADMIN_ID,
            organization_id=TEST_ORGANIZATION_ID,
            scope=InvitationScope.COURSE.value,
            course_id=first_course.id,
        )
        second, second_is_new = create_or_resend_invitation(
            db,
            email=INVITEE_EMAIL,
            role=UserRole.STUDENT.value,
            invited_by=ADMIN_ID,
            organization_id=TEST_ORGANIZATION_ID,
            scope=InvitationScope.COURSE.value,
            course_id=second_course.id,
        )

        assert second_is_new is True
        assert first.id != second.id


class TestThePreviewSaysWhereItLeads:
    @pytest.fixture()
    def anon(self, db: Session):
        def _override_db():
            yield db

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_optional_user, None)
        with TestClient(app, raise_server_exceptions=False) as tc:
            yield tc
        app.dependency_overrides.clear()

    def test_a_course_invitation_names_the_course(self, anon: TestClient, db: Session, admin: User) -> None:
        from app.models.content_version import ContentVersion

        course = _course(db)
        db.add(
            ContentVersion(
                entity_type="course",
                entity_id=course.id,
                field="title",
                locale="en",
                text="Preaching Course I",
                origin="human",
                status="ok",
            )
        )
        db.commit()
        invitation = _invitation(db, scope=InvitationScope.COURSE.value, course_id=course.id)

        body = anon.post(f"{INVITATIONS_PREFIX}/preview", json={"token": invitation.token}).json()

        assert body["scope"] == "course"
        assert body["course_title"] == "Preaching Course I"

    def test_an_organization_invitation_names_no_course(self, anon: TestClient, db: Session, admin: User) -> None:
        invitation = _invitation(db)

        body = anon.post(f"{INVITATIONS_PREFIX}/preview", json={"token": invitation.token}).json()

        assert body["scope"] == "organization"
        assert body["course_title"] is None
