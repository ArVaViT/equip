"""Course mail, and the promise that every kind of it can be stopped.

The privacy policy says it plainly: course mail "can be turned off in your
profile, and every such message carries an unsubscribe link". The one
course mail sent today — the certificate decision — ships with the means to
stop it; the switch, the link and the header are checked here by kind.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import jwt

from app.core.config import settings
from app.services.email import course_mail
from app.services.email.course_mail import (
    read_unsubscribe_token,
    send_course_mail,
    unsubscribe_token,
    wants,
)
from app.services.email.render import Message, render, render_text
from app.services.email.send import send_email

if TYPE_CHECKING:
    import pytest
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

    from app.models.user import User


def _message() -> Message:
    return Message(
        eyebrow="Course", title="Romans 8", lede="Marked.", cta_label="Read", cta_url="https://x/y", preview="p"
    )


class TestWhoGetsMail:
    def test_everything_by_default(self, db: Session, student: User) -> None:
        assert wants(student, "work_returned")

    def test_not_a_kind_the_person_turned_off(self, db: Session, student: User) -> None:
        student.email_off = ["work_returned"]
        assert not wants(student, "work_returned")
        assert wants(student, "announcement")

    def test_not_a_closed_account(self, db: Session, student: User) -> None:
        from datetime import UTC, datetime

        student.deactivated_at = datetime.now(UTC)
        assert not wants(student, "work_returned")


class TestTheLink:
    def test_a_token_names_its_person_and_kind(self) -> None:
        token = unsubscribe_token("person-1", "work_returned")
        assert read_unsubscribe_token(token) == ("person-1", "work_returned")

    def test_a_token_for_something_else_unsubscribes_nobody(self) -> None:
        # An iCal feed token is signed with the same secret; it must not work here.
        # Everything an unsubscribe token carries, except its audience.
        ical = jwt.encode(
            {"sub": "person-1", "kind": "work_returned", "aud": "equip-ical"},
            settings.JWT_SECRET_KEY,
            algorithm="HS256",
        )
        assert read_unsubscribe_token(ical) is None
        forged = jwt.encode(
            {"sub": "p", "kind": "work_returned", "aud": "equip-unsubscribe"}, "not-the-key-" + "x" * 32
        )
        assert read_unsubscribe_token(forged) is None
        unknown = jwt.encode(
            {"sub": "p", "kind": "newsletter", "aud": "equip-unsubscribe"}, settings.JWT_SECRET_KEY, algorithm="HS256"
        )
        assert read_unsubscribe_token(unknown) is None


class TestSending:
    def test_a_course_mail_carries_its_way_out(self, db: Session, student: User) -> None:
        sent: list[dict[str, Any]] = []
        with patch.object(course_mail, "send_email", side_effect=lambda **kw: sent.append(kw)):
            send_course_mail(person=student, kind="work_returned", locale="ru", message=_message(), subject="S")
        assert len(sent) == 1
        mail = sent[0]
        # In the body, as a link to a page that asks first…
        assert "/unsubscribe?token=" in mail["text"]
        assert "/unsubscribe?token=" in mail["html"]
        # …and in the headers Gmail and Yahoo read for their own button.
        assert mail["headers"]["List-Unsubscribe"].startswith("<https://")
        assert "/api/v1/email/unsubscribe?token=" in mail["headers"]["List-Unsubscribe"]
        assert mail["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
        assert mail["kind"] == "work_returned"

    def test_a_kind_turned_off_is_not_sent(self, db: Session, student: User) -> None:
        student.email_off = ["work_returned"]
        with patch.object(course_mail, "send_email") as send:
            assert (
                send_course_mail(person=student, kind="work_returned", locale="en", message=_message(), subject="S")
                is None
            )
        send.assert_not_called()

    def test_an_allowlist_keeps_a_test_run_away_from_real_people(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pydantic import SecretStr

        monkeypatch.setattr(settings, "RESEND_API_KEY", SecretStr("re_test"))
        monkeypatch.setattr(settings, "EMAIL_ALLOWLIST", "me@example.com")
        with patch("app.services.email.send.httpx.post") as post:
            delivery = send_email(to="student@example.com", subject="s", html="h", kind="work_returned")
        assert delivery.reason == "not_allowed"
        post.assert_not_called()

    def test_the_link_is_in_both_bodies(self) -> None:
        m = Message(
            **{**_message().__dict__, "unsubscribe_label": "Stop", "unsubscribe_url": "https://e/unsubscribe?token=t"}
        )
        assert 'href="https://e/unsubscribe?token=t"' in render(m)
        assert "Stop: https://e/unsubscribe?token=t" in render_text(m)


class TestTheUnsubscribeEndpoint:
    def test_reading_the_link_changes_nothing(self, anon_client: TestClient, db: Session, student: User) -> None:
        token = unsubscribe_token(str(student.id), "work_returned")
        r = anon_client.get("/api/v1/email/unsubscribe", params={"token": token})
        assert r.status_code == 200, r.text
        assert r.json() == {"kind": "work_returned", "off": False}
        db.refresh(student)
        assert student.email_off == []

    def test_pressing_the_button_turns_that_kind_off_once(
        self, anon_client: TestClient, db: Session, student: User
    ) -> None:
        token = unsubscribe_token(str(student.id), "work_returned")
        for _ in range(2):
            r = anon_client.post("/api/v1/email/unsubscribe", params={"token": token})
            assert r.status_code == 200, r.text
            assert r.json() == {"kind": "work_returned", "off": True}
        db.refresh(student)
        assert student.email_off == ["work_returned"]

    def test_the_mail_client_s_own_button_works_too(self, anon_client: TestClient, db: Session, student: User) -> None:
        token = unsubscribe_token(str(student.id), "work_returned")
        r = anon_client.post(
            "/api/v1/email/unsubscribe",
            params={"token": token},
            content="List-Unsubscribe=One-Click",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert r.status_code == 200, r.text
        db.refresh(student)
        assert "work_returned" in student.email_off

    def test_a_bad_link_says_so(self, anon_client: TestClient) -> None:
        r = anon_client.post("/api/v1/email/unsubscribe", params={"token": "nonsense"})
        assert r.status_code == 400


def test_an_empty_allowlist_lets_nobody_through(monkeypatch: pytest.MonkeyPatch) -> None:
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "RESEND_API_KEY", SecretStr("re_test"))
    monkeypatch.setattr(settings, "EMAIL_ALLOWLIST", "")
    with patch("app.services.email.send.httpx.post") as post:
        assert send_email(to="me@example.com", subject="s", html="h", kind="work_returned").reason == "not_allowed"
    post.assert_not_called()


def test_the_link_is_signed_with_a_key_of_its_own() -> None:
    """Not with the server secret: a token every Supabase service would accept
    the signature of is one rejected audience or role away from trouble."""
    import jwt as pyjwt
    import pytest as pt

    from app.core.config import settings as cfg

    token = course_mail.unsubscribe_token("11111111-1111-1111-1111-111111111111", "work_returned")
    with pt.raises(pyjwt.PyJWTError):
        pyjwt.decode(token, cfg.JWT_SECRET_KEY, algorithms=["HS256"], audience="equip-unsubscribe")
    assert course_mail.read_unsubscribe_token(token) == ("11111111-1111-1111-1111-111111111111", "work_returned")
