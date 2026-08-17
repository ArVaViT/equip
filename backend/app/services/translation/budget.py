"""How long this pass is allowed to run before it has to hand back.

The worker runs inside one Vercel function invocation, and that
invocation is killed at ``maxDuration`` (300 s, see
``backend/vercel.json``) with no warning and no chance to record
anything. Until this module existed, one job meant one whole course:
the tick claimed the job, started walking the tree, and if the walk
took longer than the function lived, the process simply vanished.

What that looked like in production, 8-10 August 2026: the row stayed
``processing`` (nobody was alive to mark it otherwise), the stale
sweep re-claimed it fifteen minutes later, the same walk started
again, and the same kill arrived. 161 attempts. Every tick paid for
real Gemini calls and every tick died before it could say so. The
counter kept climbing because ``claim_next_job`` increments on claim,
so the job eventually reached ``failed_permanent`` — a course that
was translating fine, one field at a time, declared permanently
broken because the clock kept beating it.

The fix is not a bigger timeout. It is knowing what the deadline is
and stopping *before* it:

* Every provider call is preceded by ``budget.can_afford_one_call()``.
  The reserve is the worst case for a single call — ``GEMINI_TIMEOUT``
  on each of (retries + 1) attempts plus backoff — so the call we agree
  to start can always finish inside the invocation.
* When the budget runs out mid-course, the pass returns
  ``incomplete=True``. Everything already translated is committed; the
  job goes back to ``queued`` and the next tick continues from there,
  free of charge, because ``source_hash`` short-circuits every field
  already done.
* A tick that made progress does not count as an attempt. That is the
  distinction the old code could not draw: a big course and a broken
  course both looked like "the job came back unfinished". Only the one
  that came back with nothing to show for it is failing.

So a course too large for one invocation is no longer a course that
cannot be translated. It is a course that takes several ticks, at one
tick a minute.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class TranslationBudget:
    """Wall-clock allowance for one translation pass.

    ``seconds`` is the allowance itself. ``reserve_seconds`` is what we
    keep back for the single call we might still start — a call is only
    begun when the whole of its worst case fits in what remains, so the
    invocation is never killed with a request in flight.

    Not thread-safe and deliberately not: one pass, one thread, one
    monotonic clock. ``time.monotonic`` (not ``time.time``) because an
    NTP correction mid-pass must not hand us a deadline in the past.
    """

    seconds: float
    reserve_seconds: float = 0.0
    _started_at: float = field(default_factory=time.monotonic, init=False)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._started_at

    @property
    def remaining(self) -> float:
        return self.seconds - self.elapsed

    def expired(self) -> bool:
        """True once the allowance is spent — checked between entities."""
        return self.remaining <= 0

    def can_afford_one_call(self) -> bool:
        """True while there is room for another provider call *and* its
        worst case.

        This is the check that actually protects the invocation. A bare
        ``expired()`` would happily start a 90-second call at second 179
        of a 180-second budget.
        """
        return self.remaining > self.reserve_seconds


class NoBudget(TranslationBudget):
    """The unlimited case, as an object rather than a ``None`` check.

    Every synchronous caller — a teacher editing one block, a test, an
    admin retry — has no deadline to respect, and threading ``budget is
    None`` through four layers would put that special case in every
    signature. This subclass answers "yes" to everything instead.
    """

    def __init__(self) -> None:
        super().__init__(seconds=0.0)

    @property
    def remaining(self) -> float:
        return float("inf")

    def expired(self) -> bool:
        return False

    def can_afford_one_call(self) -> bool:
        return True


def worker_budget(
    *,
    seconds: float,
    gemini_timeout_seconds: float,
    gemini_max_retries: int = 2,
) -> TranslationBudget:
    """Build the budget for one worker tick.

    The reserve is derived, not guessed: a provider call can take its
    read timeout on each of ``max_retries + 1`` attempts, plus the
    backoff between them, and we add a couple of seconds for the commit
    and the promotion check that follow the last call.
    """
    attempts = gemini_max_retries + 1
    backoff = float(sum(2**n for n in range(gemini_max_retries)))
    return TranslationBudget(
        seconds=seconds,
        reserve_seconds=gemini_timeout_seconds * attempts + backoff + 2.0,
    )


__all__ = ["NoBudget", "TranslationBudget", "worker_budget"]
