"""A person invited twice should still hold one link.

On 2026-09-12 somebody with a pending invitation to a course was invited
to the school as a nudge, and ended up with two live invitations. The
two grant different things: the course link enrols them in the course,
the school link only puts them in the school. Whichever they pressed
decided where they landed, and nothing in either email said so.

The dedupe key was ``(organization, email, role, course)``, and a school
invitation has no course — so by that key the two were unrelated rows.
They are not unrelated: a course invitation already carries school
membership. The scopes are nested, and this file holds them nested.

Two invitations to two *different* courses remain two invitations. Those
are genuinely different offers, and each email names its course.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from fastapi import HTTPException

from app.models.course import Course
from app.models.invitation import Invitation, InvitationScope, InvitationStatus
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.services.invitation_service import _subsumes_scope, create_or_resend_invitation
from tests.conftest import ADMIN_ID, TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

INVITEE = "kuryshev@example.com"


@pytest.fixture()
def courses(db: Session, admin: User) -> tuple[str, str]:
    for course_id in ("preaching-1", "preaching-2"):
        db.add(
            Course(
                id=course_id,
                status="published",
                access_mode="public",
                created_by=ADMIN_ID,
                source_locale="ru",
                organization_id=TEST_ORGANIZATION_ID,
            )
        )
    db.commit()
    return "preaching-1", "preaching-2"


def _invite(db: Session, *, scope: str, course_id: str | None = None):
    return create_or_resend_invitation(
        db,
        email=INVITEE,
        role=UserRole.STUDENT.value,
        invited_by=ADMIN_ID,
        organization_id=TEST_ORGANIZATION_ID,
        scope=scope,
        course_id=course_id,
    )


def _live(db: Session) -> list[Invitation]:
    return (
        db.query(Invitation)
        .filter(
            Invitation.email == INVITEE,
            Invitation.status == InvitationStatus.PENDING.value,
        )
        .all()
    )


class TestTheSchoolIsAlreadyInTheCourse:
    def test_inviting_to_the_school_resends_the_course_invitation(self, db: Session, courses) -> None:
        """The exact shape of the defect, in one test."""
        first, _ = courses
        course_invitation, _ = _invite(db, scope=InvitationScope.COURSE.value, course_id=first)

        again, is_new = _invite(db, scope=InvitationScope.ORGANIZATION.value)

        assert is_new is False
        assert again.id == course_invitation.id
        assert len(_live(db)) == 1

    def test_the_token_already_sent_is_the_token_resent(self, db: Session, courses) -> None:
        """A link somebody already has in their inbox must keep working."""
        first, _ = courses
        original, _ = _invite(db, scope=InvitationScope.COURSE.value, course_id=first)
        token, expires = original.token, original.expires_at

        again, _ = _invite(db, scope=InvitationScope.ORGANIZATION.value)

        assert again.token == token
        assert again.expires_at == expires

    def test_inviting_to_a_course_retires_a_bare_school_invitation(self, db: Session, courses) -> None:
        """The other direction: the new offer grants strictly more.

        Leaving the school invitation live would leave the weaker link in
        the same inbox, one press away from the wrong destination.
        """
        first, _ = courses
        school_invitation, _ = _invite(db, scope=InvitationScope.ORGANIZATION.value)

        course_invitation, is_new = _invite(db, scope=InvitationScope.COURSE.value, course_id=first)

        assert is_new is True
        assert course_invitation.id != school_invitation.id
        db.refresh(school_invitation)
        assert school_invitation.status == InvitationStatus.REVOKED.value
        assert [row.id for row in _live(db)] == [course_invitation.id]


class TestWhatStaysSeparate:
    def test_two_courses_are_two_offers(self, db: Session, courses) -> None:
        first, second = courses
        one, _ = _invite(db, scope=InvitationScope.COURSE.value, course_id=first)

        other, is_new = _invite(db, scope=InvitationScope.COURSE.value, course_id=second)

        assert is_new is True
        assert {row.id for row in _live(db)} == {one.id, other.id}

    def test_the_same_course_twice_is_a_resend(self, db: Session, courses) -> None:
        first, _ = courses
        one, _ = _invite(db, scope=InvitationScope.COURSE.value, course_id=first)

        again, is_new = _invite(db, scope=InvitationScope.COURSE.value, course_id=first)

        assert is_new is False
        assert again.id == one.id

    def test_a_different_role_is_a_different_invitation(self, db: Session, courses) -> None:
        """Role is part of the offer: student and teacher are not the same seat."""
        _invite(db, scope=InvitationScope.ORGANIZATION.value)

        as_teacher, is_new = create_or_resend_invitation(
            db,
            email=INVITEE,
            role=UserRole.TEACHER.value,
            invited_by=ADMIN_ID,
            organization_id=TEST_ORGANIZATION_ID,
            scope=InvitationScope.ORGANIZATION.value,
        )

        assert is_new is True
        assert len(_live(db)) == 2
        assert as_teacher.role == UserRole.TEACHER.value

    def test_another_school_is_another_invitation(self, db: Session, courses) -> None:
        """A second school's offer is its own, and must not be swallowed."""
        _invite(db, scope=InvitationScope.ORGANIZATION.value)
        elsewhere = uuid.uuid4()
        db.add(Organization(id=elsewhere, slug="elsewhere", public_name="Elsewhere"))
        db.commit()

        other, is_new = create_or_resend_invitation(
            db,
            email=INVITEE,
            role=UserRole.STUDENT.value,
            invited_by=ADMIN_ID,
            organization_id=elsewhere,
            scope=InvitationScope.ORGANIZATION.value,
        )

        assert is_new is True
        assert other.organization_id == elsewhere
        assert len(_live(db)) == 2


class TestThePlatformIsOutsideTheOrder:
    """A platform invitation grants an account and nothing else (2026-10-03),
    so it sits in no school's offer and no school's offer sits in it. It used
    to rank above everything, which let it retire a director's invitation or
    be resent in the director's name."""

    @pytest.mark.parametrize(
        ("outer", "outer_course", "inner", "inner_course", "covers"),
        [
            ("platform", None, "platform", None, True),
            ("platform", None, "organization", None, False),
            ("platform", None, "course", "preaching-1", False),
            ("organization", None, "platform", None, False),
            ("course", "preaching-1", "platform", None, False),
            # The school's own order is untouched.
            ("course", "preaching-1", "organization", None, True),
            ("organization", None, "course", "preaching-1", False),
        ],
    )
    def test_the_platform_covers_only_itself(
        self, outer: str, outer_course: str | None, inner: str, inner_course: str | None, covers: bool
    ) -> None:
        assert _subsumes_scope(outer, outer_course, inner, inner_course) is covers

    def test_a_platform_row_is_not_what_a_school_resends(self, db: Session, admin: User) -> None:
        platform, _ = _invite(db, scope=InvitationScope.PLATFORM.value)

        with pytest.raises(HTTPException) as refused:
            _invite(db, scope=InvitationScope.ORGANIZATION.value)

        # Refused rather than resent, and refused rather than retired: the
        # unique index does not carry the scope, so the two cannot both be
        # pending under one organization yet.
        assert refused.value.status_code == 409
        db.refresh(platform)
        assert platform.status == InvitationStatus.PENDING.value
        assert [row.id for row in _live(db)] == [platform.id]
