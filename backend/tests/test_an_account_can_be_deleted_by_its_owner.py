"""An account can be deleted by its owner — softly, visibly, reversibly.

``DELETE /users/me`` closes the account (``deleted_at`` + ``deactivated_at``),
ends every session, and hides the person from everybody else; nothing the
school keeps is removed. ``POST /users/me/restore`` brings it back, but only
for somebody who opened a link emailed to the address *after* the deletion. These tests pin each half,
the gate that must not stand in the way of leaving, and the places where
another person would otherwise still see a name.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.consent_gate import consent_subject
from app.api.dependencies import Caller, get_caller_even_if_closed, get_current_user, refuse_if_closed
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.main import app
from app.models.audit_log import AuditLog
from app.models.course import Course
from app.models.enrollment import Enrollment
from app.models.legal_acceptance import LegalAcceptance
from app.models.organization import MembershipRole, MembershipSource, OrganizationMember
from app.models.user import User, UserRole
from app.services import auth_admin, deleted_person

from .conftest import STUDENT_ID, TEACHER_ID, TEST_ORGANIZATION_ID

if TYPE_CHECKING:
    from collections.abc import Iterator

    from fastapi import HTTPException
    from sqlalchemy.orm import Session

ME = "/api/v1/users/me"
RESTORE = "/api/v1/users/me/restore"
TOKEN = "the-person-s-own-access-token"


@pytest.fixture()
def ended_sessions(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record every ``sign_out_everywhere`` instead of calling Supabase."""
    calls: list[str] = []

    def fake(token: str) -> bool:
        calls.append(token)
        return True

    monkeypatch.setattr(auth_admin, "sign_out_everywhere", fake)
    return calls


def _client_as(
    db: Session,
    user: User,
    *,
    signed_in_at: datetime | None = None,
    method: str = "magiclink",
    amr: list[dict[str, object]] | None = None,
) -> Iterator[TestClient]:
    """A client whose token names ``user`` — whatever state the account is in.

    ``get_current_user`` is left alone on purpose: it is the guard under test
    for every other route, so it reads the real row.
    """
    if amr is None:
        amr = [] if signed_in_at is None else [{"method": method, "timestamp": int(signed_in_at.timestamp())}]

    def _db() -> Iterator[Session]:
        yield db

    def _caller() -> Caller:
        db.refresh(user)
        return Caller(user=user, claims={"sub": str(user.id), "amr": amr}, token=TOKEN)

    def _current() -> User:
        db.refresh(user)
        refuse_if_closed(user)
        return user

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_caller_even_if_closed] = _caller
    app.dependency_overrides[get_current_user] = _current
    app.dependency_overrides[consent_subject] = lambda: None if user.deactivated_at else user
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc
    app.dependency_overrides.clear()


@pytest.fixture()
def me(db: Session, teacher: User, student: User) -> Iterator[TestClient]:
    yield from _client_as(db, student)


# ── Deleting ───────────────────────────────────────────────────────────


def test_deleting_closes_the_account_and_keeps_everything_the_school_holds(
    me: TestClient, db: Session, student: User, ended_sessions: list[str]
) -> None:
    db.add(Course(id="del-course", status="published", created_by=TEACHER_ID))
    db.add(Enrollment(id="del-enr", user_id=STUDENT_ID, course_id="del-course", progress=40))
    db.commit()

    assert me.delete(ME).status_code == 204

    db.refresh(student)
    assert student.deleted_at is not None
    assert student.deactivated_at is not None
    # Nothing physical: the enrolment, and the profile itself, are still there.
    assert db.get(Enrollment, "del-enr") is not None
    assert db.get(User, STUDENT_ID) is not None
    # Every session ended, with the person's own token.
    assert ended_sessions == [TOKEN]
    audit = db.query(AuditLog).filter(AuditLog.resource_id == str(STUDENT_ID)).one()
    assert audit.action == "delete"
    assert audit.details == {"mode": "self", "role": "student"}


def test_after_deleting_every_other_route_answers_account_deleted(
    me: TestClient, student: User, ended_sessions: list[str]
) -> None:
    me.delete(ME)
    response = me.get("/api/v1/users/me/courses")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == ErrorCode.ACCOUNT_DELETED.value


def test_the_guard_tells_a_deletion_from_a_deactivation(db: Session, student: User) -> None:
    """Two codes, because the client does two different things with them."""
    now = datetime.now(UTC)
    student.deactivated_at = now
    with pytest.raises(Exception) as by_admin:
        refuse_if_closed(student)
    assert by_admin.value.detail["code"] == ErrorCode.ACCOUNT_DEACTIVATED.value  # type: ignore[attr-defined]

    student.deleted_at = now
    with pytest.raises(Exception) as by_owner:
        refuse_if_closed(student)
    exc: HTTPException = by_owner.value  # type: ignore[assignment]
    assert exc.status_code == 403
    assert exc.detail["code"] == ErrorCode.ACCOUNT_DELETED.value  # type: ignore[index]


def test_deleting_twice_is_not_an_error(me: TestClient, db: Session, student: User, ended_sessions: list[str]) -> None:
    assert me.delete(ME).status_code == 204
    db.refresh(student)
    first = student.deleted_at

    assert me.delete(ME).status_code == 204
    db.refresh(student)
    assert student.deleted_at == first
    assert len(ended_sessions) == 1


def test_an_account_an_administrator_switched_off_cannot_be_deleted_over_it(
    me: TestClient, db: Session, student: User, ended_sessions: list[str]
) -> None:
    student.deactivated_at = datetime.now(UTC)
    db.commit()

    response = me.delete(ME)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == ErrorCode.ACCOUNT_DEACTIVATED.value
    db.refresh(student)
    assert student.deleted_at is None
    assert ended_sessions == []


def test_a_failed_sign_out_does_not_undo_the_deletion(
    me: TestClient, db: Session, student: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auth_admin, "sign_out_everywhere", lambda token: False)
    assert me.delete(ME).status_code == 204
    db.refresh(student)
    assert student.deleted_at is not None


def test_platform_staff_cannot_delete_themselves(
    db: Session, teacher: User, admin: User, ended_sessions: list[str]
) -> None:
    for client in _client_as(db, admin):
        response = client.delete(ME)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == ErrorCode.ACCOUNT_CANNOT_DELETE.value
        assert response.json()["detail"]["context"]["reason"] == "platform_staff"
    db.refresh(admin)
    assert admin.deleted_at is None


def _direct(db: Session, user: User) -> None:
    membership = db.query(OrganizationMember).filter_by(user_id=user.id).first()
    if membership is None:
        membership = OrganizationMember(
            user_id=user.id,
            organization_id=TEST_ORGANIZATION_ID,
            role=MembershipRole.DIRECTOR.value,
            joined_via=MembershipSource.ADMIN.value,
        )
        db.add(membership)
    membership.role = MembershipRole.DIRECTOR.value
    user.role = UserRole.DIRECTOR.value
    db.commit()


def test_the_only_director_of_a_school_cannot_leave_it_without_one(
    db: Session, teacher: User, ended_sessions: list[str]
) -> None:
    _direct(db, teacher)
    for client in _client_as(db, teacher):
        response = client.delete(ME)
        assert response.status_code == 409
        detail = response.json()["detail"]
        assert detail["context"]["reason"] == "only_director"
        assert detail["context"]["organizations"] == ["Test Organization"]


def test_a_director_with_a_colleague_may_leave(db: Session, teacher: User, ended_sessions: list[str]) -> None:
    _direct(db, teacher)
    colleague = User(id=uuid.uuid4(), email="second@example.com", full_name="Second", role=UserRole.TEACHER.value)
    db.add(colleague)
    db.commit()
    _direct(db, colleague)

    for client in _client_as(db, teacher):
        assert client.delete(ME).status_code == 204


# ── Leaving must not wait for consent ──────────────────────────────────


def test_somebody_who_owes_a_signature_can_still_leave(
    me: TestClient, db: Session, student: User, ended_sessions: list[str]
) -> None:
    """The policy calls deleting the account the way to withdraw consent."""
    db.query(LegalAcceptance).filter(LegalAcceptance.user_id == STUDENT_ID).delete()
    db.commit()

    # Every other write is still refused...
    refused = me.post("/api/v1/users/me/onboarding/complete")
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == ErrorCode.LEGAL_CONSENT_REQUIRED.value
    # ...and leaving is not.
    assert me.delete(ME).status_code == 204


def test_the_exemption_is_exact_and_not_a_prefix() -> None:
    from app.api.consent_gate import is_exempt

    assert is_exempt("/api/v1/users/me")
    assert not is_exempt("/api/v1/users/me/onboarding/complete")
    assert not is_exempt("/api/v1/users/me/restore")


# ── Restoring ──────────────────────────────────────────────────────────


def _delete(db: Session, user: User, *, at: datetime) -> None:
    user.deleted_at = at
    user.deactivated_at = at
    db.commit()


@pytest.mark.parametrize("method", ["magiclink", "otp", "recovery"])
def test_an_email_link_opened_after_the_deletion_restores_the_account(
    db: Session, teacher: User, student: User, method: str
) -> None:
    deleted = datetime.now(UTC) - timedelta(days=3)
    _delete(db, student, at=deleted)

    for client in _client_as(db, student, signed_in_at=deleted + timedelta(days=2), method=method):
        assert client.post(RESTORE).status_code == 204
        db.refresh(student)
        assert student.deleted_at is None
        assert student.deactivated_at is None
        # And the account works again.
        assert client.get("/api/v1/users/me/courses").status_code == 200
    audit = db.query(AuditLog).filter(AuditLog.action == "restore").one()
    assert audit.details is not None and audit.details["mode"] == "self"


@pytest.mark.parametrize("method", ["password", "oauth", "totp", "anonymous"])
def test_a_password_or_google_sign_in_reaches_the_screen_but_does_not_restore(
    db: Session, teacher: User, student: User, method: str
) -> None:
    """Vadym, 2026-10-17: signing in shows «restore», the restore is by the emailed link."""
    deleted = datetime.now(UTC) - timedelta(hours=1)
    _delete(db, student, at=deleted)

    for client in _client_as(db, student, signed_in_at=datetime.now(UTC), method=method):
        response = client.post(RESTORE)
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == ErrorCode.ACCOUNT_RESTORE_NEEDS_EMAIL_LINK.value
    db.refresh(student)
    assert student.deleted_at is not None


def test_a_link_opened_before_the_deletion_cannot_restore_it(db: Session, teacher: User, student: User) -> None:
    """The laptop at church that nobody closed proves nothing about who holds it now."""
    deleted = datetime.now(UTC) - timedelta(hours=1)
    _delete(db, student, at=deleted)

    for client in _client_as(db, student, signed_in_at=deleted - timedelta(minutes=5)):
        response = client.post(RESTORE)
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == ErrorCode.ACCOUNT_RESTORE_NEEDS_EMAIL_LINK.value
    db.refresh(student)
    assert student.deleted_at is not None


def test_only_the_email_entry_s_time_counts(db: Session, teacher: User, student: User) -> None:
    """A fresh password step must not lend its timestamp to an old link."""
    deleted = datetime.now(UTC) - timedelta(hours=1)
    _delete(db, student, at=deleted)
    stale_link_fresh_password = [
        {"method": "magiclink", "timestamp": int((deleted - timedelta(days=1)).timestamp())},
        {"method": "password", "timestamp": int(datetime.now(UTC).timestamp())},
    ]
    for client in _client_as(db, student, amr=stale_link_fresh_password):
        assert client.post(RESTORE).status_code == 403

    fresh_link = [
        {"method": "password", "timestamp": int((deleted - timedelta(days=1)).timestamp())},
        {"method": "otp", "timestamp": int(datetime.now(UTC).timestamp())},
    ]
    for client in _client_as(db, student, amr=fresh_link):
        assert client.post(RESTORE).status_code == 204


def test_a_malformed_amr_is_refused_not_crashed(db: Session, teacher: User, student: User) -> None:
    _delete(db, student, at=datetime.now(UTC) - timedelta(days=1))
    for amr in ([{"method": "magiclink"}], [{"method": "magiclink", "timestamp": "soon"}], ["magiclink"]):
        for client in _client_as(db, student, amr=amr):
            assert client.post(RESTORE).status_code == 403


def test_a_token_that_does_not_say_when_it_signed_in_cannot_restore(db: Session, teacher: User, student: User) -> None:
    _delete(db, student, at=datetime.now(UTC) - timedelta(days=1))
    for client in _client_as(db, student, signed_in_at=None):
        assert client.post(RESTORE).status_code == 403


def test_an_administrator_s_deactivation_is_not_undone_by_the_owner(db: Session, teacher: User, student: User) -> None:
    student.deactivated_at = datetime.now(UTC) - timedelta(days=1)
    db.commit()
    for client in _client_as(db, student, signed_in_at=datetime.now(UTC)):
        response = client.post(RESTORE)
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == ErrorCode.ACCOUNT_DEACTIVATED.value
    db.refresh(student)
    assert student.deactivated_at is not None


def test_restoring_an_active_account_changes_nothing(me: TestClient, student: User) -> None:
    assert me.post(RESTORE).status_code == 204


def test_the_admin_list_shows_it_and_the_admin_restore_clears_both(
    admin_client: TestClient, db: Session, student: User
) -> None:
    _delete(db, student, at=datetime.now(UTC))

    rows = {row["id"]: row for row in admin_client.get("/api/v1/users/admin/users").json()}
    assert rows[str(STUDENT_ID)]["deleted_at"] is not None
    # Platform staff see who it is — otherwise nobody could restore it.
    assert rows[str(STUDENT_ID)]["email"] == "student@example.com"

    assert admin_client.post(f"/api/v1/users/admin/users/{STUDENT_ID}/restore").status_code == 204
    db.refresh(student)
    assert student.deleted_at is None
    assert student.deactivated_at is None


# ── What everybody else sees ───────────────────────────────────────────


def test_the_label_is_in_the_language_of_the_request() -> None:
    assert deleted_person.label("ru") == "Удалённый пользователь"
    assert deleted_person.label("uk") == "Видалений користувач"
    assert deleted_person.label("de") == "Gelöschter Nutzer"
    assert deleted_person.label("en") == "Deleted user"
    assert set(deleted_person.LABELS) == {"en", "ru", "de", "uk"}


def test_a_course_s_author_tab_does_not_show_a_deleted_teacher(
    anon_client: TestClient, db: Session, teacher: User
) -> None:
    db.add(Course(id="del-author", status="published", created_by=TEACHER_ID, title="Acts"))
    teacher.avatar_url = "https://example.com/face.png"
    db.commit()
    before = anon_client.get("/api/v1/courses/del-author/author").json()
    assert before["name"] == "Test Teacher"

    _delete(db, teacher, at=datetime.now(UTC))

    for locale, words in (("ru", "Удалённый пользователь"), ("de", "Gelöschter Nutzer")):
        body = anon_client.get("/api/v1/courses/del-author/author", headers={"Accept-Language": locale}).json()
        assert body["name"] == words
        assert body["avatar_url"] is None
    # The course itself stays with the school.
    assert anon_client.get("/api/v1/courses/del-author").status_code == 200


def test_the_helpers_hide_only_a_deleted_person() -> None:
    gone = datetime.now(UTC)
    assert deleted_person.shown_name("Anna", None) == "Anna"
    assert deleted_person.shown_email("anna@example.com", None) == "anna@example.com"
    assert deleted_person.shown_avatar("https://x/a.png", None) == "https://x/a.png"
    token = deleted_person.set_request_locale("uk-UA,uk;q=0.9")
    try:
        assert deleted_person.shown_name("Anna", gone) == "Видалений користувач"
    finally:
        deleted_person.request_locale.reset(token)
    assert deleted_person.shown_email("anna@example.com", gone) == ""
    assert deleted_person.shown_avatar("https://x/a.png", gone) is None


def test_the_history_of_a_mark_does_not_name_a_teacher_who_left(
    db: Session, teacher: User, student: User, admin_client: TestClient
) -> None:
    db.add(Course(id="del-hist", status="published", created_by=TEACHER_ID, grading_scheme="letter"))
    db.add(Enrollment(id="enr-del-hist", user_id=STUDENT_ID, course_id="del-hist", progress=100))
    db.add(
        AuditLog(
            user_id=TEACHER_ID,
            action="grade_override_set",
            resource_type="student_grade",
            resource_id="x",
            details={"student_id": str(STUDENT_ID), "course_id": "del-hist", "override_code": "B"},
        )
    )
    db.commit()
    _delete(db, teacher, at=datetime.now(UTC))

    entries = admin_client.get(
        f"/api/v1/grades/course/del-hist/student/{STUDENT_ID}/history", headers={"Accept-Language": "ru"}
    ).json()
    assert [e["actor_name"] for e in entries] == ["Удалённый пользователь"]


# ── Supabase: what is asked of it ──────────────────────────────────────


def test_sign_out_everywhere_revokes_every_session_with_the_person_s_own_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_post(url: str, **kwargs: object) -> httpx.Response:
        seen["url"] = url
        seen.update(kwargs)
        return httpx.Response(204)

    monkeypatch.setattr(auth_admin.httpx, "post", fake_post)
    assert auth_admin.sign_out_everywhere(TOKEN) is True
    assert str(seen["url"]).endswith("/auth/v1/logout")
    assert seen["params"] == {"scope": "global"}
    assert seen["headers"]["Authorization"] == f"Bearer {TOKEN}"  # type: ignore[index]


def test_sign_out_everywhere_says_so_when_supabase_does_not_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(url: str, **kwargs: object) -> httpx.Response:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(auth_admin.httpx, "post", boom)
    assert auth_admin.sign_out_everywhere(TOKEN) is False
    monkeypatch.setattr(auth_admin.httpx, "post", lambda url, **kw: httpx.Response(401))
    assert auth_admin.sign_out_everywhere(TOKEN) is False


def test_the_supabase_fallback_keeps_the_moment_of_sign_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """Restore reads ``amr``; a token verified by Supabase rather than locally must carry it too."""
    import jwt

    from app.core import security

    signed_in = int(datetime.now(UTC).timestamp())
    token = jwt.encode(
        {"sub": str(STUDENT_ID), "aud": "authenticated", "amr": [{"method": "otp", "timestamp": signed_in}]},
        "some-other-project-secret",
        algorithm="HS256",
    )
    monkeypatch.setattr(
        security.httpx,
        "get",
        lambda url, **kw: httpx.Response(200, json={"id": str(STUDENT_ID), "aud": "authenticated", "role": "x"}),
    )
    security._supabase_cache.clear()
    payload = security._validate_via_supabase(token)
    assert payload is not None
    assert payload["amr"] == [{"method": "otp", "timestamp": signed_in}]
