"""Organization #1 was inserted by hand. #2 has to have a route.

The engineering plan draws the line for this step at "a second one
*could* be created" — not at creating it, which is a business decision.
These tests are that line: staff can admit an organization, name the
person who runs it, and move it between states, and nobody else can do
any of it.

Two rules are load-bearing enough to be tested rather than commented:

* **A slug is not editable.** It is in the organization's URL and
  printed on every certificate it has issued; editing it turns a diploma
  into a document pointing at nothing.
* **Platform staff are not appointable as directors.** The two roles
  were split on purpose (#1162); an appointment that quietly demotes an
  admin would put them back together.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_optional_user
from app.core.database import get_db
from app.main import app
from app.models.organization import Organization
from app.models.user import User, UserRole

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _client_as(db: Session, user: User) -> TestClient:
    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_optional_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def staff_client(db: Session):
    staff = User(
        id=uuid.uuid4(),
        email="staff@equipbible.com",
        full_name="Platform Staff",
        role=UserRole.ADMIN.value,
    )
    db.add(staff)
    db.commit()
    with _client_as(db, staff) as tc:
        yield tc
    app.dependency_overrides.clear()


@pytest.fixture()
def director_client(db: Session):
    director = User(
        id=uuid.uuid4(),
        email="director@example.com",
        full_name="A Director",
        role=UserRole.DIRECTOR.value,
    )
    db.add(director)
    db.commit()
    with _client_as(db, director) as tc:
        yield tc
    app.dependency_overrides.clear()


def _create(client: TestClient, **overrides) -> dict:
    payload = {"slug": "ucoat", "public_name": "UCOAT"} | overrides
    resp = client.post("/api/v1/admin/organizations", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestAdmission:
    def test_staff_admit_an_organization(self, staff_client: TestClient, db: Session):
        created = _create(staff_client, slug="second-school", public_name="Second School", country="UA")

        assert created["slug"] == "second-school"
        assert created["status"] == "approved", "an organization staff created is one staff admitted"
        assert created["member_count"] == 0
        assert created["director_emails"] == []
        assert db.query(Organization).filter(Organization.slug == "second-school").first() is not None

    def test_a_duplicate_slug_is_a_conflict_not_a_crash(self, staff_client: TestClient):
        _create(staff_client, slug="taken", public_name="First Name")
        resp = staff_client.post(
            "/api/v1/admin/organizations",
            json={"slug": "taken", "public_name": "Another Name"},
        )
        assert resp.status_code == 409, resp.text

    @pytest.mark.parametrize("bad", ["Has Spaces", "UPPER", "trailing-", "-leading", "double--hyphen", "a"])
    def test_a_slug_that_would_not_survive_a_url_is_refused(self, staff_client: TestClient, bad: str):
        resp = staff_client.post(
            "/api/v1/admin/organizations",
            json={"slug": bad, "public_name": f"Name for {bad}"},
        )
        assert resp.status_code == 422, resp.text

    def test_a_director_cannot_admit_anybody(self, director_client: TestClient):
        resp = director_client.post(
            "/api/v1/admin/organizations",
            json={"slug": "self-admitted", "public_name": "Self Admitted"},
        )
        assert resp.status_code == 403, resp.text


class TestTheSlugIsNotEditable:
    def test_a_request_that_tries_to_rename_a_slug_is_refused_outright(self, staff_client: TestClient):
        """Not ignored — refused. ``RequestModel`` forbids unknown fields,
        so a caller who thinks they renamed a slug is told they did not,
        rather than getting a 200 and a quietly unchanged value."""
        created = _create(staff_client, slug="immutable", public_name="Immutable School")

        resp = staff_client.patch(
            f"/api/v1/admin/organizations/{created['id']}",
            json={"slug": "renamed", "public_name": "Renamed School"},
        )

        assert resp.status_code == 422, resp.text
        assert "slug" in resp.text

        still = staff_client.get(f"/api/v1/admin/organizations/{created['id']}")
        assert still.json()["slug"] == "immutable", "the slug a certificate points at moved"
        assert still.json()["public_name"] == "Immutable School", "the refused request wrote half of itself"

    def test_the_rest_of_the_organization_is_editable(self, staff_client: TestClient):
        created = _create(staff_client, slug="editable", public_name="Old Name")

        resp = staff_client.patch(
            f"/api/v1/admin/organizations/{created['id']}",
            json={"public_name": "New Name", "country": "US", "legal_name": "New Name LLC"},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["public_name"] == "New Name"
        assert resp.json()["country"] == "US"


class TestStates:
    def test_verifying_records_who_and_when(self, staff_client: TestClient):
        created = _create(staff_client, slug="to-verify", public_name="To Verify")

        resp = staff_client.patch(
            f"/api/v1/admin/organizations/{created['id']}",
            json={"status": "verified", "verification_basis": "domain ucoat.org"},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "verified"
        assert body["verified_at"] is not None, "verified without a moment it happened"
        assert body["verification_basis"] == "domain ucoat.org"

    def test_leaving_verified_clears_the_stamp(self, staff_client: TestClient):
        created = _create(staff_client, slug="verified-then-not", public_name="Verified Then Not")
        staff_client.patch(
            f"/api/v1/admin/organizations/{created['id']}",
            json={"status": "verified", "verification_basis": "registry entry"},
        )

        resp = staff_client.patch(
            f"/api/v1/admin/organizations/{created['id']}",
            json={"status": "suspended"},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "suspended"
        assert resp.json()["verified_at"] is None, "record still claims a verification that was withdrawn"


class TestAppointingADirector:
    def test_the_appointment_sets_both_role_and_organization(self, staff_client: TestClient, db: Session):
        created = _create(staff_client, slug="needs-a-head", public_name="Needs A Head")
        person = User(
            id=uuid.uuid4(),
            email="new-head@example.com",
            full_name="New Head",
            role=UserRole.TEACHER.value,
        )
        db.add(person)
        db.commit()

        resp = staff_client.post(
            f"/api/v1/admin/organizations/{created['id']}/director",
            json={"email": "new-head@example.com"},
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["director_emails"] == ["new-head@example.com"]

        db.refresh(person)
        assert person.role == UserRole.DIRECTOR.value
        assert str(person.organization_id) == created["id"], "a director filed under the wrong organization"

    def test_an_unknown_email_is_a_404(self, staff_client: TestClient):
        created = _create(staff_client, slug="nobody-here", public_name="Nobody Here")
        resp = staff_client.post(
            f"/api/v1/admin/organizations/{created['id']}/director",
            json={"email": "stranger@example.com"},
        )
        assert resp.status_code == 404, resp.text

    def test_platform_staff_are_not_appointable(self, staff_client: TestClient, db: Session):
        """The roles were split on purpose; an appointment must not merge
        them back by demoting an admin."""
        created = _create(staff_client, slug="not-for-staff", public_name="Not For Staff")
        other_staff = User(
            id=uuid.uuid4(),
            email="other-staff@equipbible.com",
            full_name="Other Staff",
            role=UserRole.ADMIN.value,
        )
        db.add(other_staff)
        db.commit()

        resp = staff_client.post(
            f"/api/v1/admin/organizations/{created['id']}/director",
            json={"email": "other-staff@equipbible.com"},
        )

        assert resp.status_code == 409, resp.text
        db.refresh(other_staff)
        assert other_staff.role == UserRole.ADMIN.value, "platform staff were quietly demoted"

    def test_a_director_cannot_appoint_themselves_anywhere(self, director_client: TestClient, db: Session):
        organization = Organization(id=uuid.uuid4(), slug="theirs", public_name="Theirs")
        db.add(organization)
        db.commit()

        resp = director_client.post(
            f"/api/v1/admin/organizations/{organization.id}/director",
            json={"email": "director@example.com"},
        )
        assert resp.status_code == 403, resp.text
