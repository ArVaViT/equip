"""Coverage for the invitation system (POST/GET /invitations, accept-by-token).

RESEND_API_KEY is unset in the test environment (see conftest.py), so
``send_invitation_email`` always short-circuits on the missing-key branch
without making a real HTTP call -- no mocking needed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_optional_user
from app.core.database import get_db
from app.main import app
from app.models.invitation import Invitation
from app.models.user import User, UserRole
from tests._cv_helpers import make_course_with_text
from tests.conftest import ADMIN_ID, TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

INVITATIONS_PREFIX = "/api/v1/invitations"
INVITEE_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
INVITEE_EMAIL = "invitee@example.com"


def _seed_invitation(db: Session, *, email: str, role: str, invited_by: uuid.UUID = ADMIN_ID) -> Invitation:
    """Insert an invitation directly rather than through ``admin_client``.

    ``admin_client`` and ``invitee_client`` both mutate the SAME
    ``app.dependency_overrides`` slot (there's one FastAPI ``app``
    instance) -- whichever TestClient fixture was constructed LAST wins
    for every request made through EITHER client, per the
    ``anon_client`` docstring in conftest.py. Tests that need "an admin
    created this invite, then a different user accepts it" can't express
    that with two conflicting-identity TestClients in one test, so admin
    invite creation is seeded directly here instead of through the API.
    """
    invitation = Invitation(email=email, role=role, token=uuid.uuid4().hex, invited_by=invited_by)
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation


def _make_invitee(db: Session, *, email: str = INVITEE_EMAIL, role: str = UserRole.STUDENT.value) -> User:
    """A signed-up account under the invited email -- the accept route
    requires the caller to already exist (self-registered as student or
    logged in via Google) before redeeming a token; see invitation_service.
    """
    user = User(id=INVITEE_ID, email=email, full_name="Invitee", role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def invitee_client(db: Session, teacher: User, admin: User):
    invitee = _make_invitee(db)

    def _override_db():
        yield db

    def _override_user():
        return invitee

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_optional_user] = _override_user

    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Create (admin-only)
# ---------------------------------------------------------------------------


def test_create_invitation_admin_ok(admin_client: TestClient):
    resp = admin_client.post(
        INVITATIONS_PREFIX, json={"email": "new.teacher@example.com", "role": "teacher", "age_attested": True}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "new.teacher@example.com"
    assert body["role"] == "teacher"
    assert body["status"] == "pending"
    assert body["is_expired"] is False
    assert body["invited_by"] == str(ADMIN_ID)


def test_create_invitation_normalizes_email_case(admin_client: TestClient):
    resp = admin_client.post(
        INVITATIONS_PREFIX, json={"email": "Mixed.Case@Example.com", "role": "student", "age_attested": True}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["email"] == "mixed.case@example.com"


def test_create_invitation_rejects_admin_role(admin_client: TestClient):
    # Literal["teacher", "student"] on the schema -- an invite can never
    # grant admin, regardless of what the request body claims.
    resp = admin_client.post(INVITATIONS_PREFIX, json={"email": "x@example.com", "role": "admin", "age_attested": True})
    assert resp.status_code == 422, resp.text


def test_create_invitation_forbidden_for_student(student_client: TestClient):
    resp = student_client.post(
        INVITATIONS_PREFIX, json={"email": "x@example.com", "role": "student", "age_attested": True}
    )
    assert resp.status_code == 403, resp.text


def test_create_invitation_forbidden_for_teacher(client: TestClient):
    # ``client`` fixture is teacher-authenticated by default.
    resp = client.post(INVITATIONS_PREFIX, json={"email": "x@example.com", "role": "student", "age_attested": True})
    assert resp.status_code == 403, resp.text


def test_create_invitation_forbidden_anonymous(anon_client: TestClient):
    resp = anon_client.post(
        INVITATIONS_PREFIX, json={"email": "x@example.com", "role": "student", "age_attested": True}
    )
    assert resp.status_code == 401, resp.text


def test_create_invitation_dedupes_pending(admin_client: TestClient, db: Session):
    first = admin_client.post(
        INVITATIONS_PREFIX, json={"email": "dup@example.com", "role": "teacher", "age_attested": True}
    )
    second = admin_client.post(
        INVITATIONS_PREFIX, json={"email": "dup@example.com", "role": "teacher", "age_attested": True}
    )
    assert first.status_code == 201
    assert second.status_code == 201
    # Same row resent, not a fresh duplicate -- same id/token, and the
    # DB has exactly one row for this (email, role).
    assert first.json()["id"] == second.json()["id"]
    rows = db.query(Invitation).filter(Invitation.email == "dup@example.com").all()
    assert len(rows) == 1


def test_create_invitation_new_row_after_prior_revoked_or_accepted(admin_client: TestClient, db: Session):
    first = admin_client.post(
        INVITATIONS_PREFIX, json={"email": "again@example.com", "role": "student", "age_attested": True}
    )
    invitation_id = uuid.UUID(first.json()["id"])
    row = db.query(Invitation).filter(Invitation.id == invitation_id).one()
    row.status = "revoked"
    db.commit()

    second = admin_client.post(
        INVITATIONS_PREFIX, json={"email": "again@example.com", "role": "student", "age_attested": True}
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] != str(invitation_id)


# ---------------------------------------------------------------------------
# List (admin-only)
# ---------------------------------------------------------------------------


def test_list_invitations_admin_ok(admin_client: TestClient):
    admin_client.post(INVITATIONS_PREFIX, json={"email": "a@example.com", "role": "teacher", "age_attested": True})
    admin_client.post(INVITATIONS_PREFIX, json={"email": "b@example.com", "role": "student", "age_attested": True})

    resp = admin_client.get(INVITATIONS_PREFIX)
    assert resp.status_code == 200, resp.text
    emails = {row["email"] for row in resp.json()}
    assert {"a@example.com", "b@example.com"} <= emails


def test_the_list_names_where_each_invitation_leads(
    admin_client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
):
    # A list of many rows has to say what each one grants by name: the
    # organization, or for a course invitation the course itself. One
    # address can hold an "account only" and a school invitation at once.
    course = make_course_with_text(db, title="Acts in Twelve Evenings", status="published", source_locale="en")
    course.organization_id = TEST_ORGANIZATION_ID
    db.commit()
    db.add(
        Invitation(
            email="seat@example.com",
            role="student",
            scope="course",
            course_id=course.id,
            token=uuid.uuid4().hex,
            invited_by=ADMIN_ID,
        )
    )
    db.add(
        Invitation(
            email="account@example.com", role="student", scope="platform", token=uuid.uuid4().hex, invited_by=ADMIN_ID
        )
    )
    db.commit()
    admin_client.post(INVITATIONS_PREFIX, json={"email": "member@example.com", "role": "student", "age_attested": True})

    rows = {row["email"]: row for row in admin_client.get(INVITATIONS_PREFIX, headers={"Accept-Language": "en"}).json()}
    assert rows["member@example.com"]["organization_name"] == "Test Organization"
    assert rows["member@example.com"]["course_title"] is None
    assert rows["seat@example.com"]["course_title"] == "Acts in Twelve Evenings"
    assert rows["account@example.com"]["organization_name"] == "Test Organization"
    assert rows["account@example.com"]["course_title"] is None

    # No German title: no title, as on every surface that serves a reader —
    # never the author's language in its place. The list says «to a course».
    # (With the platform translating; off, the reader gets the source text
    # everywhere, see ``fetch_cv_entity_texts_with_fallback``.)
    monkeypatch.setattr("app.services.content_versions.read.is_translation_enabled", lambda: True)
    rows = {row["email"]: row for row in admin_client.get(INVITATIONS_PREFIX, headers={"Accept-Language": "de"}).json()}
    assert rows["seat@example.com"]["course_title"] is None


def test_list_invitations_filters_by_role_and_status(admin_client: TestClient):
    admin_client.post(INVITATIONS_PREFIX, json={"email": "t1@example.com", "role": "teacher", "age_attested": True})
    admin_client.post(INVITATIONS_PREFIX, json={"email": "s1@example.com", "role": "student", "age_attested": True})

    resp = admin_client.get(INVITATIONS_PREFIX, params={"role": "teacher"})
    assert resp.status_code == 200
    assert all(row["role"] == "teacher" for row in resp.json())

    resp = admin_client.get(INVITATIONS_PREFIX, params={"status": "pending"})
    assert resp.status_code == 200
    assert all(row["status"] == "pending" for row in resp.json())


def test_list_invitations_forbidden_for_non_admin(student_client: TestClient):
    resp = student_client.get(INVITATIONS_PREFIX)
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# Token preview (unauthenticated)
# ---------------------------------------------------------------------------


def test_preview_invitation_by_token_ok(admin_client: TestClient, anon_client: TestClient, db: Session):
    admin_client.post(
        INVITATIONS_PREFIX, json={"email": "preview@example.com", "role": "teacher", "age_attested": True}
    )
    token = db.query(Invitation).filter(Invitation.email == "preview@example.com").one().token

    resp = anon_client.post(f"{INVITATIONS_PREFIX}/preview", json={"token": token})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "preview@example.com"
    assert body["role"] == "teacher"
    assert body["status"] == "pending"
    assert body["is_expired"] is False


def test_preview_invitation_unknown_token_404(anon_client: TestClient):
    resp = anon_client.post(f"{INVITATIONS_PREFIX}/preview", json={"token": "does-not-exist"})
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"]["code"] == "invitation.not_found"


def test_a_token_is_no_longer_read_from_the_path(admin_client: TestClient, anon_client: TestClient, db: Session):
    """The old ``GET /token/{token}`` is gone (2026-09-28).

    It stayed while a browser might still run the bundle from before the
    preview moved into a POST body. The platform log showed its last real
    caller on 2026-09-15; after that only scanners reached it. Kept, it
    would keep writing live tokens into a log nothing here can redact.
    """
    admin_client.post(INVITATIONS_PREFIX, json={"email": "stale@example.com", "role": "student", "age_attested": True})
    token = db.query(Invitation).filter(Invitation.email == "stale@example.com").one().token

    assert anon_client.get(f"{INVITATIONS_PREFIX}/token/{token}").status_code == 404
    assert anon_client.post(f"{INVITATIONS_PREFIX}/preview", json={"token": token}).status_code == 200


# ---------------------------------------------------------------------------
# Accept
# ---------------------------------------------------------------------------


def test_accept_invitation_promotes_role(invitee_client: TestClient, db: Session):
    token = _seed_invitation(db, email=INVITEE_EMAIL, role="teacher").token

    resp = invitee_client.post(f"{INVITATIONS_PREFIX}/accept", json={"token": token})
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "teacher"

    updated = db.query(User).filter(User.id == INVITEE_ID).one()
    assert updated.role == "teacher"
    row = db.query(Invitation).filter(Invitation.token == token).one()
    assert row.status == "accepted"
    assert row.accepted_at is not None


def test_accept_invitation_rejects_replay(invitee_client: TestClient, db: Session):
    token = _seed_invitation(db, email=INVITEE_EMAIL, role="teacher").token

    first = invitee_client.post(f"{INVITATIONS_PREFIX}/accept", json={"token": token})
    assert first.status_code == 200

    second = invitee_client.post(f"{INVITATIONS_PREFIX}/accept", json={"token": token})
    assert second.status_code == 409, second.text
    assert second.json()["detail"]["code"] == "invitation.already_used"


def test_accept_invitation_rejects_unknown_token(invitee_client: TestClient):
    resp = invitee_client.post(f"{INVITATIONS_PREFIX}/accept", json={"token": "bogus-token"})
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"]["code"] == "invitation.not_found"


def test_accept_invitation_rejects_expired(invitee_client: TestClient, db: Session):
    row = _seed_invitation(db, email=INVITEE_EMAIL, role="student")
    row.expires_at = datetime.now(UTC) - timedelta(days=1)
    db.commit()

    resp = invitee_client.post(f"{INVITATIONS_PREFIX}/accept", json={"token": row.token})
    assert resp.status_code == 410, resp.text
    assert resp.json()["detail"]["code"] == "invitation.expired"


def test_accept_invitation_rejects_email_mismatch(invitee_client: TestClient, db: Session):
    # Invite issued to a DIFFERENT email than the authenticated caller's.
    token = _seed_invitation(db, email="someone.else@example.com", role="teacher").token

    resp = invitee_client.post(f"{INVITATIONS_PREFIX}/accept", json={"token": token})
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"]["code"] == "invitation.email_mismatch"

    # And the caller's role must NOT have been touched by the attempt.
    unchanged = db.query(User).filter(User.id == INVITEE_ID).one()
    assert unchanged.role == UserRole.STUDENT.value


def test_accept_invitation_cannot_be_used_to_tamper_role_via_body(invitee_client: TestClient):
    # The accept schema takes a token and nothing else. A request that
    # smuggles ``role`` alongside it is refused outright rather than
    # quietly stripped: the caller is told which field was rejected, and
    # the attempt is visible in the log as a 422 instead of passing for
    # an ordinary accept.
    resp = invitee_client.post(
        f"{INVITATIONS_PREFIX}/accept",
        json={"token": "whatever", "role": "admin"},
    )
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"][0]["loc"] == ["body", "role"]


def test_accept_invitation_requires_auth(anon_client: TestClient):
    resp = anon_client.post(f"{INVITATIONS_PREFIX}/accept", json={"token": "whatever"})
    assert resp.status_code == 401, resp.text


# ---------------------------------------------------------------------------
# Revoking — an invitation sent to the wrong address used to stay live for its
# full seven days, carrying a teacher role, with nothing able to take it back.
# `revoked` was a legal status from the first migration and `accept` already
# refused anything that was not `pending`; only the route was missing.
# ---------------------------------------------------------------------------


def test_revoking_stops_the_link_from_working(admin_client: TestClient, db: Session):
    created = admin_client.post(
        INVITATIONS_PREFIX, json={"email": "wrong.address@example.com", "role": "teacher", "age_attested": True}
    ).json()

    resp = admin_client.delete(f"{INVITATIONS_PREFIX}/{created['id']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "revoked"

    row = db.query(Invitation).filter(Invitation.id == uuid.UUID(created["id"])).first()
    assert row is not None
    # The token itself still exists; what changed is that it is no longer
    # redeemable, which is what `accept_invitation` checks first.
    preview = admin_client.post(f"{INVITATIONS_PREFIX}/preview", json={"token": row.token})
    assert preview.status_code in (200, 404, 410)
    if preview.status_code == 200:
        assert preview.json()["status"] == "revoked"


def test_revoking_twice_is_not_an_error(admin_client: TestClient):
    created = admin_client.post(
        INVITATIONS_PREFIX, json={"email": "twice@example.com", "role": "student", "age_attested": True}
    ).json()
    assert admin_client.delete(f"{INVITATIONS_PREFIX}/{created['id']}").status_code == 200
    second = admin_client.delete(f"{INVITATIONS_PREFIX}/{created['id']}")
    assert second.status_code == 200
    assert second.json()["status"] == "revoked"


def test_an_accepted_invitation_cannot_be_revoked(admin_client: TestClient, db: Session):
    # Revoking here would read as "that access is gone", and it is not: the
    # person has an account. Removing the role is the other operation.
    created = admin_client.post(
        INVITATIONS_PREFIX, json={"email": "already.in@example.com", "role": "teacher", "age_attested": True}
    ).json()
    row = db.query(Invitation).filter(Invitation.id == uuid.UUID(created["id"])).first()
    assert row is not None
    row.status = "accepted"
    db.commit()

    resp = admin_client.delete(f"{INVITATIONS_PREFIX}/{created['id']}")
    assert resp.status_code == 409, resp.text


def test_revoking_something_that_does_not_exist_is_404(admin_client: TestClient):
    resp = admin_client.delete(f"{INVITATIONS_PREFIX}/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_a_student_cannot_revoke(student_client: TestClient, db: Session, admin: User):
    invitation = _seed_invitation(db, email="someone@example.com", role="teacher")
    resp = student_client.delete(f"{INVITATIONS_PREFIX}/{invitation.id}")
    assert resp.status_code == 403


def test_a_teacher_cannot_revoke(client: TestClient, db: Session, admin: User):
    invitation = _seed_invitation(db, email="another@example.com", role="teacher")
    resp = client.delete(f"{INVITATIONS_PREFIX}/{invitation.id}")
    assert resp.status_code == 403


def test_a_director_cannot_revoke_another_organizations_invitation(db: Session, admin: User):
    """Scope, not just role.

    A director is trusted inside their own organization. Without the
    organization check they could withdraw an invitation belonging to a
    different one — and be told it worked.
    """
    import uuid as _uuid

    from fastapi import HTTPException

    from app.services.invitation_service import revoke_invitation

    invitation = _seed_invitation(db, email="theirs@example.com", role="teacher")

    director = User(
        id=_uuid.uuid4(),
        email="director@elsewhere.example.com",
        full_name="Director Elsewhere",
        role=UserRole.DIRECTOR.value,
    )

    with pytest.raises(HTTPException) as caught:
        revoke_invitation(
            db,
            invitation_id=invitation.id,
            actor=director,
            organization_id=_uuid.uuid4(),
        )
    assert caught.value.status_code == 404

    db.refresh(invitation)
    assert invitation.status == "pending"
