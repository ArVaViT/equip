"""A platform admin can see Equip as someone else, and can change nothing.

Runs the real ``get_current_user`` (no override): only the token decoder is
faked, so the header is resolved exactly as in production.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import dependencies
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.main import app
from app.models.audit_log import AuditLog
from app.models.user import User, UserRole
from app.services import view_as

TOKENS: dict[str, str] = {}


@pytest.fixture()
def real_auth(db: Session, admin: User, student: User, teacher: User, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    TOKENS.update({"admin": str(admin.id), "student": str(student.id), "teacher": str(teacher.id)})
    monkeypatch.setattr(
        dependencies,
        "decode_access_token",
        lambda token: {"sub": uuid.UUID(TOKENS[token])} if token in TOKENS else None,
    )

    def _override_db():
        yield db

    app.dependency_overrides[get_db] = _override_db
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc
    app.dependency_overrides.clear()


def _auth(who: str, view_id: str | None = None) -> dict[str, str]:
    headers = {"Authorization": f"Bearer {who}"}
    if view_id:
        headers[view_as.HEADER] = view_id
    return headers


def _start(client: TestClient, email: str = "student@example.com") -> dict:
    response = client.post(
        "/api/v1/admin/view-as", json={"email": email, "reason": "dogfooding a submission"}, headers=_auth("admin")
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_starting_a_view_is_recorded_with_its_reason(
    real_auth: TestClient, db: Session, admin: User, student: User
) -> None:
    started = _start(real_auth, "STUDENT@example.com")
    assert started["person"]["email"] == "student@example.com"
    row = db.get(AuditLog, uuid.UUID(started["id"]))
    assert row is not None
    assert row.action == view_as.ACTION_START
    assert str(row.user_id) == str(admin.id)
    assert row.resource_id == str(student.id)
    assert row.details["reason"] == "dogfooding a submission"


def test_the_admin_sees_what_the_student_sees(real_auth: TestClient) -> None:
    view_id = _start(real_auth)["id"]
    # An admin-only read: refused, because the request is now the student.
    as_student = real_auth.get("/api/v1/users/admin/users", headers=_auth("admin", view_id))
    assert as_student.status_code == 403
    as_admin = real_auth.get("/api/v1/users/admin/users", headers=_auth("admin"))
    assert as_admin.status_code == 200


def test_no_write_gets_through(real_auth: TestClient, db: Session, student: User) -> None:
    view_id = _start(real_auth)["id"]
    before = student.preferred_locale
    for method in ("post", "put", "patch", "delete"):
        response = getattr(real_auth, method)("/api/v1/users/me/preferences", headers=_auth("admin", view_id))
        assert response.status_code == 403, (method, response.text)
        assert response.json()["detail"]["code"] == ErrorCode.VIEW_AS_READ_ONLY.value
    db.refresh(student)
    assert student.preferred_locale == before


def test_the_header_alone_makes_nobody_an_admin(real_auth: TestClient) -> None:
    view_id = _start(real_auth)["id"]
    response = real_auth.get("/api/v1/users/me/courses", headers=_auth("teacher", view_id))
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == ErrorCode.VIEW_AS_REFUSED.value


def test_only_an_admin_can_start_one(real_auth: TestClient) -> None:
    response = real_auth.post(
        "/api/v1/admin/view-as", json={"email": "student@example.com", "reason": "curious"}, headers=_auth("teacher")
    )
    assert response.status_code == 403


def test_a_view_of_another_admin_cannot_be_borrowed(real_auth: TestClient, db: Session) -> None:
    other = User(id=uuid.uuid4(), email="other-admin@example.com", full_name="Other", role=UserRole.ADMIN.value)
    db.add(other)
    db.commit()
    TOKENS["other"] = str(other.id)
    view_id = _start(real_auth)["id"]
    response = real_auth.get("/api/v1/users/me/courses", headers=_auth("other", view_id))
    assert response.status_code == 403


def test_an_ended_view_stops_working(real_auth: TestClient) -> None:
    view_id = _start(real_auth)["id"]
    assert real_auth.get("/api/v1/users/me/courses", headers=_auth("admin", view_id)).status_code == 200
    assert real_auth.post(f"/api/v1/admin/view-as/{view_id}/end", headers=_auth("admin")).status_code == 204
    response = real_auth.get("/api/v1/users/me/courses", headers=_auth("admin", view_id))
    assert response.status_code == 403


def test_a_view_runs_out_after_thirty_minutes(real_auth: TestClient, db: Session) -> None:
    view_id = _start(real_auth)["id"]
    row = db.get(AuditLog, uuid.UUID(view_id))
    assert row is not None
    row.created_at = datetime.now(UTC) - view_as.TTL - timedelta(seconds=1)
    db.commit()
    response = real_auth.get("/api/v1/users/me/courses", headers=_auth("admin", view_id))
    assert response.status_code == 403


def test_garbage_in_the_header_is_refused_not_ignored(real_auth: TestClient) -> None:
    response = real_auth.get("/api/v1/users/me/courses", headers=_auth("admin", "not-a-view"))
    assert response.status_code == 403


def test_the_session_turns_read_only(db: Session, admin: User, student: User) -> None:
    row = view_as.start(db, admin, student, "check")
    assert view_as.resolve(db, admin, str(row.id)).id == student.id
    assert db.info.get("equip_view_as_read_only") is True
