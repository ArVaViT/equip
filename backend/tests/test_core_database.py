"""Unit tests for ``app.core.database`` error paths.

The conftest provides an in-memory SQLite engine for all the
integration tests; the production ``_get_engine`` / ``get_db`` Postgres
path therefore never runs. That leaves all the defensive 503 +
``DATABASE_URL`` + ``SQLAlchemyError`` paths uncovered.

This file exercises the ``get_db`` error branches directly by
monkeypatching the module's globals — that's far cleaner than trying
to reload the module with a synthetic env, and the paths are pure
control flow so the test fidelity matches production.
"""

from __future__ import annotations

import contextlib
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError

from app.core import database as core_db


def _drain(gen) -> object:
    """Run the FastAPI dependency generator until completion.

    ``get_db`` is a generator that ``yield``s the session; FastAPI
    drains it after the request. In tests we do the same so the
    ``finally`` block (``db.close()``) runs.
    """
    out = next(gen)
    with contextlib.suppress(StopIteration):
        next(gen)
    return out


class TestGetDbEngineErrors:
    def test_engine_init_failure_returns_503(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When ``_get_engine`` raises (bad ``DATABASE_URL``, missing
        ``psycopg2``, etc.) the dependency MUST return a clean 503 with
        a generic message — not leak the underlying error or 500."""

        def fail() -> object:
            raise RuntimeError("DATABASE_URL is empty or not set")

        monkeypatch.setattr(core_db, "_get_engine", fail)
        # Also clear _SessionLocal so we don't accidentally take the
        # other 503 branch.
        monkeypatch.setattr(core_db, "_SessionLocal", None)

        with pytest.raises(HTTPException) as exc:
            next(core_db.get_db())
        assert exc.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert exc.value.detail == "Database connection error"

    def test_missing_session_factory_returns_503(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If ``_get_engine`` somehow succeeds without setting
        ``_SessionLocal`` (refactor bug, partial init), the dependency
        still returns 503 instead of crashing with ``NoneType is not
        callable``."""

        monkeypatch.setattr(core_db, "_get_engine", lambda: MagicMock())
        monkeypatch.setattr(core_db, "_SessionLocal", None)

        with pytest.raises(HTTPException) as exc:
            next(core_db.get_db())
        assert exc.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert "session factory" in exc.value.detail.lower()


class TestGetDbErrorHandling:
    """The yield-then-cleanup half of ``get_db``. SQLAlchemy errors
    must rollback + propagate; other exceptions must also rollback +
    propagate; the session is always closed in ``finally``.
    """

    def test_sqlalchemy_error_rolls_back_and_reraises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_session = MagicMock()
        session_factory = MagicMock(return_value=fake_session)

        monkeypatch.setattr(core_db, "_get_engine", lambda: MagicMock())
        monkeypatch.setattr(core_db, "_SessionLocal", session_factory)

        gen = core_db.get_db()
        db = next(gen)  # enter the yield point
        assert db is fake_session

        # Now drive the generator into the SQLAlchemyError branch by
        # ``throw``-ing one in.
        with pytest.raises(SQLAlchemyError):
            gen.throw(SQLAlchemyError("query exploded"))
        fake_session.rollback.assert_called_once()
        fake_session.close.assert_called_once()

    def test_generic_exception_also_rolls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-SQLAlchemy exceptions raised inside a request still need
        the same rollback + close — a leaked transaction would pin the
        Postgres connection. Pin the broad except path."""
        fake_session = MagicMock()
        session_factory = MagicMock(return_value=fake_session)

        monkeypatch.setattr(core_db, "_get_engine", lambda: MagicMock())
        monkeypatch.setattr(core_db, "_SessionLocal", session_factory)

        gen = core_db.get_db()
        next(gen)

        with pytest.raises(ValueError):
            gen.throw(ValueError("business-logic error"))
        fake_session.rollback.assert_called_once()
        fake_session.close.assert_called_once()

    def test_clean_exit_closes_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The happy path: yield once, generator exhausts normally,
        ``finally`` closes the session. No rollback fires."""
        fake_session = MagicMock()
        session_factory = MagicMock(return_value=fake_session)

        monkeypatch.setattr(core_db, "_get_engine", lambda: MagicMock())
        monkeypatch.setattr(core_db, "_SessionLocal", session_factory)

        gen = core_db.get_db()
        next(gen)
        with pytest.raises(StopIteration):
            next(gen)  # exhaust → enters finally
        fake_session.close.assert_called_once()
        fake_session.rollback.assert_not_called()
