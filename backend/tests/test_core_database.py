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


class TestServerlessPoolerGuard:
    def test_warns_on_direct_5432_url_under_serverless(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """On serverless, a direct :5432 DATABASE_URL would exhaust
        connections under load (the pool is tiny by design). _get_engine must WARN so the
        misconfiguration surfaces at boot, not during an incident."""
        import logging

        monkeypatch.setattr(core_db, "_engine", None)
        monkeypatch.setattr(core_db, "_SessionLocal", None)
        monkeypatch.setattr(core_db, "IS_SERVERLESS", True)
        monkeypatch.setattr(
            core_db.settings, "DATABASE_URL", "postgresql://u:p@db.abc.supabase.co:5432/postgres", raising=False
        )
        with caplog.at_level(logging.WARNING):
            core_db._get_engine()
        monkeypatch.setattr(core_db, "_engine", None)  # don't cache the throwaway engine
        assert any("5432" in r.getMessage() and "POOLER" in r.getMessage() for r in caplog.records)

    def test_quiet_on_transaction_pooler_6543(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        monkeypatch.setattr(core_db, "_engine", None)
        monkeypatch.setattr(core_db, "_SessionLocal", None)
        monkeypatch.setattr(core_db, "IS_SERVERLESS", True)
        monkeypatch.setattr(
            core_db.settings,
            "DATABASE_URL",
            "postgresql://u:p@aws-0-us.pooler.supabase.com:6543/postgres",
            raising=False,
        )
        with caplog.at_level(logging.WARNING):
            core_db._get_engine()
        monkeypatch.setattr(core_db, "_engine", None)
        assert not any("POOLER" in r.getMessage() for r in caplog.records)


class TestConcurrentColdStart:
    """Ten requests arrive at an uninitialised module at the same time.

    FastAPI runs a sync dependency such as ``get_db`` in a threadpool, so a
    cold serverless instance handed a burst of calls really does start
    several threads through ``_get_engine`` together. Opening one course
    page fires about ten.

    Production showed what that cost on 2026-09-20 at 14:36 UTC: nine of
    those calls returned 200 and ``GET /api/v1/calendar/events`` returned
    503. One thread had published ``_engine`` and had not yet built
    ``_SessionLocal``; a second took the early return, found the factory
    still ``None`` and raised. Nothing was logged, because that branch
    raises an ``HTTPException`` without a log line — an error the user saw
    and the logs did not contain.

    The fix publishes the engine last, under a lock. The first test below
    fails against the ordering that preceded it: a fake engine that is slow
    to answer ``.dialect`` holds open the exact window between the two
    globals, and the nine later arrivals land in it.
    """

    def test_no_thread_sees_an_engine_without_its_session_factory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import threading
        import time

        monkeypatch.setattr(core_db, "_engine", None)
        monkeypatch.setattr(core_db, "_SessionLocal", None)

        class SlowToDescribeItself:
            """An engine that takes a moment to answer ``.dialect``.

            That single attribute is read between building the engine and
            building the session factory, so making it slow holds open
            exactly the window the outage happened in, and only that one.
            A fixed module keeps the window inside the lock and behind an
            unpublished global; a broken one lets nine threads through it.
            """

            def __init__(self) -> None:
                self._dialect = MagicMock()
                self._dialect.name = "sqlite"

            @property
            def dialect(self) -> MagicMock:
                time.sleep(0.1)
                return self._dialect

        monkeypatch.setattr(core_db, "create_engine", lambda url, **kwargs: SlowToDescribeItself())

        observed: list[object] = []
        record = threading.Lock()

        def arrive() -> None:
            try:
                core_db._get_engine()
                # What ``get_db`` does next, and the exact read that failed.
                with record:
                    observed.append(core_db._SessionLocal)
            except Exception as exc:
                with record:
                    observed.append(exc)

        # One request lands first and the rest arrive while it is still
        # setting up, which is what a cold instance with a course page
        # pointed at it looks like.
        pioneer = threading.Thread(target=arrive)
        pioneer.start()
        time.sleep(0.02)
        rest = [threading.Thread(target=arrive) for _ in range(9)]
        for thread in rest:
            thread.start()
        for thread in [pioneer, *rest]:
            thread.join(timeout=10)

        assert len(observed) == 10
        assert [o for o in observed if isinstance(o, Exception)] == []
        assert all(o is not None for o in observed), (
            "a thread was handed an engine while the session factory was still None - this is the 503 from 2026-09-20"
        )

    def test_the_engine_is_built_once_however_many_arrive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The lock must not turn into ten engines, each with its own pool."""
        import threading

        monkeypatch.setattr(core_db, "_engine", None)
        monkeypatch.setattr(core_db, "_SessionLocal", None)

        calls: list[str] = []
        lock = threading.Lock()

        def counting_create_engine(url: str, **kwargs: object) -> MagicMock:
            with lock:
                calls.append(url)
            engine = MagicMock()
            engine.dialect.name = "sqlite"
            return engine

        monkeypatch.setattr(core_db, "create_engine", counting_create_engine)

        threads = [threading.Thread(target=core_db._get_engine) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        assert len(calls) == 1
