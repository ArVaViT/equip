"""Regression tests for the CORS origin allow-list regex.

The Origin regex in ``app.core.config.Settings`` decides which browser
origins receive ``Access-Control-Allow-Origin`` echoed back with
``allow_credentials=True``. A too-loose pattern lets an attacker-owned
``vercel.app`` deployment make credentialed cross-origin requests
against the API — equivalent to a same-origin context for any
authenticated user.

The historical regex matched any ``equip-frontend-X.vercel.app``, so
an attacker could register ``equip-frontend-evil.vercel.app`` under
their own Vercel team and start scraping data from a logged-in
victim's session. The current pattern anchors the suffix to our team
slug (``vadyms-projects-dfb6f76f``) so only deployments under our
account match.

These tests are intentionally pure-regex (no Settings instantiation /
no env file loading) so they keep running under any test environment.
"""

from __future__ import annotations

import re

from app.core.config import Settings


def _regex() -> re.Pattern[str]:
    """Compile ``Settings.CORS_ORIGIN_REGEX`` against the model's default.

    Pydantic ``BaseSettings`` exposes field defaults via ``model_fields``,
    which means we can introspect the class-level default without
    constructing a ``Settings`` instance (which would fail in CI without
    a populated ``.env``).
    """
    default = Settings.model_fields["CORS_ORIGIN_REGEX"].default
    assert isinstance(default, str) and default, "CORS_ORIGIN_REGEX default must be a non-empty string"
    return re.compile(default)


# Origins that MUST be allowed -- losing any of these breaks a real
# user flow (production, custom domain, Vercel preview, local dev).
ALLOWED_ORIGINS = (
    "https://equipbible.com",
    "https://www.equipbible.com",
    "https://equip-frontend.vercel.app",
    "https://equip-frontend-vadyms-projects-dfb6f76f.vercel.app",
    "https://equip-frontend-abc123-vadyms-projects-dfb6f76f.vercel.app",
    "https://equip-frontend-git-main-vadyms-projects-dfb6f76f.vercel.app",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8000",
)

# Origins that MUST NOT be allowed. Each is a real-world bypass pattern:
#  * ``equip-frontend-evil.vercel.app`` -- attacker registers their own
#    vercel.app project. Blocked by the team-slug anchor.
#  * ``equip-frontend.vercel.app.evil.com`` -- subdomain takeover trick.
#    Blocked by the trailing ``$`` anchor.
#  * ``evilequipbible.com`` / ``equipbible.com.evil.com`` -- substring
#    confusion. Blocked by the leading ``^`` anchor and trailing ``$``.
#  * ``http://equipbible.com`` -- downgrade to HTTP. Blocked because the
#    apex pattern requires ``https://``.
#  * ``https://equip-frontend.vercel.app:1234`` -- port injection.
#    Blocked because the ``.vercel.app`` patterns have ``$`` immediately
#    after the host.
FORBIDDEN_ORIGINS = (
    "https://equip-frontend-evil.vercel.app",
    "https://equip-frontend-abc.vercel.app",
    "https://equip-frontend.vercel.app.evil.com",
    "https://evilequipbible.com",
    "https://equipbible.com.evil.com",
    "http://equipbible.com",
    "https://equip-frontend.vercel.app:1234",
    "https://equip-frontend-vadyms-projects-dfb6f76f.vercel.app.evil.com",
    "null",
    "",
)


def test_legitimate_origins_match() -> None:
    """Every origin we ship from must keep matching the regex.

    A regression that silently denies our own preview URLs would not
    fail any test that only inspects bad inputs; this is the inverse
    half of the contract.
    """
    pat = _regex()
    failures = [o for o in ALLOWED_ORIGINS if not pat.match(o)]
    assert not failures, f"these legitimate origins no longer match the CORS regex: {failures}"


def test_attacker_controlled_vercel_app_does_not_match() -> None:
    """The headline regression: ``equip-frontend-evil.vercel.app`` (an
    attacker's own Vercel project) must NOT match.

    Before the team-slug anchor, the regex was
    ``equip-frontend(?:-[\\w-]+)?\\.vercel\\.app`` which matched this
    pattern and let a malicious sub-team site receive credentialed
    responses from our API.
    """
    pat = _regex()
    assert pat.match("https://equip-frontend-evil.vercel.app") is None
    assert pat.match("https://equip-frontend-abc.vercel.app") is None


def test_forbidden_origins_do_not_match() -> None:
    """The full table of historically-tempting bypass patterns."""
    pat = _regex()
    leaks = [o for o in FORBIDDEN_ORIGINS if pat.match(o)]
    assert not leaks, f"these attacker-shaped origins still match the CORS regex: {leaks}"


def test_regex_requires_team_slug_for_preview_aliases() -> None:
    """Structural check: the preview-URL branch of the regex must
    literally contain the Vercel team slug, so a future edit that
    drops it gets caught even if no new origin is added to the
    forbidden list.
    """
    default = Settings.model_fields["CORS_ORIGIN_REGEX"].default
    assert "vadyms-projects-dfb6f76f" in default, (
        "Preview-URL branch of CORS_ORIGIN_REGEX must be anchored to the "
        "Vercel team slug; otherwise any equip-frontend-*.vercel.app "
        "project (including attacker-owned ones) will be allowed."
    )
