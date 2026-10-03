"""A named lease holds for the whole of a sweep that commits as it goes.

The idle pool sweep used a transaction-scoped advisory lock, and committed
after every question — which released the lock at the first commit, so an
overlapping tick could sweep the same questions. A lease is a row instead.
The same semantics were checked against Postgres 17 on 2026-10-01; here they
run on the SQLite test database, whose upsert has the same syntax.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.services.worker_lease import claim, release

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def test_one_holder_at_a_time(db: Session) -> None:
    first = claim(db, "sweep", now=T0)
    assert first is not None
    assert claim(db, "sweep", now=T0 + timedelta(seconds=10)) is None


def test_a_commit_does_not_give_it_away(db: Session) -> None:
    """The bug a transaction lock had: the sweep's own commit released it."""
    assert claim(db, "sweep", now=T0) is not None
    db.commit()
    assert claim(db, "sweep", now=T0 + timedelta(seconds=30)) is None


def test_a_holder_that_died_lets_go_when_it_expires(db: Session) -> None:
    assert claim(db, "sweep", now=T0) is not None
    assert claim(db, "sweep", now=T0 + timedelta(seconds=331)) is not None


def test_only_its_holder_can_give_it_back(db: Session) -> None:
    stale = claim(db, "sweep", now=T0)
    assert stale is not None
    current = claim(db, "sweep", now=T0 + timedelta(seconds=400))
    assert current is not None
    release(db, "sweep", stale)  # the old holder, finishing late
    assert claim(db, "sweep", now=T0 + timedelta(seconds=401)) is None
    release(db, "sweep", current)
    assert claim(db, "sweep", now=T0 + timedelta(seconds=402)) is not None


def test_leases_are_independent(db: Session) -> None:
    assert claim(db, "sweep", now=T0) is not None
    assert claim(db, "prune", now=T0) is not None
