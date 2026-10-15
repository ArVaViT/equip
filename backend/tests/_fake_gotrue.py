"""Supabase Auth's admin API, as far as ``app.services.auth_admin`` uses it.

Answers at the HTTP level -- status codes and GoTrue's own error bodies --
so the parsing in ``auth_admin`` is exercised, not bypassed. Creating an
account writes its profile the way ``handle_new_user`` does in production,
because the service finds accounts through profiles.

Installed for every test by ``conftest`` with no accounts in it, so nothing
under test can reach a real GoTrue.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx

from app.models.user import User

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

#: What the fake refuses as breached, beside anything shorter than twelve.
BREACHED = frozenset({"password1234", "qwertyuiop12"})


@dataclass
class FakeAccount:
    id: uuid.UUID
    email: str
    password: str
    confirmed: bool
    metadata: dict[str, Any] = field(default_factory=dict)


class FakeGoTrue:
    def __init__(self) -> None:
        self.accounts: dict[uuid.UUID, FakeAccount] = {}
        self.calls: list[tuple[str, str]] = []
        self.db: Session | None = None
        #: Set to make every call fail the way an unreachable GoTrue does.
        self.down = False

    # -- seeding ---------------------------------------------------------

    def add_account(self, db: Session, *, email: str, confirmed: bool, password: str = "first-attempt-pw") -> User:
        """An account that exists before the test starts, with its profile."""
        account = FakeAccount(id=uuid.uuid4(), email=email, password=password, confirmed=confirmed)
        self.accounts[account.id] = account
        return self._write_profile(db, account, full_name="Earlier Attempt", locale="en")

    def by_email(self, email: str) -> FakeAccount | None:
        return next((a for a in self.accounts.values() if a.email == email), None)

    # -- the protocol ----------------------------------------------------

    def __call__(self, method: str, path: str, *, json: dict[str, Any] | None = None) -> httpx.Response:
        from app.services.auth_admin import _unavailable

        self.calls.append((method, path))
        if self.down:
            raise _unavailable("unreachable")
        parts = path.strip("/").split("/")
        if parts[:2] != ["admin", "users"]:
            return httpx.Response(404, json={"code": 404, "error_code": "not_found", "msg": "not found"})
        if method == "POST" and len(parts) == 2:
            return self._create(json or {})
        account = self.accounts.get(uuid.UUID(parts[2])) if len(parts) == 3 else None
        if account is None:
            return httpx.Response(404, json={"code": 404, "error_code": "user_not_found", "msg": "User not found"})
        if method == "GET":
            return httpx.Response(200, json=self._body(account))
        if method == "PUT":
            return self._update(account, json or {})
        return httpx.Response(405, json={"code": 405, "msg": "method not allowed"})

    def _weak(self, password: str) -> httpx.Response | None:
        if len(password) < 12 or password in BREACHED:
            return httpx.Response(
                422, json={"code": 422, "error_code": "weak_password", "msg": "Password is known to be weak"}
            )
        return None

    def _create(self, body: dict[str, Any]) -> httpx.Response:
        email = str(body["email"]).strip().lower()
        if self.by_email(email) is not None:
            return httpx.Response(
                422,
                json={"code": 422, "error_code": "email_exists", "msg": "A user with this email already exists"},
            )
        if (refused := self._weak(str(body.get("password", "")))) is not None:
            return refused
        account = FakeAccount(
            id=uuid.uuid4(),
            email=email,
            password=str(body["password"]),
            confirmed=bool(body.get("email_confirm")),
            metadata=dict(body.get("user_metadata") or {}),
        )
        self.accounts[account.id] = account
        assert self.db is not None, "FakeGoTrue.db is set by the fixture"
        self._write_profile(
            self.db,
            account,
            full_name=account.metadata.get("full_name", ""),
            locale=account.metadata.get("preferred_locale"),
        )
        return httpx.Response(200, json=self._body(account))

    def _update(self, account: FakeAccount, body: dict[str, Any]) -> httpx.Response:
        if "password" in body:
            if (refused := self._weak(str(body["password"]))) is not None:
                return refused
            account.password = str(body["password"])
        if body.get("email_confirm"):
            account.confirmed = True
        account.metadata.update(body.get("user_metadata") or {})
        return httpx.Response(200, json=self._body(account))

    @staticmethod
    def _body(account: FakeAccount) -> dict[str, Any]:
        return {
            "id": str(account.id),
            "email": account.email,
            "email_confirmed_at": datetime.now(UTC).isoformat() if account.confirmed else None,
            "user_metadata": account.metadata,
        }

    @staticmethod
    def _write_profile(db: Session, account: FakeAccount, *, full_name: str, locale: str | None) -> User:
        """What ``handle_new_user`` writes: a student in no organization."""
        from tests.conftest import NOBODY_BELONGS_ANYWHERE

        before = db.info.get(NOBODY_BELONGS_ANYWHERE, False)
        db.info[NOBODY_BELONGS_ANYWHERE] = True
        try:
            has_locale = locale in ("ru", "en", "de", "uk")
            profile = User(
                id=account.id,
                email=account.email,
                full_name=full_name,
                role="student",
                preferred_locale=locale if has_locale else "en",
                locale_source="chosen" if has_locale else "default",
            )
            db.add(profile)
            db.commit()
        finally:
            db.info[NOBODY_BELONGS_ANYWHERE] = before
        return profile
