"""The invitation email: what it says, in whose language, and how it looks.

Three things this file is here to stop coming back.

**The language.** An invitation used to default to the platform's
fallback, so German and Ukrainian schools mailed their own people in
English. There is no preference to read — the invited person has no
account — so the language is the inviting person's, and every locale
must produce its own text rather than English with a translated button.

**The palette.** The August palette fix landed in the Auth emails, where
a test forbids the retired colours, and never reached the invitation,
which had no test at all: it kept a blue button for a month after the
product stopped being blue.

**The pictures.** The message led with the course cover until
2026-09-12. Half of recipients never load images; a cover is a picture
of text and cannot reflow on a phone; and the cover is written in the
course's language, so a Russian invitation opened under an English
banner. Everything that looks like a poster is now real text.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.models.content_version import ContentVersion
from app.models.course import Course
from app.models.course_event import CourseEvent
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


def _course_with_title(db: Session, title: str = "Курс проповедника — I", locale: str = "ru") -> Course:
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


def _session(db: Session, *, when: datetime) -> CourseEvent:
    event = CourseEvent(
        id=uuid.uuid4(),
        course_id=COURSE_ID,
        event_type="live_session",
        event_date=when,
        created_by=ADMIN_ID,
    )
    db.add(event)
    db.commit()
    return event


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
    def test_a_course_invitation_names_the_course_the_school_and_the_teacher(self, db: Session, admin: User) -> None:
        _school(db)
        _course_with_title(db)
        invitation = _invitation(db, scope=InvitationScope.COURSE.value, course_id=COURSE_ID)

        message = build_invitation_message(
            db, invitation, accept_url=ACCEPT_URL, locale="ru", inviter_name="Дмитрий Константинов"
        )

        assert message.title == "Курс проповедника — I"
        assert "UCOAT" in message.eyebrow
        assert any(fact.value == "Дмитрий Константинов" for fact in message.facts)
        assert invitation_subject(message, "ru", invitation.scope).startswith("Приглашение на курс")

    def test_the_first_session_carries_its_timezone(self, db: Session, admin: User) -> None:
        """A time without a zone is worse than no time.

        Half of this school is on the west coast: "20:00" has meant two
        different evenings to two readers of the same letter.
        """
        _school(db)
        _course_with_title(db)
        # 2026-09-19 00:00 UTC is the 18th, 20:00 Eastern / 17:00 Pacific.
        _session(db, when=datetime(2026, 9, 19, 0, 0, tzinfo=UTC))
        invitation = _invitation(db, scope=InvitationScope.COURSE.value, course_id=COURSE_ID)

        message = build_invitation_message(db, invitation, accept_url=ACCEPT_URL, locale="ru", inviter_name="Д")
        session_row = next(fact for fact in message.facts if "занятие" in fact.label.lower())

        assert "20:00" in session_row.value
        assert "17:00" in session_row.value
        assert "восточному" in session_row.value

    def test_a_session_that_has_passed_is_not_advertised(self, db: Session, admin: User) -> None:
        _school(db)
        _course_with_title(db)
        _session(db, when=datetime.now(UTC) - timedelta(days=1))
        invitation = _invitation(db, scope=InvitationScope.COURSE.value, course_id=COURSE_ID)

        message = build_invitation_message(db, invitation, accept_url=ACCEPT_URL, locale="ru", inviter_name="Д")

        assert not any("занятие" in fact.label.lower() for fact in message.facts)

    def test_the_lesson_count_is_only_claimed_when_there_are_lessons(self, db: Session, admin: User) -> None:
        _school(db)
        _course_with_title(db)
        invitation = _invitation(db, scope=InvitationScope.COURSE.value, course_id=COURSE_ID)

        message = build_invitation_message(db, invitation, accept_url=ACCEPT_URL, locale="ru", inviter_name=None)

        # The course has no chapters yet, so the message says nothing
        # about lessons rather than "0 lessons".
        assert not any("уроков" in fact.label.lower() for fact in message.facts)

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

    def test_the_message_carries_no_images_at_all(self, db: Session, admin: User) -> None:
        """A poster made of text, not a picture of a poster."""
        _school(db)
        _course_with_title(db)
        invitation = _invitation(db, scope=InvitationScope.COURSE.value, course_id=COURSE_ID)

        html = render(build_invitation_message(db, invitation, accept_url=ACCEPT_URL, locale="ru", inviter_name="Д"))

        assert "<img" not in html
        assert "background-image" not in html

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


class TestTheTextAlternative:
    """What a client shows when it renders the text, not the HTML.

    Gmail derives that version by stripping tags, and CSS does not exist
    for it. A previous layout put a label and its value in one cell and
    leaned on ``display:block`` to separate them; the text alternative
    ran them together into one word.
    """

    @staticmethod
    def _as_text(html: str) -> str:
        broken = re.sub(r"<br\s*/?>|</p>|</tr>|</td>", "\n", html)
        return re.sub(r"<[^>]+>", "", broken)

    def test_each_fact_keeps_its_label_off_its_value(self, db: Session, admin: User) -> None:
        _school(db)
        invitation = _invitation(db)

        text = self._as_text(
            render(build_invitation_message(db, invitation, accept_url=ACCEPT_URL, locale="ru", inviter_name="Vadym"))
        )

        assert "рольстудент" not in text

    def test_the_link_survives_as_the_only_way_in(self, db: Session, admin: User) -> None:
        _school(db)
        invitation = _invitation(db)

        html = render(
            build_invitation_message(db, invitation, accept_url=ACCEPT_URL, locale="ru", inviter_name="Vadym")
        )

        assert ACCEPT_URL in html

    @pytest.mark.parametrize(("locale", "expected"), [("ru", "19.09.2026"), ("en", "2026-09-19")])
    def test_the_date_is_written_the_way_the_language_writes_dates(
        self, db: Session, admin: User, locale: str, expected: str
    ) -> None:
        invitation = _invitation(db)
        invitation.expires_at = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
        db.commit()

        message = build_invitation_message(db, invitation, accept_url=ACCEPT_URL, locale=locale, inviter_name=None)

        assert any(expected in note for note in message.notes)
