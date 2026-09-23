"""The consent gate, from the side the client does not control.

``FirstRunFlow.tsx`` covers the app until somebody accepts. It is the right
screen and it is the wrong place for the only copy of the rule: it runs on the
reader's machine. A second tab pointed straight at the API, a bundle cached
from before the gate shipped, a script somebody wrote against ``/api/v1``, or
the dialog simply failing to mount — and the platform accepted every write it
was offered while ``legal_acceptances`` held nothing at all.

These tests pin what the server now does about that: a change from somebody
who has not accepted is refused, a read is not, the way out of the gate stays
open, and nothing here has an opinion about a caller with no session.

The last test is the one that keeps the rest honest. A guard test passes just
as happily when the thing it guards has been deleted — so it mutates the gate,
three ways, and requires the refusal to disappear each time. If a weakening of
``app.api.consent_gate`` does not change what these tests see, they are not
testing it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.api import consent_gate
from app.legal import LEGAL_DOCUMENTS, required_slugs

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session

ACCEPT = "/api/v1/legal/acceptances"
PREFERENCES = "/api/v1/users/me/preferences"
COURSES = "/api/v1/courses"

#: The specimen write these tests hold the gate against.
#:
#: It used to be ``PREFERENCES``, which is now exempt (see
#: ``TestTheLanguageOfTheQuestionComesFirst`` below) — and a guard test whose
#: specimen is exempt proves nothing at all. This one is a POST with no body,
#: idempotent, reachable by any signed-in person, and it changes something:
#: everything the old specimen gave these tests, minus the exemption.
A_WRITE = "/api/v1/users/me/onboarding/complete"


@pytest.fixture(autouse=True)
def _they_arrive_having_signed_nothing(nobody_has_signed_anything: None) -> None:
    """Every fixture user in this file has accepted nothing yet.

    The suite otherwise hands every fabricated profile the current
    acceptances, because several hundred tests write something and are not
    about consent. This file is about exactly that, so the seeding is off.
    """


def _accept_everything(client: TestClient) -> None:
    for slug, version in LEGAL_DOCUMENTS.items():
        response = client.post(ACCEPT, json={"slug": slug, "version": version, "locale": "en"})
        assert response.status_code == 201, response.text


def _code(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


def test_a_change_from_somebody_who_has_not_accepted_is_refused(student_client: TestClient) -> None:
    response = student_client.post(A_WRITE)

    assert response.status_code == 403, response.text
    assert _code(response) == "legal.consent_required"


def test_the_refusal_names_what_is_still_owed(student_client: TestClient) -> None:
    """A client that meets this opens the gate on those documents, not on a guess."""
    response = student_client.post(A_WRITE)

    outstanding = response.json()["detail"]["context"]["outstanding"]
    assert set(outstanding) == set(required_slugs("student"))


def test_the_same_change_goes_through_once_they_have_accepted(student_client: TestClient) -> None:
    _accept_everything(student_client)

    response = student_client.post(A_WRITE)

    assert response.status_code == 200, response.text


def test_a_teacher_is_held_to_it_too(client: TestClient) -> None:
    """Not a student rule. Whoever has not signed cannot author either."""
    refused = client.post(COURSES, json={"title": "Acts"})
    assert refused.status_code == 403
    assert _code(refused) == "legal.consent_required"

    _accept_everything(client)

    allowed = client.post(COURSES, json={"title": "Acts"})
    assert allowed.status_code in (200, 201), allowed.text


def test_reading_is_never_blocked(student_client: TestClient) -> None:
    """Somebody mid-gate still has a dashboard behind the dialog.

    Refusing reads would make the gate a sign-out, and it would break the
    screen that shows them what they are being asked to accept.
    """
    assert student_client.get("/api/v1/courses").status_code == 200
    assert student_client.get("/api/v1/legal/acceptances/me").status_code == 200


def test_the_way_out_of_the_gate_is_not_behind_the_gate(student_client: TestClient) -> None:
    """Accepting is a POST. A gate that closes its own exit is a wall."""
    assert student_client.get("/api/v1/legal/documents/privacy").status_code == 200

    response = student_client.post(
        ACCEPT,
        json={"slug": "privacy", "version": LEGAL_DOCUMENTS["privacy"], "locale": "en"},
    )

    assert response.status_code == 201, response.text


def test_a_caller_with_no_session_is_not_this_gate_s_business(anon_client: TestClient) -> None:
    """The uptime checks and the Datadog Synthetics runs are anonymous.

    Nobody is behind them who could accept anything, and they reach nothing
    authenticated: whatever gate a route already had still answers them. This
    one has nothing to say, and says nothing — a synthetic run must never be
    told to go and read the privacy policy.
    """
    response = anon_client.post(A_WRITE, headers={"user-agent": "Datadog/Synthetics"})

    assert response.status_code in (401, 403)
    assert _code(response) != "legal.consent_required"


def test_health_answers_a_probe_regardless(student_client: TestClient) -> None:
    assert student_client.get("/health").status_code == 200


def test_every_mutating_route_under_the_api_carries_the_gate(student_client: TestClient) -> None:
    """Declared once on ``include_router``, so a route written tomorrow is
    covered without anybody remembering to cover it. This is the test that
    notices if that declaration is moved, narrowed, or dropped.

    Driven from the OpenAPI schema rather than from a hand-kept list, and
    asserted by making the request rather than by reading FastAPI's internals:
    what matters is the answer the route gives, and the schema is where "every
    route" is actually written down. Only the paths that take no parameters
    are called — the rest would need a real id to reach the handler, and the
    gate runs long before the handler either way.
    """
    from app.main import app

    schema = app.openapi()
    called: list[str] = []
    for path, operations in schema["paths"].items():
        if not path.startswith("/api/v1") or "{" in path:
            continue
        if any(path.startswith(prefix) for prefix in consent_gate.EXEMPT_PREFIXES):
            continue
        for method in operations:
            if method.upper() not in consent_gate.MUTATING_METHODS:
                continue
            response = student_client.request(method.upper(), path, json={})
            assert _code(response) == "legal.consent_required", f"{method.upper()} {path} -> {response.text}"
            called.append(f"{method.upper()} {path}")

    assert len(called) >= 10, called


class TestTheseTestsWouldNoticeIfTheGateWentAway:
    """Mutation check: weaken the gate, and the refusal must disappear.

    Each case removes exactly one thing the gate relies on. If the request is
    still refused afterwards, the 403 above was coming from somewhere else and
    the tests in this file prove nothing about ``consent_gate``.
    """

    def test_with_post_no_longer_counted_as_a_change(
        self, student_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(consent_gate, "MUTATING_METHODS", frozenset())

        assert student_client.post(A_WRITE).status_code == 200

    def test_with_the_registry_answering_that_nothing_is_owed(
        self, student_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(consent_gate, "user_owes_consent", lambda db, user: ())

        assert student_client.post(A_WRITE).status_code == 200

    def test_with_the_route_added_to_the_exemptions(
        self, student_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(consent_gate, "EXEMPT_PREFIXES", ("/api/v1/users/",))

        assert student_client.post(A_WRITE).status_code == 200


class TestWhatTheRegistrySays:
    """The gate asks the registry; it does not re-derive the answer.

    Which documents a role signs, and whether a new version needs signing at
    all, are properties of the document registry. This file's job is to show
    that the gate reads them from there — so that adding a document, or
    publishing a correction that nobody has to re-sign, changes one table and
    nothing in ``consent_gate``.
    """

    def test_holding_every_current_version_owes_nothing(self) -> None:
        accepted = {(slug, version) for slug, version in LEGAL_DOCUMENTS.items()}

        assert consent_gate.outstanding_slugs("student", accepted) == ()

    def test_holding_an_old_version_owes_that_document(self) -> None:
        accepted = {(slug, "0.0") for slug in LEGAL_DOCUMENTS}

        assert set(consent_gate.outstanding_slugs("student", accepted)) == set(required_slugs("student"))

    def test_holding_nothing_owes_everything(self) -> None:
        assert set(consent_gate.outstanding_slugs("teacher", set())) == set(required_slugs("teacher"))


def test_a_person_who_owes_one_document_of_two_is_still_stopped(student_client: TestClient, db: Session) -> None:
    """Partial consent is not consent, and the error says which half is missing."""
    slug = next(iter(LEGAL_DOCUMENTS))
    accepted = student_client.post(ACCEPT, json={"slug": slug, "version": LEGAL_DOCUMENTS[slug], "locale": "en"})
    assert accepted.status_code == 201, accepted.text

    response = student_client.post(A_WRITE)

    assert response.status_code == 403
    assert slug not in response.json()["detail"]["context"]["outstanding"]


class TestTheGateDoesNotReadATokenItHasNoOpinionAbout:
    """What the gate looks at, and — the point of this class — what it does not.

    ``/api/v1/internal/`` has been on ``EXEMPT_PREFIXES`` since the gate
    shipped, but the exemption could not take effect: the subject was
    declared as ``Depends(get_optional_user)``, and FastAPI resolves a
    declared dependency *before* the body that consults the exemption list.
    So every request under ``/api/v1`` had its bearer header decoded,
    including the minutely cron tick, whose ``Authorization`` carries the
    worker's shared secret rather than a JWT. Each one logged
    ``JWT decode failed: Not enough segments`` — 1,747 of them over two days
    in September 2026, about 90% of the backend's warning volume.

    These tests fail if the subject goes back to being resolved eagerly.
    """

    @staticmethod
    def _request(method: str, path: str) -> Request:
        return Request(
            {
                "type": "http",
                "method": method,
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": [],
                "scheme": "https",
                "server": ("api.equipbible.com", 443),
            }
        )

    @staticmethod
    def _secret() -> HTTPAuthorizationCredentials:
        """What Vercel Cron sends: a shared secret, which is not a JWT."""
        return HTTPAuthorizationCredentials(scheme="Bearer", credentials="a-shared-secret-with-no-dots")

    @pytest.fixture()
    def _tokens_read(self, monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
        seen: list[str | None] = []

        def _spy(token: str | None, session: Session) -> None:
            seen.append(token)
            return None

        monkeypatch.setattr(consent_gate, "resolve_optional_user", _spy)
        return seen

    def test_a_read_is_decided_without_the_token(self, db: Session, _tokens_read: list[str | None]) -> None:
        assert consent_gate.consent_subject(self._request("GET", COURSES), self._secret(), db) is None
        assert _tokens_read == []

    def test_the_cron_worker_is_decided_without_the_token(self, db: Session, _tokens_read: list[str | None]) -> None:
        """A POST — so the method alone does not save it — on an exempt path."""
        request = self._request("POST", "/api/v1/internal/translation-worker")

        assert consent_gate.consent_subject(request, self._secret(), db) is None
        assert _tokens_read == []

    def test_a_change_the_gate_judges_still_reads_the_token(self, db: Session, _tokens_read: list[str | None]) -> None:
        """The exemptions must not have turned the gate off for real traffic."""
        consent_gate.consent_subject(self._request("POST", A_WRITE), self._secret(), db)

        assert _tokens_read == ["a-shared-secret-with-no-dots"]

    def test_an_unauthenticated_change_reads_no_token_and_names_nobody(
        self, db: Session, _tokens_read: list[str | None]
    ) -> None:
        assert consent_gate.consent_subject(self._request("POST", A_WRITE), None, db) is None
        assert _tokens_read == [None]


class TestTheLanguageOfTheQuestionComesFirst:
    """``/api/v1/users/me/preferences`` is exempt, and why that is not a hole.

    Every other exemption is here because closing it would make the gate
    impossible to *pass*. This one is here because closing it made the gate
    impossible to *read*.

    The client reports the browser's language for an account nobody ever set
    one on — a Google sign-up carries no language into the signup trigger, so
    the profile is created on the fallback. That report is a PATCH, so the
    gate refused it, and production showed the whole shape on 2026-09-22 at
    22:33 UTC: ``PATCH /users/me/preferences`` 403, then seven seconds later
    two ``POST /legal/acceptances`` 201. Somebody read the consent screen in a
    language they had not chosen, and the first-run setup went on offering it,
    because the profile still said so.

    What an un-consented caller gains is the ability to choose the language of
    the page that is asking them to consent. The route changes
    ``preferred_locale`` and nothing else — the test below is what keeps that
    true, since the exemption is only as narrow as the route is.
    """

    def test_a_person_who_has_signed_nothing_can_still_choose_the_language(self, student_client: TestClient) -> None:
        response = student_client.patch(PREFERENCES, json={"preferred_locale": "de"})

        assert response.status_code == 200, response.text
        assert response.json()["preferred_locale"] == "de"

    def test_the_browser_s_report_lands_too(self, student_client: TestClient) -> None:
        """The exact call production refused: a detected locale, not a choice."""
        response = student_client.patch(
            PREFERENCES,
            json={"preferred_locale": "de", "detected": True},
        )

        assert response.status_code == 200, response.text
        assert response.json()["locale_source"] == "detected"

    def test_the_exemption_is_no_wider_than_the_language(self) -> None:
        """The route's body model is the whole of what the exemption opens.

        If somebody adds a field to ``PreferredLocaleUpdate`` — a role, a
        flag, anything a person could want before accepting the terms — this
        fails, and the exemption has to be argued again rather than inherited.
        """
        from app.schemas.user import PreferredLocaleUpdate

        assert set(PreferredLocaleUpdate.model_fields) == {"preferred_locale", "detected"}

    def test_it_still_needs_a_session(self, anon_client: TestClient) -> None:
        """Exempt from the consent gate is not exempt from being signed in."""
        response = anon_client.patch(PREFERENCES, json={"preferred_locale": "de"})

        assert response.status_code in (401, 403)
        assert _code(response) != "legal.consent_required"
