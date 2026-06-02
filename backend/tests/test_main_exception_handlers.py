"""Tests for the global exception handlers in ``app.main``.

The handlers wrap every authenticated route with a canonical envelope:

* ``IntegrityError`` (constraint violation) → 409 with the ``pgcode`` /
  ``orig.diag.constraint_name`` extracted for log search.
* ``SQLAlchemyError`` (lock timeout, connection drop, OperationalError)
  → 503 with ``exc_info=True``.
* generic ``Exception`` → 500.

They're un-tested in the happy-path suite because routes raise their
own ``equip_error`` first. We register a small set of temporary test
routes that raise each exception type, then hit them through the
existing TestClient.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import IntegrityError, OperationalError

if TYPE_CHECKING:
    from collections.abc import Generator

    from fastapi.testclient import TestClient


class _DiagBag:
    constraint_name = "uq_test_constraint"


class _OrigError(Exception):
    pgcode = "23505"
    diag = _DiagBag()


def _register_test_routes() -> list[str]:
    """Register three ``/__exc_test/...`` routes on the app that each
    raise one of the exception types the global handlers map. Returns
    the list of paths so the cleanup pass can remove them."""
    from app.main import app

    paths = [
        "/__exc_test/integrity",
        "/__exc_test/sqlalchemy",
        "/__exc_test/generic",
    ]

    async def raise_integrity() -> None:
        raise IntegrityError("statement", "params", _OrigError("dup"))

    async def raise_sqlalchemy() -> None:
        raise OperationalError("statement", None, Exception("lock timeout"))

    async def raise_generic() -> None:
        raise RuntimeError("totally unexpected")

    app.add_api_route(paths[0], raise_integrity, methods=["GET"])
    app.add_api_route(paths[1], raise_sqlalchemy, methods=["GET"])
    app.add_api_route(paths[2], raise_generic, methods=["GET"])
    return paths


def _unregister(paths: list[str]) -> None:
    from app.main import app

    app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) not in paths]


import pytest as _pytest  # noqa: E402 — needed at fixture decorator time


@_pytest.fixture
def exc_routes() -> Generator[None, None, None]:
    paths = _register_test_routes()
    yield
    _unregister(paths)


class TestIntegrityErrorHandler:
    def test_integrity_error_becomes_409(
        self,
        client: TestClient,
        exc_routes: None,
    ) -> None:
        """Pin the canonical envelope (409 + 'conflicts with current
        state') and exercise the ``pgcode`` / ``constraint_name``
        extraction off ``exc.orig``."""
        r = client.get("/__exc_test/integrity")
        assert r.status_code == 409
        assert "conflicts with current state" in r.json()["detail"]


class TestSqlAlchemyErrorHandler:
    def test_database_error_becomes_503(
        self,
        client: TestClient,
        exc_routes: None,
    ) -> None:
        """Lock timeout / OperationalError / connection drop → 503 with
        the canonical message. Don't leak the SQL or driver error."""
        r = client.get("/__exc_test/sqlalchemy")
        assert r.status_code == 503
        assert "temporarily unavailable" in r.json()["detail"]


class TestUnhandledExceptionHandler:
    def test_generic_exception_becomes_500(
        self,
        client: TestClient,
        exc_routes: None,
    ) -> None:
        """Catch-all — generic ``Exception`` maps to 500 with the
        generic message; no stack-trace leak."""
        r = client.get("/__exc_test/generic")
        assert r.status_code == 500
        assert r.json()["detail"] == "Internal server error"
