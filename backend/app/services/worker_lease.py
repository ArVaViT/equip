"""Named leases: one holder at a time for background work that commits as it goes.

The idle translation tick sweeps the Daily Challenge pool, and ticks overlap
(a cron every minute, a function allowed five). A transaction-scoped advisory
lock does not hold across the sweep, because the sweep commits after every
question and the first commit releases it; a session-scoped one is unsafe
behind Supabase's transaction pooler, which hands the server connection — and
its locks — to the next client. A lease is a row instead:

* :func:`claim` is one upsert that succeeds only when the row is absent or
  expired, committed at once so an overlapping tick sees it;
* :func:`release` deletes it, only if this holder still has it;
* a holder that dies leaves a row that expires on its own, so nothing wedges.

Both work on SQLite (the test database), whose upsert has the same syntax.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

#: Longer than any one invocation can live (``maxDuration: 300`` in
#: ``backend/vercel.json``), so a live holder never loses its lease, and short
#: enough that a crashed one blocks the work for a few minutes at most.
DEFAULT_TTL = timedelta(seconds=330)

_CLAIM = text(
    "INSERT INTO worker_leases (name, holder, expires_at) VALUES (:name, :holder, :expires_at) "
    "ON CONFLICT (name) DO UPDATE SET holder = excluded.holder, expires_at = excluded.expires_at "
    "WHERE worker_leases.expires_at < :now "
    "RETURNING holder"
)
_RELEASE = text("DELETE FROM worker_leases WHERE name = :name AND holder = :holder")


def claim(db: Session, name: str, *, ttl: timedelta = DEFAULT_TTL, now: datetime | None = None) -> uuid.UUID | None:
    """Take the lease ``name``; the holder id to release it with, or ``None`` if someone has it.

    Commits: the claim must be visible to an overlapping tick at once.
    """
    moment = now or datetime.now(UTC)
    holder = uuid.uuid4()
    won = db.execute(
        _CLAIM,
        # Strings, not a UUID: Postgres reads an untyped literal as the
        # column's type, and SQLite has no UUID type to bind to.
        # Times as ISO strings for the same reason, and one format on both
        # sides, so SQLite's text comparison orders them as Postgres does.
        {"name": name, "holder": str(holder), "expires_at": (moment + ttl).isoformat(), "now": moment.isoformat()},
    ).scalar()
    db.commit()
    return holder if won is not None and str(won) == str(holder) else None


def release(db: Session, name: str, holder: uuid.UUID) -> None:
    """Give the lease back, if this holder still has it. Commits."""
    db.execute(_RELEASE, {"name": name, "holder": str(holder)})
    db.commit()
