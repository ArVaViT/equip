"""The three things the backend asks of Supabase Auth's admin API.

Until 2026-10-15 the backend never wrote to Supabase Auth: an invited
person signed up like anybody else, waited for a confirmation email, came
back, and only then could redeem their invitation. That second email was
where invited people were lost — five of nine email sign-ups confirmed
between 2026-08-31 and 2026-10-15, every one of the rest an invitee — and
it proved nothing the invitation had not proved already: the invitation
link was delivered to that same mailbox.

So an invitation now creates the account itself (``register_by_invitation``
in ``invitation_service``), and these are the calls it needs:

* read an account — is it confirmed;
* create one already confirmed;
* confirm one that exists unconfirmed, with the password chosen now.

Nothing here decides *whether* to do any of that. The service does; this
module only speaks GoTrue's protocol and turns its answers into ours.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from fastapi import status

from app.core.config import settings
from app.core.errors import ErrorCode, equip_error

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class AuthAccount:
    """An account as Supabase Auth holds it, reduced to what we decide on."""

    id: UUID
    #: The address is proven: confirmed by a link, by an OAuth provider, or
    #: by an administrator. Only an unconfirmed account may be taken over by
    #: somebody holding an invitation to its address.
    confirmed: bool


class EmailTaken(Exception):
    """``create_confirmed`` lost to an account created a moment earlier."""


def _unavailable(reason: str) -> Exception:
    return equip_error(
        ErrorCode.AUTH_UNAVAILABLE,
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        message="The sign-in service did not answer. Nothing was changed; try again in a moment.",
        context={"reason": reason},
    )


def _error_code(response: httpx.Response) -> str | None:
    """GoTrue's machine-readable code, in either of the shapes it answers with.

    Unversioned requests get ``{"code": 422, "error_code": "weak_password"}``;
    the 2024-01-01 API version moves the string into ``code``.
    """
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    for key in ("error_code", "code"):
        value = body.get(key)
        if isinstance(value, str):
            return value
    return None


def _call(method: str, path: str, *, json: dict[str, Any] | None = None) -> httpx.Response:
    base = settings.SUPABASE_URL
    key = settings.SUPABASE_SERVICE_ROLE_KEY
    if not base or not key:
        # A deployment without the secret key cannot create accounts, and
        # must say so rather than pretend the address was the problem.
        raise _unavailable("unconfigured")
    try:
        return httpx.request(
            method,
            f"{base.rstrip('/')}/auth/v1{path}",
            json=json,
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        logger.warning("auth admin %s %s failed: %s", method, path.split("/")[2], type(exc).__name__)
        raise _unavailable("unreachable") from exc


def _refuse(response: httpx.Response, what: str) -> Exception:
    """Our answer to a refusal from GoTrue: the password, or "try again"."""
    code = _error_code(response)
    if code == "weak_password":
        return equip_error(
            ErrorCode.AUTH_WEAK_PASSWORD,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            message="Choose a different password: this one is too short or appears in a known breach",
            context={"field": "password"},
        )
    # The status and code, never the body: a refusal can echo the address.
    logger.warning("auth admin %s refused: %s %s", what, response.status_code, code)
    return _unavailable(code or str(response.status_code))


def get_account(user_id: UUID) -> AuthAccount | None:
    response = _call("GET", f"/admin/users/{user_id}")
    if response.status_code == status.HTTP_404_NOT_FOUND:
        return None
    if response.status_code != status.HTTP_200_OK:
        raise _refuse(response, "read")
    body = response.json()
    return AuthAccount(id=UUID(body["id"]), confirmed=bool(body.get("email_confirmed_at")))


def create_confirmed(email: str, password: str, metadata: dict[str, str]) -> UUID:
    """A new account whose address counts as proven from the start.

    ``handle_new_user`` writes the profile from ``metadata`` exactly as it
    does for a sign-up, so the name and language land where they always do.
    """
    response = _call(
        "POST",
        "/admin/users",
        json={"email": email, "password": password, "email_confirm": True, "user_metadata": metadata},
    )
    if _error_code(response) == "email_exists":
        raise EmailTaken
    if response.status_code not in (status.HTTP_200_OK, status.HTTP_201_CREATED):
        raise _refuse(response, "create")
    return UUID(response.json()["id"])


def confirm_with_password(user_id: UUID, password: str, metadata: dict[str, str]) -> None:
    """Confirm an unconfirmed account and give it the password chosen now.

    GoTrue's own sign-up will not do this: asked again for an unconfirmed
    address it mails a new link and keeps the first attempt's password
    (``internal/api/signup.go``: "do not update the user"), so a person who
    retyped a different password could never sign in with it.
    """
    response = _call(
        "PUT",
        f"/admin/users/{user_id}",
        json={"password": password, "email_confirm": True, "user_metadata": metadata},
    )
    if response.status_code != status.HTTP_200_OK:
        raise _refuse(response, "confirm")
