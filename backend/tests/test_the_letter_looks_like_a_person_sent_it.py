"""Deliverability: the parts of a message a filter reads before a human does.

Written on 2026-09-12, after the first real batch of invitations — ten
of them, one minute, from a domain three days old — landed in spam and
in Gmail's Trash for most recipients. Authentication was not the
problem: the raw headers said ``dkim=pass``, ``spf=pass``,
``dmarc=pass``. Three other things were.

**There was no text alternative of our own.** The provider derives one
by stripping tags, and our layout is a table, so what a text client
showed was ``First session2026-09-12, 20:00 EasternLessons4, 75
minutes eachTeacherDmytro Kostantynov``. A run-on wall of words with a
link in it is the shape of the spam corpus.

**Nobody sent it.** ``From: Equip <noreply@…>`` is a machine writing to
someone who has never heard of the machine. The invitation is from a
teacher, and it should say so.

**There was no way to answer.** A message that cannot be replied to is
a broadcast. Replies to a real mailbox are also the single strongest
signal a recipient can give in our favour.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.models.invitation import Invitation, InvitationScope
from app.models.organization import Organization
from app.models.user import UserRole
from app.services.email.invitation import build_invitation_message
from app.services.email.render import Fact, Message, render_text
from app.services.email.send import FROM, FROM_ADDRESS, _from_header
from tests.conftest import ADMIN_ID, TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User

ACCEPT_URL = "https://equipbible.com/invite/accept?token=abc123"


def _invitation(db: Session) -> Invitation:
    invitation = Invitation(
        email="newcomer@example.com",
        role=UserRole.STUDENT.value,
        scope=InvitationScope.ORGANIZATION.value,
        token=uuid.uuid4().hex,
        invited_by=ADMIN_ID,
        organization_id=TEST_ORGANIZATION_ID,
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation


class TestTheTextWeWriteOurselves:
    def test_every_fact_stands_on_its_own_line(self) -> None:
        """The failure that started this file, in one assertion."""
        text = render_text(
            Message(
                eyebrow="UCOAT",
                title="Курс проповедника",
                lede="Четыре занятия.",
                cta_label="Принять приглашение",
                cta_url=ACCEPT_URL,
                preview="",
                facts=(Fact("Первое занятие", "19.09.2026, 20:00"), Fact("Уроков", "4")),
            )
        )

        assert "Первое занятие: 19.09.2026, 20:00" in text.splitlines()
        assert "Уроков: 4" in text.splitlines()
        # The shape the provider produced: one label glued to the next
        # value, with no separator anywhere.
        assert "20:00Уроков" not in text

    def test_the_link_is_reachable_without_a_single_tag(self) -> None:
        text = render_text(
            Message(
                eyebrow="",
                title="T",
                lede="",
                cta_label="Принять приглашение",
                cta_url=ACCEPT_URL,
                preview="",
            )
        )

        assert ACCEPT_URL in text
        assert "<" not in text

    def test_it_carries_everything_the_html_carries(self, db: Session, admin: User) -> None:
        """Two versions of one message, not a summary and a message.

        A text part that says less than the HTML is its own spam signal
        — and it strands whoever reads mail as text.
        """
        db.query(Organization).filter(Organization.id == TEST_ORGANIZATION_ID).one().public_name = "UCOAT"
        db.commit()
        message = build_invitation_message(
            db, _invitation(db), accept_url=ACCEPT_URL, locale="ru", inviter_name="Дмитрий Константинов"
        )

        text = render_text(message)

        assert message.title in text
        assert message.cta_url in text
        for fact in message.facts:
            assert fact.value in text
        for note in message.notes:
            assert note in text


class TestWhoTheMessageIsFrom:
    def test_a_named_sender_stands_in_front_of_the_product(self) -> None:
        assert _from_header("Dmytro Kostantynov") == f'"Dmytro Kostantynov via Equip" <{FROM_ADDRESS}>'

    def test_without_a_name_it_is_the_product_alone(self) -> None:
        assert _from_header(None) == FROM
        assert _from_header("   ") == FROM

    def test_a_name_can_not_forge_a_second_address(self) -> None:
        """The display name is typed by a person, and it ends up in a header.

        A quote in it would close ours early and let the rest of the
        name become anything — another address, another header.
        """
        header = _from_header('Mallory" <evil@attacker.test>, "x')

        assert header.count("<") == 1
        assert header.endswith(f"<{FROM_ADDRESS}>")
        assert '"' not in header[1:-1].split('" <')[0].replace('"', "")

    def test_a_name_can_not_start_a_header_of_its_own(self) -> None:
        header = _from_header("Mallory\r\nBcc: everyone@example.test")

        assert "\r" not in header
        assert "\n" not in header

    def test_a_very_long_name_is_cut_rather_than_carried(self) -> None:
        header = _from_header("Ы" * 500)

        assert len(header) < 140
