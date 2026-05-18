"""Regression tests for per-endpoint rate-limit coverage.

The in-memory ``RateLimitMiddleware`` carries a small ``ENDPOINT_LIMITS``
table that overrides the global 100/60s default for sensitive routes.
These tests assert that the table stays populated for the
high-abuse-surface endpoints we care about and that ``_resolve_limit``
actually picks the override (not the global default) when a request
to one of them lands.

Why this matters: ``ENDPOINT_LIMITS`` is a plain dict, so a future
edit could silently drop an entry without breaking anything else.
Catching a regression at the dict level is cheap; catching it after
a credential-stuffing burst against ``/auth/me`` or a brute-force
enumeration of ``/certificates/verify/`` is not.

These tests inspect the middleware directly and do not depend on the
``autouse=True`` rate-limiter reset fixture, so they are immune to
the bucket bleed that would otherwise make ``429`` assertions flaky.
"""

from __future__ import annotations

import pytest

from app.middleware.rate_limit import ENDPOINT_LIMITS, RateLimitMiddleware

# Each entry is (route_path, expected_max_calls, expected_window_seconds).
# Pick representative sub-paths under each prefix so the ``startswith``
# resolution is exercised the way real traffic hits it.
EXPECTED_OVERRIDES: tuple[tuple[str, int, int], ...] = (
    ("/api/v1/auth/me", 10, 60),
    ("/api/v1/certificates/verify/abc-123", 30, 60),
    ("/api/v1/verse-of-the-day", 60, 60),
)


@pytest.mark.parametrize("path, expected_calls, expected_window", EXPECTED_OVERRIDES)
def test_endpoint_resolves_to_per_route_override(path: str, expected_calls: int, expected_window: int) -> None:
    """Each sensitive endpoint must resolve to its tighter override,
    not the global 100/60s default.
    """
    mw = RateLimitMiddleware(app=None, calls=100, window=60)
    matched_prefix, calls, window = mw._resolve_limit(path)
    assert matched_prefix is not None, f"{path} should have matched an override prefix"
    assert (calls, window) == (expected_calls, expected_window), (
        f"{path} resolved to ({calls}, {window}); expected ({expected_calls}, {expected_window}). "
        "Did someone drop the per-route override from ENDPOINT_LIMITS?"
    )


def test_default_route_keeps_global_limit() -> None:
    """A route with no matching prefix must fall through to the global
    default. This guards against an accidental wildcard entry being
    added to ENDPOINT_LIMITS that would tighten everything.
    """
    mw = RateLimitMiddleware(app=None, calls=100, window=60)
    matched_prefix, calls, window = mw._resolve_limit("/api/v1/courses")
    assert matched_prefix is None, "unmatched routes must signal no override"
    assert (calls, window) == (100, 60)


def test_verify_paths_share_one_bucket_per_ip() -> None:
    """Two different ``/certificates/verify/<X>`` requests from the same
    IP must resolve to the SAME bucket-key prefix so an attacker who
    varies the cert number can't get a fresh 30/min budget per guess.
    Regression for the pre-fix bug where the bucket key included the
    full path (cert-number tail), making the rate limit effectively
    per-cert instead of per-IP.
    """
    mw = RateLimitMiddleware(app=None, calls=100, window=60)
    prefix_a, _, _ = mw._resolve_limit("/api/v1/certificates/verify/aaa-111")
    prefix_b, _, _ = mw._resolve_limit("/api/v1/certificates/verify/bbb-222")
    assert prefix_a == prefix_b == "/api/v1/certificates/verify/"


def test_sensitive_prefixes_are_all_present() -> None:
    """Belt-and-suspenders: assert by literal prefix that the table
    still contains every override we depend on. Catches the case where
    someone renames the key (e.g. trailing slash drift) and breaks the
    ``startswith`` match without the parametrized test above noticing.
    """
    required_prefixes = (
        "/api/v1/auth/",
        "/api/v1/certificates/verify/",
        "/api/v1/verse-of-the-day",
    )
    missing = [p for p in required_prefixes if p not in ENDPOINT_LIMITS]
    assert not missing, f"ENDPOINT_LIMITS lost coverage for: {missing}"


def test_overrides_are_tighter_than_global_default() -> None:
    """An override that's looser than the global default is almost
    certainly a typo and would silently make a sensitive endpoint
    cheaper to abuse, not more expensive.
    """
    global_calls, global_window = 100, 60
    for prefix, (calls, window) in ENDPOINT_LIMITS.items():
        # Per-window rate: calls/window. Compare to the global.
        rate = calls / window
        global_rate = global_calls / global_window
        assert rate <= global_rate, (
            f"Override for {prefix!r} allows {rate:.2f} req/s, which is looser "
            f"than the global {global_rate:.2f} req/s. Either tighten it or "
            f"remove the entry."
        )
