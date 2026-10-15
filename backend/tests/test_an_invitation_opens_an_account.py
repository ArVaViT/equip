"""An invitation creates the account it invites, with no second email.

``POST /invitations/register`` and the preview that decides whether the page
shows a form or a sign-in button. Every shape an invited address can be in,
and every way a link can stop admitting anybody, is pinned here -- together
with the rule underneath all of them: the address is the invitation's, the
password of a confirmed account is never set from a link, and nothing is
written to Supabase Auth for a link that would refuse anyway.

Supabase Auth itself is ``tests/_fake_gotrue`` (installed by ``conftest``).
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_optional_user
from app.core.database import get_db
from app.main import app
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.invitation import Invitation, InvitationScope, InvitationStatus
from app.models.organization import OrganizationMember
from app.models.user import User, UserRole
from app.services import invitation_service
from app.services.invitation_service import create_or_resend_invitation, hash_invitation_token, invitation_token
from tests.conftest import ADMIN_ID, TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from tests._fake_gotrue import FakeGoTrue

PREFIX = "/api/v1/invitations"
EMAIL = "newcomer@example.com"
PASSWORD = "a long enough passphrase"
COURSE_ID = "acts-1"


@pytest.fixture()
def anon(db: Session, admin: User) -> TestClient:
    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: None
    app.dependency_overrides[get_optional_user] = lambda: None
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc


def _course(db: Session) -> Course:
    course = Course(
        id=COURSE_ID,
        status="published",
        access_mode="public",
        created_by=ADMIN_ID,
        source_locale="en",
        organization_id=TEST_ORGANIZATION_ID,
    )
    db.add(course)
    db.commit()
    return course


def _invitation(
    db: Session,
    *,
    email: str = EMAIL,
    scope: str = InvitationScope.ORGANIZATION.value,
    role: str = UserRole.STUDENT.value,
    course_id: str | None = None,
    **extra: object,
) -> tuple[Invitation, str]:
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
    return invitation, invitation_token(invitation.id)


def _register(anon: TestClient, token: str, **overrides: object):
    body = {"token": token, "full_name": "Sasha Petrov", "password": PASSWORD, "locale": "de"}
    body.update(overrides)
    return anon.post(f"{PREFIX}/register", json=body)


def _code(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


# ---------------------------------------------------------------------------
# The three shapes an address can be in
# ---------------------------------------------------------------------------


class TestNoAccountYet:
    def test_the_account_is_made_confirmed_and_the_invitation_accepted(
        self, anon: TestClient, db: Session, gotrue: FakeGoTrue
    ) -> None:
        _course(db)
        invitation, token = _invitation(db, scope=InvitationScope.COURSE.value, course_id=COURSE_ID)

        response = _register(anon, token)

        assert response.status_code == 201, response.text
        assert response.json() == {
            "role": "student",
            "scope": "course",
            "enrolled_course_id": COURSE_ID,
            "email": EMAIL,
        }
        account = gotrue.by_email(EMAIL)
        assert account is not None
        assert account.confirmed is True
        assert account.password == PASSWORD
        profile = db.query(User).filter(User.id == account.id).one()
        assert (profile.full_name, profile.preferred_locale) == ("Sasha Petrov", "de")
        db.refresh(invitation)
        assert invitation.status == InvitationStatus.ACCEPTED.value
        assert db.query(Enrollment).filter_by(user_id=account.id, course_id=COURSE_ID).count() == 1
        assert db.query(OrganizationMember).filter_by(user_id=account.id).count() == 1

    def test_the_address_comes_only_from_the_invitation(self, anon: TestClient, db: Session) -> None:
        _invitation_row, token = _invitation(db)

        response = _register(anon, token, email="somebody.else@example.com")

        assert response.status_code == 422
        assert db.query(User).filter(User.email == "somebody.else@example.com").count() == 0

    def test_a_password_supabase_refuses_leaves_nothing_behind(
        self, anon: TestClient, db: Session, gotrue: FakeGoTrue
    ) -> None:
        invitation, token = _invitation(db)

        response = _register(anon, token, password="password1234")

        assert response.status_code == 422
        assert _code(response) == "auth.weak_password"
        assert gotrue.accounts == {}
        db.refresh(invitation)
        assert invitation.status == InvitationStatus.PENDING.value

    def test_supabase_not_answering_is_said_and_changes_nothing(
        self, anon: TestClient, db: Session, gotrue: FakeGoTrue
    ) -> None:
        gotrue.down = True
        invitation, token = _invitation(db)

        response = _register(anon, token)

        assert response.status_code == 503
        assert _code(response) == "auth.unavailable"
        db.refresh(invitation)
        assert invitation.status == InvitationStatus.PENDING.value


class TestAnAccountNobodyConfirmed:
    def test_the_link_confirms_it_with_the_password_chosen_now(
        self, anon: TestClient, db: Session, gotrue: FakeGoTrue
    ) -> None:
        """The second-attempt case Supabase's sign-up gets wrong: it keeps the
        first attempt's password and mails yet another link."""
        earlier = gotrue.add_account(db, email=EMAIL, confirmed=False, password="the first attempt")
        invitation, token = _invitation(db)

        response = _register(anon, token)

        assert response.status_code == 201, response.text
        account = gotrue.accounts[earlier.id]
        assert account.confirmed is True
        assert account.password == PASSWORD
        assert len(gotrue.accounts) == 1
        db.refresh(earlier)
        assert (earlier.full_name, earlier.preferred_locale, earlier.locale_source) == ("Sasha Petrov", "de", "chosen")
        db.refresh(invitation)
        assert invitation.status == InvitationStatus.ACCEPTED.value

    def test_an_address_written_in_other_case_is_the_same_account(
        self, anon: TestClient, db: Session, gotrue: FakeGoTrue
    ) -> None:
        earlier = gotrue.add_account(db, email="Newcomer@Example.com", confirmed=False)
        _invitation_row, token = _invitation(db)

        response = _register(anon, token)

        assert response.status_code == 201, response.text
        assert len(gotrue.accounts) == 1
        assert gotrue.accounts[earlier.id].confirmed is True

    def test_a_platform_invitation_closed_by_the_first_attempt_still_opens(
        self, anon: TestClient, db: Session, gotrue: FakeGoTrue
    ) -> None:
        """The profile of an unconfirmed sign-up fulfils a platform invitation
        in the database; the person it was for must still get in by it."""
        gotrue.add_account(db, email=EMAIL, confirmed=False)
        _invitation_row, token = _invitation(
            db,
            scope=InvitationScope.PLATFORM.value,
            status=InvitationStatus.FULFILLED.value,
            fulfilled_at=datetime.now(UTC),
        )

        response = _register(anon, token)

        assert response.status_code == 201, response.text
        assert gotrue.by_email(EMAIL).confirmed is True  # type: ignore[union-attr]

    def test_a_refused_password_leaves_it_unconfirmed(self, anon: TestClient, db: Session, gotrue: FakeGoTrue) -> None:
        earlier = gotrue.add_account(db, email=EMAIL, confirmed=False, password="the first attempt")
        _invitation_row, token = _invitation(db)

        response = _register(anon, token, password="short")

        assert _code(response) == "auth.weak_password"
        assert gotrue.accounts[earlier.id].confirmed is False
        assert gotrue.accounts[earlier.id].password == "the first attempt"


class TestAConfirmedAccount:
    def test_is_refused_and_its_password_never_touched(self, anon: TestClient, db: Session, gotrue: FakeGoTrue) -> None:
        existing = gotrue.add_account(db, email=EMAIL, confirmed=True, password="their own password")
        invitation, token = _invitation(db)

        response = _register(anon, token)

        assert response.status_code == 409
        assert _code(response) == "invitation.account_exists"
        assert gotrue.accounts[existing.id].password == "their own password"
        assert ("PUT", f"/admin/users/{existing.id}") not in gotrue.calls
        db.refresh(invitation)
        assert invitation.status == InvitationStatus.PENDING.value

    def test_created_between_the_look_and_the_write_is_refused_too(
        self, anon: TestClient, db: Session, gotrue: FakeGoTrue, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A double submit: the first request made the account while the
        second was deciding. The second decides again, on what is there."""
        real = invitation_service.account_for_address
        looks: list[str] = []

        def first_look_sees_nothing(db: Session, email: str):
            looks.append(email)
            if len(looks) == 1:
                gotrue.add_account(db, email=EMAIL, confirmed=True)
                return None
            return real(db, email)

        monkeypatch.setattr(invitation_service, "account_for_address", first_look_sees_nothing)
        _invitation_row, token = _invitation(db)

        response = _register(anon, token)

        assert response.status_code == 409
        assert _code(response) == "invitation.account_exists"
        assert len(looks) == 2


# ---------------------------------------------------------------------------
# A link that admits nobody touches no account
# ---------------------------------------------------------------------------


class TestALinkThatRefusesTouchesNoAccount:
    def _assert_untouched(self, gotrue: FakeGoTrue) -> None:
        assert gotrue.accounts == {}
        assert not [call for call in gotrue.calls if call[0] in ("POST", "PUT")]

    def test_expired(self, anon: TestClient, db: Session, gotrue: FakeGoTrue) -> None:
        _row, token = _invitation(db, expires_at=datetime.now(UTC) - timedelta(minutes=1))
        response = _register(anon, token)
        assert (response.status_code, _code(response)) == (410, "invitation.expired")
        self._assert_untouched(gotrue)

    def test_revoked(self, anon: TestClient, db: Session, gotrue: FakeGoTrue) -> None:
        _row, token = _invitation(db, status=InvitationStatus.REVOKED.value)
        response = _register(anon, token)
        assert (response.status_code, _code(response)) == (409, "invitation.already_used")
        self._assert_untouched(gotrue)

    def test_unknown(self, anon: TestClient, gotrue: FakeGoTrue) -> None:
        response = _register(anon, "not-a-token-anybody-was-sent")
        assert (response.status_code, _code(response)) == (404, "invitation.not_found")
        self._assert_untouched(gotrue)

    def test_course_gone(self, anon: TestClient, db: Session, gotrue: FakeGoTrue) -> None:
        course = _course(db)
        _row, token = _invitation(db, scope=InvitationScope.COURSE.value, course_id=COURSE_ID)
        course.deleted_at = datetime.now(UTC)
        db.commit()
        response = _register(anon, token)
        assert response.status_code == 404
        self._assert_untouched(gotrue)

    def test_sender_no_longer_speaks_for_the_school(self, anon: TestClient, db: Session, gotrue: FakeGoTrue) -> None:
        _row, token = _invitation(db)
        db.query(User).filter(User.id == ADMIN_ID).update({User.deactivated_at: datetime.now(UTC)})
        db.commit()
        response = _register(anon, token)
        assert (response.status_code, _code(response)) == (403, "invitation.inviter_not_staff")
        self._assert_untouched(gotrue)

    def test_used_once_is_used(self, anon: TestClient, db: Session, gotrue: FakeGoTrue) -> None:
        _row, token = _invitation(db)
        assert _register(anon, token).status_code == 201

        again = _register(anon, token, password="another long passphrase")

        assert (again.status_code, _code(again)) == (409, "invitation.already_used")
        assert gotrue.by_email(EMAIL).password == PASSWORD  # type: ignore[union-attr]


def test_registering_is_rate_limited(anon: TestClient) -> None:
    answers = [_register(anon, f"guess-{n}").status_code for n in range(11)]
    assert answers[:10] == [404] * 10
    assert answers[10] == 429


# ---------------------------------------------------------------------------
# What the preview tells the page
# ---------------------------------------------------------------------------


class TestThePreview:
    def _preview(self, anon: TestClient, token: str) -> dict:
        response = anon.post(f"{PREFIX}/preview", json={"token": token})
        assert response.status_code == 200, response.text
        return response.json()

    def test_names_the_school(self, anon: TestClient, db: Session) -> None:
        _row, token = _invitation(db)
        body = self._preview(anon, token)
        assert body["organization_name"] == "Test Organization"
        assert body["unusable_reason"] is None
        assert body["has_account"] is False

    def test_a_platform_invitation_names_no_school(self, anon: TestClient, db: Session) -> None:
        _row, token = _invitation(db, scope=InvitationScope.PLATFORM.value)
        assert self._preview(anon, token)["organization_name"] is None

    def test_says_when_the_address_has_a_confirmed_account(
        self, anon: TestClient, db: Session, gotrue: FakeGoTrue
    ) -> None:
        gotrue.add_account(db, email=EMAIL, confirmed=True)
        _row, token = _invitation(db)
        assert self._preview(anon, token)["has_account"] is True

    def test_an_unconfirmed_account_is_not_one_to_sign_in_to(
        self, anon: TestClient, db: Session, gotrue: FakeGoTrue
    ) -> None:
        gotrue.add_account(db, email=EMAIL, confirmed=False)
        _row, token = _invitation(db)
        assert self._preview(anon, token)["has_account"] is False

    def test_supabase_not_answering_shows_the_form(self, anon: TestClient, db: Session, gotrue: FakeGoTrue) -> None:
        gotrue.add_account(db, email=EMAIL, confirmed=True)
        gotrue.down = True
        _row, token = _invitation(db)
        assert self._preview(anon, token)["has_account"] is False

    @pytest.mark.parametrize(
        ("extra", "reason"),
        [
            ({"expires_at": datetime.now(UTC) - timedelta(minutes=1)}, "expired"),
            ({"status": "revoked"}, "revoked"),
            ({"status": "accepted", "accepted_at": datetime.now(UTC)}, "used"),
        ],
    )
    def test_names_why_a_link_is_spent(self, anon: TestClient, db: Session, extra: dict, reason: str) -> None:
        _row, token = _invitation(db, **extra)
        assert self._preview(anon, token)["unusable_reason"] == reason

    def test_names_a_course_that_is_gone(self, anon: TestClient, db: Session) -> None:
        course = _course(db)
        _row, token = _invitation(db, scope=InvitationScope.COURSE.value, course_id=COURSE_ID)
        course.deleted_at = datetime.now(UTC)
        db.commit()
        assert self._preview(anon, token)["unusable_reason"] == "course_gone"

    def test_names_a_sender_who_left(self, anon: TestClient, db: Session) -> None:
        _row, token = _invitation(db)
        db.query(User).filter(User.id == ADMIN_ID).update({User.deactivated_at: datetime.now(UTC)})
        db.commit()
        assert self._preview(anon, token)["unusable_reason"] == "inviter_left"


# ---------------------------------------------------------------------------
# The token: derived, hashed, stable across resends, never handed out
# ---------------------------------------------------------------------------


class TestTheToken:
    def test_the_table_holds_only_its_hash(self, db: Session, admin: User) -> None:
        invitation, _new = create_or_resend_invitation(
            db, email=EMAIL, role="student", invited_by=ADMIN_ID, organization_id=TEST_ORGANIZATION_ID
        )
        token = invitation_token(invitation.id)
        assert invitation.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert token not in {str(value) for value in vars(invitation).values()}

    def test_a_resend_mails_the_same_link_and_starts_its_seven_days_over(self, db: Session, admin: User) -> None:
        first, _new = create_or_resend_invitation(
            db, email=EMAIL, role="student", invited_by=ADMIN_ID, organization_id=TEST_ORGANIZATION_ID
        )
        first.expires_at = datetime.now(UTC) + timedelta(hours=2)
        db.commit()
        hash_before = first.token_hash

        again, is_new = create_or_resend_invitation(
            db, email=EMAIL, role="student", invited_by=ADMIN_ID, organization_id=TEST_ORGANIZATION_ID
        )

        assert is_new is False
        assert again.token_hash == hash_before
        expires = again.expires_at if again.expires_at.tzinfo else again.expires_at.replace(tzinfo=UTC)
        assert expires > datetime.now(UTC) + timedelta(days=6, hours=23)

    def test_a_link_mailed_before_the_hashing_still_opens(self, anon: TestClient, db: Session) -> None:
        """What the migration's backfill promises: the random tokens already
        in inboxes are found by their hash."""
        _invitation(db, token_hash=hash_invitation_token("a-random-token-from-september"))
        response = anon.post(f"{PREFIX}/preview", json={"token": "a-random-token-from-september"})
        assert response.status_code == 200

    def test_a_resend_of_a_link_from_before_mails_one_that_opens(
        self, db: Session, admin: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A row written before the derivation holds the hash of a random
        token nobody can read back. Its resend must mail a link that opens."""
        mailed: list[str] = []
        monkeypatch.setattr(
            invitation_service, "send_invitation_email", lambda *_a, accept_url, **_k: mailed.append(accept_url)
        )
        old, _token = _invitation(db, token_hash=hash_invitation_token("a-random-token-from-september"))

        again, is_new = create_or_resend_invitation(
            db, email=EMAIL, role="student", invited_by=ADMIN_ID, organization_id=TEST_ORGANIZATION_ID
        )

        assert (again.id, is_new) == (old.id, False)
        token = mailed[-1].split("#token=", 1)[1]
        assert invitation_service.get_invitation_by_token(db, token).id == old.id

    def test_no_response_to_staff_carries_the_token(self, admin_client: TestClient, db: Session) -> None:
        created = admin_client.post(PREFIX, json={"email": EMAIL, "role": "teacher", "age_attested": True})
        resent = admin_client.post(PREFIX, json={"email": EMAIL, "role": "teacher", "age_attested": True})
        listed = admin_client.get(PREFIX)
        assert created.status_code == 201, created.text
        row = db.query(Invitation).filter(Invitation.email == EMAIL).one()
        token = invitation_token(row.id)

        for response in (created, resent, listed):
            assert token not in response.text
            assert row.token_hash not in response.text
        revoked = admin_client.delete(f"{PREFIX}/{row.id}")
        assert token not in revoked.text
        assert row.token_hash not in revoked.text

    def test_the_token_depends_on_the_server_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ident = uuid.uuid4()
        before = invitation_token(ident)
        monkeypatch.setattr(invitation_service.settings, "JWT_SECRET_KEY", "another-key")
        assert invitation_token(ident) != before


def test_accepting_after_google_is_not_held_at_the_consent_gate(
    db: Session, admin: User, nobody_has_signed_anything: None
) -> None:
    """A person new to Equip signs in with Google on the invite page, where
    the first-run consent screen does not render; the page accepts for them."""
    person = User(id=uuid.uuid4(), email=EMAIL, full_name="New", role=UserRole.STUDENT.value)
    db.add(person)
    db.commit()
    _row, token = _invitation(db)

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: person
    app.dependency_overrides[get_optional_user] = lambda: person
    from app.api import consent_gate

    app.dependency_overrides[consent_gate.consent_subject] = lambda: person
    with TestClient(app, raise_server_exceptions=False) as tc:
        response = tc.post(f"{PREFIX}/accept", json={"token": token})

    assert response.status_code == 200, response.text
