"""Survive the network going away mid-run.

These backfills run for hours on a laptop behind an always-on VPN. On
2026-08-16 the course pass died four hours in, and not from anything to
do with translation:

    could not translate host name "aws-0-us-west-2.pooler.supabase.com"
    to address: nodename nor servname provided, or not known

The name stopped resolving. The script did retry — 45s, 60s, 75s — and
then gave up, because the whole retry budget was under four minutes and
the outage was longer. Everything after that course was simply not
translated, and nobody would have known until somebody opened the site
in German.

Two things were wrong, and both are fixed here.

*The budget was too short.* A VPN reconnect, a laptop waking from
sleep, or a pooler failover is minutes, not seconds. Waiting a quarter
of an hour costs nothing on a run that takes hours; giving up costs the
whole remainder of the run.

*The pool kept the corpse.* SQLAlchemy holds connections open in a
pool. When the network drops, those sockets are dead but still checked
in, so the next attempt is handed one and fails again for a reason that
has nothing to do with the current state of the network. Disposing the
engine between attempts is what makes the retry mean anything.

What is deliberately *not* retried: anything that is not a database
transport error. A constraint violation or a bad query is not going to
resolve itself in ninety seconds, and looping on one would hide it.
"""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING

from sqlalchemy.exc import DBAPIError

from app.core.database import _get_engine

if TYPE_CHECKING:
    import logging
    from collections.abc import Callable

    from sqlalchemy.orm import Session

# Roughly eighteen minutes in total, backing off to two-minute checks:
# long enough to sit through a VPN reconnect or a pooler failover, short
# enough that a database which is genuinely gone still ends the run
# rather than spinning overnight.
ATTEMPTS = 12
FIRST_WAIT_SECONDS = 10.0
MAX_WAIT_SECONDS = 120.0


def _wait_for(attempt: int) -> float:
    return min(FIRST_WAIT_SECONDS * (2**attempt), MAX_WAIT_SECONDS)


def run_with_reconnect[T](
    work: Callable[[], T],
    *,
    label: str,
    logger: logging.Logger,
    db: Session,
) -> T:
    """Run ``work``, waiting out a database that is temporarily unreachable.

    Raises the last error if it never comes back, so a real outage still
    ends the run instead of looping silently.
    """
    for attempt in range(ATTEMPTS):
        try:
            return work()
        except DBAPIError as exc:
            # Rolling back over a dead socket fails too; the dispose
            # below is what actually clears it.
            with contextlib.suppress(DBAPIError):
                db.rollback()
            # Drop every pooled connection: they were opened before the
            # network went away and will fail again on checkout.
            _get_engine().dispose()
            if attempt == ATTEMPTS - 1:
                logger.error("database still unreachable on %s after %d attempts", label, ATTEMPTS)
                raise
            wait = _wait_for(attempt)
            logger.warning(
                "database unreachable on %s (%s); reconnecting in %.0fs (attempt %d of %d)",
                label,
                exc.__class__.__name__,
                wait,
                attempt + 1,
                ATTEMPTS,
            )
            time.sleep(wait)
    raise AssertionError("unreachable")
