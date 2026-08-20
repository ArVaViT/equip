"""A connection that arrives read-only must not make the request fail.

Supavisor hands out server connections from a shared pool, and some of
them arrive carrying ``default_transaction_read_only = on`` — set at
session scope by some other client and never reset. Measured on
production 2026-08-20: six fresh connections in a row read ``off``, one
taken minutes earlier read ``on`` with ``source = session``, while
``pg_is_in_recovery()`` was false. The database was writable; that one
connection was not.

From outside it looks like a request that fails for no reason and works
on retry. Two admin repairs came back "Database temporarily unavailable"
— the generic 503 every ``SQLAlchemyError`` becomes — while the same
writes through a direct connection went through. It is also where the
``cannot execute SELECT FOR UPDATE in a read-only transaction`` errors
in yesterday's worker logs came from, which read as database trouble and
were nothing of the kind.
"""

from __future__ import annotations

import re

import pytest


class TestEveryTransactionSaysWhatItNeeds:
    def test_a_transaction_asks_for_a_writable_connection(self) -> None:
        """The hook the engine installs, called with a connection that
        records what it was told."""
        from app.core.database import open_the_transaction_the_way_we_mean_it

        said: list[str] = []

        class _Recording:
            def exec_driver_sql(self, statement: str) -> None:
                said.append(statement)

        open_the_transaction_the_way_we_mean_it(_Recording())  # type: ignore[arg-type]

        assert "SET LOCAL default_transaction_read_only = off" in said, (
            "a connection that arrives read-only must not decide what this transaction may do"
        )

    def test_it_still_bounds_how_long_a_statement_may_run(self) -> None:
        """The reason the hook existed before this change, which must
        survive it: without the bound a pathological query holds a pooler
        slot for the two-minute cluster default."""
        from app.core.database import open_the_transaction_the_way_we_mean_it

        said: list[str] = []

        class _Recording:
            def exec_driver_sql(self, statement: str) -> None:
                said.append(statement)

        open_the_transaction_the_way_we_mean_it(_Recording())  # type: ignore[arg-type]

        assert "SET LOCAL statement_timeout = '30s'" in said


class TestTheStatementIsScopedToOneTransaction:
    @pytest.mark.parametrize(
        "statement",
        ["SET LOCAL statement_timeout = '30s'", "SET LOCAL default_transaction_read_only = off"],
    )
    def test_nothing_is_set_at_session_scope(self, statement: str) -> None:
        """Both statements must be ``SET LOCAL``.

        A bare ``SET`` would leak onto whatever client gets this server
        connection next — which is exactly how the poison being defended
        against got into the pool in the first place. Fixing a leak by
        leaking in the other direction would be worse than the leak.
        """
        import inspect

        from app.core import database

        source = inspect.getsource(database)
        assert statement in source
        bare = re.findall(r'exec_driver_sql\("SET (?!LOCAL)', source)
        assert not bare, f"a session-scoped SET would poison the pool for the next client: {bare}"
