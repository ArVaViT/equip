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

        assert "SET TRANSACTION READ WRITE" in said, (
            "a connection that arrives read-only must not decide what this transaction may do"
        )
        assert "default_transaction_read_only" not in " ".join(said), (
            "that GUC is the mode the NEXT transaction starts in; setting it here "
            "changed nothing and production kept answering 503"
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
    def test_the_timeout_is_set_local(self) -> None:
        """A bare ``SET`` would leak onto whatever client gets this
        server connection next — which is how the poison being defended
        against got into the pool in the first place."""
        import inspect

        from app.core import database

        source = inspect.getsource(database)
        assert "SET LOCAL statement_timeout = '30s'" in source

    def test_the_write_mode_names_the_current_transaction(self) -> None:
        """``SET LOCAL default_transaction_read_only = off`` is what this
        said first, and it does nothing: that GUC is the mode the NEXT
        transaction begins in, and this one has already begun. The
        statement ran, production kept answering 503, and the deploy that
        supposedly carried the fix carried nothing."""
        import inspect

        from app.core import database

        source = inspect.getsource(database.open_the_transaction_the_way_we_mean_it)
        assert "SET TRANSACTION READ WRITE" in source
        assert "default_transaction_read_only = off" not in source

    def test_nothing_is_set_at_session_scope(self) -> None:
        """Fixing a leak by leaking in the other direction would be worse
        than the leak. ``SET TRANSACTION`` is transaction-scoped by
        definition; every other statement here must say ``LOCAL``."""
        import inspect

        from app.core import database

        source = inspect.getsource(database)
        bare = re.findall(r'exec_driver_sql\("SET (?!LOCAL|TRANSACTION)', source)
        assert not bare, f"a session-scoped SET would poison the pool for the next client: {bare}"
