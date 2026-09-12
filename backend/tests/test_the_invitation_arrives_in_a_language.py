"""The invitation email: what it says, in whose language, and how it looks.

Two things this file is here to stop coming back.

The first is the language. An invitation used to default to the
platform's fallback, so German and Ukrainian schools mailed their own
people in English. There is no preference to read — the invited person
has no account — so the language is the inviting person's, and every
locale must produce its own text rather than English with a translated
button.

The second is the palette. The August palette fix landed in the Auth
emails, where a test forbids the retired colours, and never reached the
invitation, which had no test at all: it kept a blue button for a month
after the product stopped being blue. That guard now exists on this
side too, which is the only reason the two can stay in step.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from app.models.content_version import ContentVersion
from app.models.course import Course
from app.models.invitation import Invitation, InvitationScope
from app.models.organization import Organization
from app.models.user import UserRole
from app.services.email import theme
from app.services.email.invitation import build_invitation_message, invitation_subject
from app.services.email.render import render
from app.services.invitation_service import _inviter_locale
from tests.conftest import ADMIN_ID, TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User

ACCEPT_URL = "https://equipbible.com/invite/accept?token=abc123"
COURSE_ID = "preaching-1"


def _invitation(db: Session, *, scope: str = InvitationScope.ORGANIZATION.value, course_id: str | None = None):
    invitation = Invitation(
        email="newcomer@example.com",
        role=UserRole.STUDENT.value,
        scope=scope,
        course_id=course_id,
        token=uuid.uuid4().hex,
        invited_by=ADMIN_ID,
        organization_id=TEST_ORGANIZATION_ID,
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation


def _course_with_title(db: Session, title: str = "Preaching Course I", locale: str = "en") -> Course:
    course = Course(
        id=COURSE_ID,
        status="published",
        access_mode="public",
        created_by=ADMIN_ID,
        source_locale=locale,
        image_url="/img/course-assets/preaching-1/cover.png",
    )
    db.add(course)
    db.add(
        ContentVersion(
            entity_type="course",
            entity_id=COURSE_ID,
            field="title",
            locale=locale,
            text=title,
            origin="human",
            status="ok",
        )
    )
    db.commit()
    return course


def _school(db: Session, name: str = "UCOAT") -> Organization:
    organization = db.query(Organization).filter(Organization.id == TEST_ORGANIZATION_ID).one()
    organization.public_name = name
    db.commit()
    return organization


class TestWhoseLanguage:
    @pytest.mark.parametrize("locale", ["ru", "en", "de", "uk"])
    def test_the_inviter_decides(self, db: Session, admin: User, locale: str) -> None:
        admin.preferred_locale = locale
        db.commit()
        assert _inviter_locale(db, admin.id) == locale

    def test_no_inviter_falls_back_to_english(self, db: Session) -> None:
        assert _inviter_locale(db, None) == "en"


class TestWhatItSays:
    def test_a_course_invitation_names_the_course_the_school_and_the_inviter(
        self, db: Session, admin: User
    ) -> None:
        _school(db)
        _course_with_title(db)
        invitation = _invitation(db, scope=InvitationScope.COURSE.value, course_id=COURSE_ID)

        message = build_invitation_message(
            db, invitation, accept_url=ACCEPT_URL, locale="ru", inviter_name="Дмитрий Константинов"
        )

        assert message.title == "Preaching Course I"
        assert message.org_name == "UCOAT"
        assert "Дмитрий Константинов" in message.lede
        assert "UCOAT" in message.lede
        # The old copy said none of this: "You've been invited to Equip
        # as a student" was the whole of it.
        assert invitation_subject(message, "ru", invitation.scope).startswith("Приглашение на курс")

    def test_the_banner_is_the_course_cover_made_absolute(self, db: Session, admin: User) -> None:
        _course_with_title(db)
        invitation = _invitation(db, scope=InvitationScope.COURSE.value, course_id=COURSE_ID)

        message = build_invitation_message(db, invitation, accept_url=ACCEPT_URL, locale="en", inviter_name=None)

        # Stored as a path the app proxies; a mail client has no origin
        # to resolve that against.
        assert message.banner_url == "https://equipbible.com/img/course-assets/preaching-1/cover.png"

    def test_an_organization_invitation_has_no_banner(self, db: Session, admin: User) -> None:
        _school(db)
        invitation = _invitation(db)

        message = build_invitation_message(db, invitation, accept_url=ACCEPT_URL, locale="en", inviter_name="Vadym")

        assert message.banner_url is None
        assert message.title == "UCOAT"

    def test_the_lesson_count_is_only_claimed_when_there_are_lessons(self, db: Session, admin: User) -> None:
        _course_with_title(db)
        invitation = _invitation(db, scope=InvitationScope.COURSE.value, course_id=COURSE_ID)

        message = build_invitation_message(db, invitation, accept_url=ACCEPT_URL, locale="en", inviter_name=None)

        # The course has no chapters yet, so the message says nothing
        # about lessons rather than "0 lessons".
        assert [fact.label for fact in message.facts] == ["Your role"]

    @pytest.mark.parametrize("locale", ["ru", "en", "de", "uk"])
    def test_every_locale_writes_its_own_invitation(self, db: Session, admin: User, locale: str) -> None:
        _school(db)
        invitation = _invitation(db)

        message = build_invitation_message(db, invitation, accept_url=ACCEPT_URL, locale=locale, inviter_name="Vadym")
        html = render(message)

        assert ACCEPT_URL in html
        # The catalog answered in this locale rather than handing back
        # the key or the English string.
        assert "email.invitation" not in html
        if locale != "en":
            assert "Accept invitation" not in html


class TestHowItLooks:
    def test_the_email_wears_the_current_palette(self, db: Session, admin: User) -> None:
        _school(db)
        _course_with_title(db)
        invitation = _invitation(db, scope=InvitationScope.COURSE.value, course_id=COURSE_ID)

        html = render(
            build_invitation_message(db, invitation, accept_url=ACCEPT_URL, locale="ru", inviter_name="Vadym")
        )

        found = [colour for colour in theme.RETIRED_COLOURS if colour.lower() in html.lower()]
        assert not found, f"retired palette in the invitation email: {found}"
        assert theme.INK.lower() in html.lower()

    def test_the_banner_reserves_no_height(self, db: Session, admin: User) -> None:
        """With images off, a reserved height is a dark hole.

        Roughly half of recipients never load images. The first draft
        set height="375" and opened as a black rectangle a third of the
        way down the message.
        """
        _course_with_title(db)
        invitation = _invitation(db, scope=InvitationScope.COURSE.value, course_id=COURSE_ID)

        html = render(
            build_invitation_message(db, invitation, accept_url=ACCEPT_URL, locale="en", inviter_name=None)
        )

        assert "<img" in html
        assert "height=" not in html
        assert 'alt="Preaching Course I"' in html

    def test_nothing_a_person_typed_reaches_the_html_raw(self, db: Session, admin: User) -> None:
        """Course titles and names are typed by people.

        Today they are only ever rendered into a body the same people
        receive, so the blast radius is small — but the contract has to
        be in the code, not in the habit of whoever writes the next
        caller.
        """
        _school(db, name='Bad <script>alert("x")</script> School')
        invitation = _invitation(db)

        html = render(
            build_invitation_message(
                db, invitation, accept_url=ACCEPT_URL, locale="en", inviter_name='Mallory" onmouseover="x'
            )
        )

        assert "<script>" not in html
        assert 'onmouseover="x' not in html
        assert "&lt;script&gt;" in html
