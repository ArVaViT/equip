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

WHY THERE IS NO MONEY BUDGET HERE
---------------------------------

This module counts seconds and nothing else, and that was examined on
2026-08-20 — after the pipeline's cost was measured for the first time
and half of it turned out to be invisible — with the question "should
there be a per-tick cap on calls, or a spend counter, or anything at
all that stops on money rather than on time?"

No. The answer is deliberate, and this is the record of it.

**A tick's call count is already bounded, by this clock.** The batch
loop in ``executor.py`` asks ``can_afford_one_call()`` before each
batch of ``DEFAULT_MAX_WORKERS``, so a 180-second tick cannot outrun
its allowance. A saturated pipeline was measured at about $0.29/hour —
roughly 1,200 fields — which is under half a cent per tick. Any cap
honest enough not to stall a large course would have to sit far above
that, and a cap that never fires is a comment.

**A runaway against a provider that is refusing is already bounded.**
``_OUTAGE_STREAK_LIMIT`` stops a pass after three consecutive
unanswered calls. It was added for exactly the event this question
comes from: the prepaid balance ran out and the pipeline spent hours
firing every call in a full-catalogue plan into a hard 429.

**The work is self-terminating.** ``source_hash`` short-circuits every
field already done, so a pass over finished content is free and the
queue empties once everything reaches the current generation. There is
no steady state in which this pipeline spends money.

**The prepaid balance is a real bound and ours would not be.** It is
enforced by Google, it cannot be bypassed by a bug in this file, and at
$0.29/hour a $50 monthly cap survives about a week of *continuous*
saturation — which is far more work than the catalogue contains. A
limit we wrote would be one more thing that can be wrong, and wrong in
the expensive direction: this pipeline has twice paid for a bound that
stopped legitimate work — 161 attempts on a course the invocation clock
kept beating, and 174 healthy rows promoted to ``failed_permanent`` by
an eight-minute outage. A stall is silent and a bill is not.

**And the counter already exists.** ``sum:equip.gemini.calls_total{*}``
over any window is cumulative calls; ``equip.gemini.tokens_*_total`` is
cumulative spend, and as of 2026-08-20 it finally includes the
reviewer, which was 52% of the bill and had no series at all. The
``[Equip] Gemini spend jumped`` monitor sits on top of it. A second
counter here would be a second number to reconcile with that one.

What was actually missing was never the authority to stop. It was
knowing. That is fixed in ``gemini.py``; revisit this only if a real
event gets past all four of the bounds above.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.core.config import call_reserve_seconds


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

    The reserve is derived, not guessed — see ``call_reserve_seconds``,
    which lives in ``core/config.py`` because the settings validator
    needs the same arithmetic to refuse a deployment whose budget is
    smaller than one call, and importing this module from there would
    close a cycle through ``app.services.translation.__init__``.
    """
    return TranslationBudget(
        seconds=seconds,
        reserve_seconds=call_reserve_seconds(gemini_timeout_seconds, gemini_max_retries),
    )


__all__ = ["NoBudget", "TranslationBudget", "worker_budget"]
