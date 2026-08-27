"""A director administers one organization. Platform staff administer Equip.

Until 2026-08-26 those were one role. Forty-five routes were gated by
``require_admin``, and they were two unrelated things: twenty-six belong
to an organization — cohorts, ведомости, invitations, certificate
approval, its own settings — and nineteen belong to the platform: the
translation queue, user accounts, health, the audit log.

With one organization that was harmless. With two it is a leak, and not
a subtle one: the person who closes their own ведомость would, by the
same right, re-open the translation queue for every organization on the
platform and read everyone's audit log.

Organizations do not exist yet. This file exists now anyway, because the
role split is what makes every later step small — and because a test
written after the columns arrive would be a test written against
whatever the code happened to do.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_optional_user
from app.core.database import get_db
from app.main import app
from app.models.user import User, UserRole

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

#: Routes that belong to an organization. A director holds these.
ORGANIZATION_ROUTES = [
    ("GET", "/api/v1/cohorts"),
    ("GET", "/api/v1/admin/org-settings"),
    ("GET", "/api/v1/invitations"),
    ("GET", "/api/v1/certificates/admin/pending"),
]

#: Routes that belong to Equip itself. A director must not hold these,
#: whatever they are allowed to do inside their own organization.
PLATFORM_ROUTES = [
    ("GET", "/api/v1/admin/translations/needs-review"),
    ("GET", "/api/v1/admin/translations/queue-status"),
    ("GET", "/api/v1/users/admin/users"),
    ("GET", "/api/v1/audit"),
]


@pytest.fixture()
def director(db: Session) -> User:
    user = User(
        id=uuid.uuid4(),
        email="director@example.com",
        full_name="Director",
        role=UserRole.DIRECTOR.value,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture()
def director_client(db: Session, director: User) -> TestClient:
    def _override_db():
        yield db

    app.dependency_overrides[get_db] = lambda: _override_db()
    app.dependency_overrides[get_current_user] = lambda: director
    app.dependency_overrides[get_optional_user] = lambda: director
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc
    app.dependency_overrides.clear()


@pytest.mark.parametrize(("method", "path"), ORGANIZATION_ROUTES)
def test_a_director_may_administer_their_organization(director_client: TestClient, method: str, path: str):
    resp = director_client.request(method, path)
    assert resp.status_code != 403, f"{method} {path} refused a director: {resp.text[:200]}"


@pytest.mark.parametrize(("method", "path"), PLATFORM_ROUTES)
def test_a_director_may_not_administer_the_platform(director_client: TestClient, method: str, path: str):
    """The whole point of the split.

    A 403 here is the test passing. If one of these ever returns 200,
    a director of one organization is reading or changing something that
    belongs to all of them.
    """
    resp = director_client.request(method, path)
    assert resp.status_code == 403, f"{method} {path} let a director in: {resp.status_code}"


@pytest.mark.parametrize(("method", "path"), ORGANIZATION_ROUTES + PLATFORM_ROUTES)
def test_platform_staff_hold_both(admin_client: TestClient, method: str, path: str):
    """Platform staff administer every organization by definition — not
    because the two roles are the same thing."""
    resp = admin_client.request(method, path)
    assert resp.status_code != 403, f"{method} {path} refused platform staff: {resp.text[:200]}"


@pytest.mark.parametrize(("method", "path"), ORGANIZATION_ROUTES)
def test_a_teacher_is_not_a_director(client: TestClient, method: str, path: str):
    """A teacher teaches. Closing a ведомость, approving a certificate and
    inviting colleagues are the director's, and were the admin's before
    that — at no point were they a teacher's."""
    resp = client.request(method, path)
    assert resp.status_code == 403, f"{method} {path} let a teacher in: {resp.status_code}"
