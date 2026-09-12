"""The cases an invitation meets once it is out of our hands.

A token lives seven days in somebody else's inbox. In that time the
course can be deleted, the school can be renamed, the person can be
deactivated, the invitation can be revoked, the same token can be
opened on two devices at once, and the address it was sent to can turn
out to belong to somebody who already has an account — possibly a
teacher, possibly a director, possibly the person who sent it.

Each of these is a question about what the platform owes the person
holding the link. The answers are pinned here, together with the
telemetry that makes them visible: when something refuses, we count
why, because "the link did not work" is not a diagnosis.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException

from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.invitation import Invitation, InvitationScope, InvitationStatus
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.services.invitation_service import (
    accept_invitation,
    create_or_resend_invitation,
    revoke_invitation,
)
from tests.conftest import ADMIN_ID, TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

INVITEE_ID = uuid.UUID("eeeeeeee-4444-5555-6666-eeeeeeeeeeee")
INVITEE_EMAIL = "edge@example.com"
COURSE_ID = "edge-course"


def _course(db: Session, course_id: str = COURSE_ID) -> Course:
    course = Course(
        id=course_id,
        status="published",
        access_mode="public",
        created_by=ADMIN_ID,
        source_locale="en",
        organization_id=TEST_ORGANIZATION_ID,
    )
    db.add(course)
    db.commit()
    return course


def _invitee(db: Session, *, role: str = UserRole.STUDENT.value, email: str = INVITEE_EMAIL) -> User:
    user = User(id=INVITEE_ID, email=email, full_name="Edge Case", role=role)
    db.add(user)
    db.commit()
    db.query(User).filter(User.id == INVITEE_ID).update({User.organization_id: None})
    db.commit()
    db.refresh(user)
    return user


def _invitation(
    db: Session,
    *,
    scope: str = InvitationScope.COURSE.value,
    course_id: str | None = COURSE_ID,
    role: str = UserRole.STUDENT.value,
    email: str = INVITEE_EMAIL,
) -> Invitation:
    invitation = Invitation(
        email=email,
        role=role,
        scope=scope,
        course_id=course_id if scope == InvitationScope.COURSE.value else None,
        token=uuid.uuid4().hex,
        invited_by=ADMIN_ID,
        organization_id=TEST_ORGANIZATION_ID,
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation


def _accept(db: Session, invitation: Invitation, *, email: str = INVITEE_EMAIL) -> Invitation:
    return accept_invitation(
        db,
        token=invitation.token,
        current_user_id=INVITEE_ID,
        current_user_email=email,
    )


def _status_of(exc: HTTPException) -> int:
    """The code the API would answer with — `equip_error` builds an
    ``HTTPException``, so asserting the type is asserting the contract."""
    return exc.status_code


class TestTheLinkArrivesLate:
    def test_an_expired_invitation_is_gone_not_broken(self, db: Session, admin: User) -> None:
        _invitee(db)
        _course(db)
        invitation = _invitation(db)
        invitation.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()

        with pytest.raises(HTTPException) as exc:
            _accept(db, invitation)

        # 410, not 404: the invitation existed, and saying so is what
        # lets the page offer "ask for a new one" instead of "wrong
        # link".
        assert _status_of(exc.value) == 410

    def test_a_revoked_invitation_refuses(self, db: Session, admin: User) -> None:
        _invitee(db)
        _course(db)
        invitation = _invitation(db)
        revoke_invitation(db, invitation_id=invitation.id, actor=admin, organization_id=TEST_ORGANIZATION_ID)

        with pytest.raises(HTTPException) as exc:
            _accept(db, invitation)

        assert _status_of(exc.value) == 409

    def test_expiry_is_read_at_the_boundary_not_by_a_sweep(self, db: Session, admin: User) -> None:
        """A minute before expiry the link still works.

        Expiry is computed on read rather than flipped by a cron, so
        there is no window where a live invitation reads as dead.
        """
        _invitee(db)
        _course(db)
        invitation = _invitation(db)
        invitation.expires_at = datetime.now(UTC) + timedelta(minutes=1)
        db.commit()

        accepted = _accept(db, invitation)

        assert accepted.status == InvitationStatus.ACCEPTED.value


class TestTheAddressIsNotAStranger:
    def test_a_different_account_cannot_spend_it(self, db: Session, admin: User) -> None:
        _invitee(db, email="someone.else@example.com")
        _course(db)
        invitation = _invitation(db)

        with pytest.raises(HTTPException) as exc:
            _accept(db, invitation, email="someone.else@example.com")

        assert _status_of(exc.value) == 403
        assert db.query(Enrollment).filter(Enrollment.user_id == INVITEE_ID).count() == 0

    def test_case_and_whitespace_do_not_decide_who_you_are(self, db: Session, admin: User) -> None:
        """Mail addresses arrive shouted and padded.

        Gmail hands back "Edge@Example.com " often enough that treating
        it as a different person would turn a working invitation into a
        support conversation.
        """
        _invitee(db)
        _course(db)
        invitation = _invitation(db)

        accepted = _accept(db, invitation, email="  Edge@Example.COM  ")

        assert accepted.status == InvitationStatus.ACCEPTED.value

    def test_a_teacher_accepting_a_student_invitation_keeps_teaching(self, db: Session, admin: User) -> None:
        _invitee(db, role=UserRole.TEACHER.value)
        _course(db)
        invitation = _invitation(db, role=UserRole.STUDENT.value)

        _accept(db, invitation)

        user = db.query(User).filter(User.id == INVITEE_ID).one()
        assert user.role == UserRole.TEACHER.value
        # And is still seated on the course they were invited to.
        assert db.query(Enrollment).filter(Enrollment.user_id == INVITEE_ID).count() == 1


class TestTheCourseMoves:
    def test_a_course_deleted_after_the_invitation_refuses_without_consuming_it(self, db: Session, admin: User) -> None:
        _invitee(db)
        course = _course(db)
        invitation = _invitation(db)
        course.deleted_at = datetime.now(UTC)
        db.commit()

        with pytest.raises(HTTPException) as exc:
            _accept(db, invitation)
        assert _status_of(exc.value) == 404

        db.rollback()
        assert (
            db.query(Invitation).filter(Invitation.id == invitation.id).one().status == InvitationStatus.PENDING.value
        )

    def test_being_enrolled_already_is_not_an_error(self, db: Session, admin: User) -> None:
        """Somebody may find the course and enrol before the link arrives.

        The enrolment is idempotent on (user, course, cohort), so the
        invitation lands on the seat they already have rather than
        creating a second one or failing.
        """
        _invitee(db)
        course = _course(db)
        db.add(Enrollment(id=str(uuid.uuid4()), user_id=INVITEE_ID, course_id=course.id, progress=42))
        db.commit()
        invitation = _invitation(db)

        _accept(db, invitation)

        rows = db.query(Enrollment).filter(Enrollment.user_id == INVITEE_ID).all()
        assert len(rows) == 1
        # And the progress they had made is untouched.
        assert rows[0].progress == 42


class TestTwoDevicesOneToken:
    def test_the_second_acceptance_loses(self, db: Session, admin: User) -> None:
        _invitee(db)
        _course(db)
        invitation = _invitation(db)

        _accept(db, invitation)
        with pytest.raises(HTTPException) as exc:
            _accept(db, invitation)

        assert _status_of(exc.value) == 409
        assert db.query(Enrollment).filter(Enrollment.user_id == INVITEE_ID).count() == 1


class TestWhatTheInviterCannotDo:
    def test_a_course_from_another_school_is_not_offerable(self, db: Session, admin: User) -> None:
        other_org = uuid.UUID("dddddddd-7777-7777-7777-dddddddddddd")
        db.add(Organization(id=other_org, slug="other-school", public_name="Other School"))
        db.commit()
        foreign = Course(
            id="foreign-1",
            status="published",
            access_mode="public",
            created_by=ADMIN_ID,
            source_locale="en",
            organization_id=other_org,
        )
        db.add(foreign)
        db.commit()

        with pytest.raises(HTTPException) as exc:
            create_or_resend_invitation(
                db,
                email=INVITEE_EMAIL,
                role=UserRole.STUDENT.value,
                invited_by=ADMIN_ID,
                organization_id=TEST_ORGANIZATION_ID,
                scope=InvitationScope.COURSE.value,
                course_id=foreign.id,
            )

        assert _status_of(exc.value) == 404

    def test_a_course_scope_without_a_course_is_refused(self, db: Session, admin: User) -> None:
        with pytest.raises(HTTPException) as exc:
            create_or_resend_invitation(
                db,
                email=INVITEE_EMAIL,
                role=UserRole.STUDENT.value,
                invited_by=ADMIN_ID,
                organization_id=TEST_ORGANIZATION_ID,
                scope=InvitationScope.COURSE.value,
                course_id=None,
            )

        assert _status_of(exc.value) == 404

    def test_a_course_on_a_non_course_scope_is_refused(self, db: Session, admin: User) -> None:
        _course(db)

        with pytest.raises(HTTPException) as exc:
            create_or_resend_invitation(
                db,
                email=INVITEE_EMAIL,
                role=UserRole.STUDENT.value,
                invited_by=ADMIN_ID,
                organization_id=TEST_ORGANIZATION_ID,
                scope=InvitationScope.ORGANIZATION.value,
                course_id=COURSE_ID,
            )

        assert _status_of(exc.value) == 422


class TestTheTelemetry:
    """Every refusal is counted, with the reason on the tag.

    Without this, "the link did not work" arrives as a message from a
    person rather than as a number on a dashboard, and the difference
    between an expired link, a revoked one and the wrong mailbox is
    invisible.
    """

    def _metric_lines(self, caplog: pytest.LogCaptureFixture) -> list[str]:
        return [r.getMessage() for r in caplog.records if r.name == "equip.metric"]

    def test_accepting_is_counted_with_what_it_granted(
        self, db: Session, admin: User, caplog: pytest.LogCaptureFixture
    ) -> None:
        _invitee(db)
        _course(db)
        invitation = _invitation(db)

        with caplog.at_level(logging.INFO, logger="equip.metric"):
            _accept(db, invitation)

        accepted = [m for m in self._metric_lines(caplog) if "equip.invitations.accepted_total" in m]
        assert len(accepted) == 1
        assert "scope=course" in accepted[0]
        assert "joined_organization=true" in accepted[0]

    @pytest.mark.parametrize(
        ("prepare", "reason"),
        [
            ("expired", "expired"),
            ("revoked", "already_used"),
            ("mismatch", "email_mismatch"),
        ],
    )
    def test_each_refusal_names_itself(
        self, db: Session, admin: User, caplog: pytest.LogCaptureFixture, prepare: str, reason: str
    ) -> None:
        _invitee(db, email="someone.else@example.com" if prepare == "mismatch" else INVITEE_EMAIL)
        _course(db)
        invitation = _invitation(db)
        if prepare == "expired":
            invitation.expires_at = datetime.now(UTC) - timedelta(minutes=1)
            db.commit()
        elif prepare == "revoked":
            revoke_invitation(db, invitation_id=invitation.id, actor=admin, organization_id=TEST_ORGANIZATION_ID)

        with caplog.at_level(logging.INFO, logger="equip.metric"), pytest.raises(HTTPException):
            _accept(db, invitation, email="someone.else@example.com" if prepare == "mismatch" else INVITEE_EMAIL)

        refused = [m for m in self._metric_lines(caplog) if "equip.invitations.refused_total" in m]
        assert refused, "a refusal with no metric is a support ticket waiting to happen"
        assert f"reason={reason}" in refused[0]

    def test_creating_is_counted_and_a_resend_is_told_apart(
        self, db: Session, admin: User, caplog: pytest.LogCaptureFixture
    ) -> None:
        _course(db)

        with caplog.at_level(logging.INFO, logger="equip.metric"):
            create_or_resend_invitation(
                db,
                email=INVITEE_EMAIL,
                role=UserRole.STUDENT.value,
                invited_by=ADMIN_ID,
                organization_id=TEST_ORGANIZATION_ID,
                scope=InvitationScope.COURSE.value,
                course_id=COURSE_ID,
            )
            create_or_resend_invitation(
                db,
                email=INVITEE_EMAIL,
                role=UserRole.STUDENT.value,
                invited_by=ADMIN_ID,
                organization_id=TEST_ORGANIZATION_ID,
                scope=InvitationScope.COURSE.value,
                course_id=COURSE_ID,
            )

        created = [m for m in self._metric_lines(caplog) if "equip.invitations.created_total" in m]
        assert len(created) == 2
        assert "kind=new" in created[0]
        # A resend is not a second invitation, and counting it as one
        # would make the acceptance rate look half as good as it is.
        assert "kind=resend" in created[1]


class TestTheInvitationComesFromTheTeacher:
    """A course invitation is written by whoever owns the course.

    The person receiving it is about to study under that teacher, and an
    invitation signed by an administrator they have never met is a worse
    invitation. What a teacher may NOT do is mint another teacher —
    that would be an escalation with extra steps — so a teaching role
    stays with a director.
    """

    def test_a_teacher_may_invite_a_student_onto_their_own_course(self, db: Session, admin: User) -> None:
        teacher = User(
            id=uuid.UUID("aaaaaaaa-1111-1111-1111-aaaaaaaaaaaa"),
            email="teacher@example.com",
            full_name="Teacher",
            role=UserRole.TEACHER.value,
        )
        db.add(teacher)
        db.commit()
        course = Course(
            id="teachers-own",
            status="published",
            access_mode="public",
            created_by=teacher.id,
            source_locale="en",
            organization_id=TEST_ORGANIZATION_ID,
        )
        db.add(course)
        db.commit()

        invitation, is_new = create_or_resend_invitation(
            db,
            email=INVITEE_EMAIL,
            role=UserRole.STUDENT.value,
            invited_by=teacher.id,
            organization_id=TEST_ORGANIZATION_ID,
            scope=InvitationScope.COURSE.value,
            course_id=course.id,
        )

        assert is_new is True
        assert invitation.invited_by == teacher.id


class TestTheLinkIsSpentOnce:
    """Accepting ends the invitation, whoever the person turned out to be.

    Two paths reach the same place: somebody who had no account and made
    one from the link, and somebody who was already signed in. Both end
    with the invitation accepted and the link refusing a second use.
    """

    def test_an_account_that_already_existed_spends_it_too(self, db: Session, admin: User) -> None:
        # No registration step here: this person already had an account
        # and simply clicked the link.
        _invitee(db)
        _course(db)
        invitation = _invitation(db)

        accepted = _accept(db, invitation)

        assert accepted.status == InvitationStatus.ACCEPTED.value
        assert accepted.accepted_at is not None
        assert db.query(Enrollment).filter(Enrollment.user_id == INVITEE_ID).count() == 1

        with pytest.raises(HTTPException) as exc:
            _accept(db, invitation)
        assert _status_of(exc.value) == 409

    def test_the_seat_is_what_makes_it_accepted(self, db: Session, admin: User) -> None:
        """For a course invitation the two are the same event.

        The enrolment and the status flip land in one transaction, so
        there is no state where the invitation reads as used and the
        person is not on the course, or the other way round.
        """
        _invitee(db)
        _course(db)
        invitation = _invitation(db)

        _accept(db, invitation)

        row = db.query(Invitation).filter(Invitation.id == invitation.id).one()
        enrolment = db.query(Enrollment).filter(Enrollment.user_id == INVITEE_ID).one()
        assert row.status == InvitationStatus.ACCEPTED.value
        assert enrolment.course_id == COURSE_ID
