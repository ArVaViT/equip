"""The consent gate, enforced where it cannot be skipped.

Until now the gate lived entirely in ``FirstRunFlow.tsx``: a full-screen
dialog that covers the app until the person accepts. It is a good dialog.
It is also the only thing standing between an unaccepted account and the
whole API — and it is JavaScript running on the reader's own machine. A
second tab pointed at ``api.equipbible.com``, a stale bundle, a script
somebody wrote against the API, or simply the dialog failing to mount, and
the platform hands over every write it has while the consent table says
nothing was ever agreed to.

That gap is the difference between a consent record and consent. The record
answers "did this person agree, and to what"; enforcement answers "and were
they allowed to act before they did". Only the server can answer the second
one, because only the server sees every request.

What this refuses, and what it does not
---------------------------------------

**Refused:** ``POST`` / ``PUT`` / ``PATCH`` / ``DELETE`` from a signed-in
person who still owes an acceptance, anywhere under ``/api/v1``.

**Allowed:** every read. Somebody who has not yet accepted can still see
their dashboard behind the dialog, and — more to the point — can still read
the documents they are being asked to accept. A gate that blocks its own
escape hatch is a wall; the frontend learned that the hard way (see the
``exempt`` constant in ``FirstRunFlow.tsx``) and the server must not
reintroduce it from the other side.

**Not their business:** anonymous callers. The Datadog Synthetics browser
tests and the uptime checks carry no session, and the internal cron workers
authenticate with a shared secret rather than a user. None of them has a
person behind it who could accept anything, and none of them reaches an
authenticated surface anyway — whatever gate already guards a route still
guards it. This dependency simply has nothing to say about a request with
no user, and says nothing.

Why a router dependency and not middleware
------------------------------------------

Middleware would have to decode the bearer token and load the profile a
second time, duplicating ``get_current_user`` and drifting from it. A
dependency declared on ``include_router`` runs before the route's own
dependencies and is overridable in tests the same way every other
dependency here is.

The identity itself is resolved by ``consent_subject``, which reads the
token only once it knows this gate has an opinion about the request — not
by depending on ``get_optional_user``, which would resolve for every read
and every exempt path as well. See that function for what the shortcut
cost in practice.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from fastapi import Depends, Request, status
from fastapi.security import HTTPAuthorizationCredentials  # noqa: TC002 — used by FastAPI Depends at runtime
from sqlalchemy import select

from app.api.dependencies import optional_security, resolve_optional_user
from app.core.database import get_db
from app.core.errors import ErrorCode, equip_error
from app.legal import registry as legal_registry
from app.models.legal_acceptance import LegalAcceptance

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.user import User

#: The methods that change something. ``HEAD`` and ``OPTIONS`` are reads by
#: definition; ``OPTIONS`` is also the CORS preflight, which carries no
#: credentials at all and must never be answered with a 403.
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

#: Paths this gate must never close, matched as prefixes of the full path.
#:
#: Each one is here because closing it would make the gate impossible to
#: pass, not because the route is unimportant:
#:
#: ``/api/v1/legal/``
#:     Reading a document, recording an acceptance, and closing a notice.
#:     This is the way out; it is the one thing that cannot be gated.
#: ``/api/v1/auth/``
#:     The identity probe the client makes on every page load, and signing
#:     out. Somebody who does not want to accept must be able to leave.
#: ``/api/v1/health``
#:     Liveness. No user, no consent, no opinion.
#: ``/api/v1/internal/``
#:     The cron workers, authenticated by shared secret. Anonymous to this
#:     gate already; listed so a future worker route that does carry a user
#:     does not silently start failing at 03:00.
#: ``/api/v1/users/me/preferences``
#:     The language the documents are shown in. This one is here for a
#:     different reason than the others: closing it does not make the gate
#:     impossible to pass, it makes it impossible to read.
#:
#:     The client reports the browser's language for an account nobody ever
#:     set one on - a Google sign-up carries no language into the signup
#:     trigger, so the profile is created on the fallback. That report is a
#:     PATCH, so the gate refused it, and production showed the whole shape
#:     on 2026-09-22 at 22:33 UTC: PATCH /users/me/preferences 403, then
#:     seven seconds later two POST /legal/acceptances 201. The person read
#:     the consent screen in a language they had not chosen, and the
#:     first-run setup went on offering it, because the profile still said
#:     so. It self-heals on the next load, which is one load too late.
#:
#:     Asking somebody to accept legal documents in a language they did not
#:     choose is worse than letting them set that language first. The route
#:     changes ``preferred_locale`` and nothing else - see
#:     ``update_my_preferences``, whose body model is ``PreferredLocaleUpdate``
#:     - so what an un-consented caller gains here is the ability to pick
#:     the language of the page that is asking them to consent.
EXEMPT_PREFIXES: tuple[str, ...] = (
    "/api/v1/legal/",
    "/api/v1/auth/",
    "/api/v1/health",
    "/api/v1/internal/",
    "/api/v1/users/me/preferences",
)

#: The registry's role-aware answer, when the registry has one.
#:
#: ``outstanding_for(role, accepted)`` arrives with the document registry
#: (PR #1291): it knows that a teacher signs the teacher terms and a student
#: does not, and that a version published as a correction does not bring
#: anybody back to the gate. This module treats the registry as data and
#: asks it the question rather than re-deriving the answer, so a new
#: document or a new role changes one table and nothing here.
#:
#: Until that lands, ``_outstanding_from_current_versions`` below answers the
#: same question from what today's registry does expose — one current version
#: per signable document, required of everybody. Same shape, coarser rule,
#: and coarser in the safe direction: it can ask somebody for a document they
#: would not have been asked for, never the reverse.
_RoleAwareOutstanding = Callable[[str, set[tuple[str, str]]], Sequence[Any]]
_registry_outstanding: _RoleAwareOutstanding | None = getattr(legal_registry, "outstanding_for", None)


def _outstanding_from_current_versions(role: str, accepted: set[tuple[str, str]]) -> tuple[str, ...]:
    """Which signable documents this person has not accepted at its current version."""
    required = set(legal_registry.required_slugs())
    return tuple(
        slug
        for slug, version in sorted(legal_registry.LEGAL_DOCUMENTS.items())
        if slug in required and (slug, version) not in accepted
    )


def outstanding_slugs(role: str, accepted: set[tuple[str, str]]) -> tuple[str, ...]:
    """What this person still owes, as slugs, newest rule first."""
    if _registry_outstanding is not None:
        return tuple(str(spec.slug) for spec in _registry_outstanding(role, accepted))
    return _outstanding_from_current_versions(role, accepted)


def user_owes_consent(db: Session, user: User) -> tuple[str, ...]:
    """The documents ``user`` must accept before they may change anything.

    One indexed read of ``legal_acceptances`` on ``user_id`` — the same
    index ``GET /legal/acceptances/me`` uses — per mutating request. Reads
    never reach here.
    """
    accepted = {
        (row.document_slug, row.version)
        for row in db.scalars(select(LegalAcceptance).where(LegalAcceptance.user_id == user.id)).all()
    }
    return outstanding_slugs(user.role, accepted)


def consent_subject(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security),
    db: Session = Depends(get_db),
) -> User | None:
    """Who is making this change, when the change is one this gate judges.

    ``None`` for everything the gate ignores — and the point is that it
    answers ``None`` *without reading the token*. A read, or a path on
    ``EXEMPT_PREFIXES``, is decided from the request line alone.

    That matters because this gate is declared on ``include_router`` and so
    runs for every request under ``/api/v1``. Depending on
    ``get_optional_user`` directly decoded the bearer header of requests the
    gate had already decided it had nothing to say about — including
    ``/api/v1/internal/``, where Vercel Cron authenticates the worker by
    sending its shared secret as ``Authorization: Bearer <secret>``. That
    secret is not a JWT, so every tick of the minutely cron logged
    ``JWT decode failed: Not enough segments``: 1,747 warnings across two
    days in September 2026, roughly 90% of the backend's whole warning
    volume, every one of them for a request this module's own docstring
    says it has no opinion about.

    The exemption was always written down — ``/api/v1/internal/`` has been
    in ``EXEMPT_PREFIXES`` from the start. It just could not take effect,
    because FastAPI resolves a declared dependency before the body that
    consults the exemption list ever runs.
    """
    if request.method not in MUTATING_METHODS:
        return None
    if any(request.url.path.startswith(prefix) for prefix in EXEMPT_PREFIXES):
        return None
    return resolve_optional_user(credentials.credentials if credentials is not None else None, db)


def require_legal_consent(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(consent_subject),
) -> None:
    """Refuse a change from somebody who has not accepted the current documents.

    Raises ``legal.consent_required`` (403) carrying the outstanding slugs,
    so a client that meets it can open the gate on exactly those documents
    instead of guessing — and so a script that meets it is told what it is
    missing rather than a bare "forbidden".
    """
    if request.method not in MUTATING_METHODS:
        return
    if current_user is None:
        return
    path = request.url.path
    if any(path.startswith(prefix) for prefix in EXEMPT_PREFIXES):
        return

    owed = user_owes_consent(db, current_user)
    if not owed:
        return

    raise equip_error(
        ErrorCode.LEGAL_CONSENT_REQUIRED,
        status_code=status.HTTP_403_FORBIDDEN,
        message="Accept the current terms and privacy policy before making changes",
        context={"outstanding": list(owed)},
    )


__all__ = [
    "EXEMPT_PREFIXES",
    "MUTATING_METHODS",
    "consent_subject",
    "outstanding_slugs",
    "require_legal_consent",
    "user_owes_consent",
]
