"""The half of the pipeline that nobody has to remember.

Everything else here is reactive: a teacher saves, a hook fires, a job
is queued. That is the right shape for latency — an edit should be on
its way to the other languages before the teacher's hand leaves the
mouse — and it is the wrong shape for certainty, because it only ever
notices what somebody just touched.

Two things it cannot see, and both arrive with scale:

* **A new language.** Switch on a fifth locale and every course that
  exists is instantly incomplete in it. No save happened, so no hook
  fires, and the documented remedy was a person calling
  ``POST /courses/{id}/translate`` on each course in turn. That is a
  list somebody maintains by hand, and it does not survive a hundred
  courses, let alone a thousand.
* **A pass that failed.** A provider outage, a deploy mid-flight, a job
  that hit its attempt cap. The course sits half-translated, and the
  only thing that would revive it is a coincidence: somebody happening
  to edit it again.

So: events for speed, a sweep for certainty. The sweep walks the
courses readers can reach, oldest-checked first, a few per worker tick,
around the clock. Every course is re-examined on a fixed cycle whether
or not anyone touched it, and anything with a gap is queued exactly as
a save would have queued it.

Drafts are deliberately out of scope. They translate when their author
presses "prepare for publication" — a course being written all week
would otherwise be re-translated all week, paying for wording that is
still changing.

What this makes true, and it is the point: adding a language becomes a
config change plus a wait, and a thousand courses need exactly as much
attention as three.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.course import Course, CourseStatus
from app.services.translation.completeness import course_translation_completeness
from app.services.translation.queue import enqueue_course_translation
from app.services.translation.service import is_translation_enabled

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Courses examined per worker tick.
#
# Small on purpose: the check is a tree walk plus one bulk query, which
# is cheap for one course and not free for a thousand. At three a
# minute a catalogue of a thousand courses comes round about every five
# and a half hours — fast enough that a newly added language is fully
# served the same day, slow enough that the sweep is never what the
# database is busy with.
DEFAULT_SWEEP_LIMIT = 3


@dataclass(frozen=True, slots=True)
class SweepReport:
    """What one sweep looked at and what it started."""

    examined: int = 0
    queued: int = 0
    complete: int = 0

    @property
    def found_work(self) -> bool:
        return self.queued > 0


def sweep_courses(db: Session, *, limit: int = DEFAULT_SWEEP_LIMIT) -> SweepReport:
    """Examine the least recently checked live courses; queue any with gaps.

    Safe to call every tick and safe to call when everything is fine:
    a complete course costs one walk and one timestamp write, and
    ``enqueue_course_translation`` is idempotent, so a course already in
    the queue is not queued twice.
    """
    if not is_translation_enabled():
        return SweepReport()

    courses = (
        db.execute(
            select(Course)
            .where(
                Course.deleted_at.is_(None),
                Course.status.in_([CourseStatus.PUBLISHED, CourseStatus.PUBLISHING]),
            )
            # NULLs first: a course nobody has ever checked — one created
            # by an import, or by any path that fires no hook — is the
            # most likely to be missing something.
            .order_by(Course.translations_checked_at.asc().nulls_first())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    if not courses:
        return SweepReport()

    examined = queued = complete = 0
    now = datetime.now(UTC)
    for course in courses:
        examined += 1
        completeness = course_translation_completeness(db, course)
        # Stamped whether or not there was a gap: the timestamp records
        # that the course was *looked at*, which is what keeps the cycle
        # moving. A course with a permanently unfixable field would
        # otherwise be re-examined forever while the rest waited.
        course.translations_checked_at = now
        if completeness.is_complete:
            complete += 1
            continue
        enqueue_course_translation(db, str(course.id))
        queued += 1
        logger.info(
            "sweep: course %s is missing %d of %d translations %s; queued",
            course.id,
            completeness.required - completeness.present,
            completeness.required,
            completeness.by_locale(),
        )

    db.commit()
    if queued:
        logger.info("sweep: examined %d courses, queued %d, %d already whole", examined, queued, complete)
    return SweepReport(examined=examined, queued=queued, complete=complete)


def courses_with_gaps(db: Session, *, limit: int = 50) -> list[tuple[str, dict[str, int]]]:
    """Which courses are missing what, right now — for the admin surface.

    Walks every live course rather than a slice, so it is the expensive
    honest answer rather than the cheap scheduled one. Used by an
    operator asking "is anything behind?", not by the worker.
    """
    if not is_translation_enabled():
        return []
    courses = (
        db.execute(
            select(Course)
            .where(
                Course.deleted_at.is_(None),
                Course.status.in_([CourseStatus.PUBLISHED, CourseStatus.PUBLISHING]),
            )
            .limit(limit)
        )
        .scalars()
        .all()
    )
    out: list[tuple[str, dict[str, int]]] = []
    for course in courses:
        completeness = course_translation_completeness(db, course)
        if not completeness.is_complete:
            out.append((str(course.id), completeness.by_locale()))
    return out


__all__ = ["DEFAULT_SWEEP_LIMIT", "SweepReport", "courses_with_gaps", "sweep_courses"]
