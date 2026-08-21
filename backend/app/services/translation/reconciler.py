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

Not everything a reader sees belongs to a course. A platform-wide
announcement — the banner on every dashboard, ``course_id IS NULL`` —
has no course to derive a language from, so ``reconcile_entity`` returns
an empty report for it and the course walk never yields it. Nothing
translated those, and because a reader is never served a language they
did not choose, a German reader got an empty title and empty body rather
than the Russian original. The platform-wide pass below is where they
are picked up.

What this makes true, and it is the point: adding a language becomes a
config change plus a wait, and a thousand courses need exactly as much
attention as three.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.announcement import Announcement
from app.models.content_version import ContentVersion, ContentVersionStatus
from app.models.course import Course, CourseStatus
from app.schemas.locale import LOCALE_CODES, LocaleCode, normalize_locale
from app.services.language_detection import detect_locale
from app.services.translation.completeness import (
    UNACTIONABLE_GAP_REASONS,
    completeness_of,
    course_translation_completeness,
)
from app.services.translation.orchestrator import (
    OrchestratorReport,
    TranslationFieldSpec,
    translate_entity_fields,
)
from app.services.translation.queue import enqueue_course_translation
from app.services.translation.registry import REGISTRY
from app.services.translation.service import is_translation_enabled

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.services.translation.budget import TranslationBudget
    from app.services.translation.completeness import TranslationGap
    from app.services.translation.protocol import ContentKind, TranslationProvider

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

# Platform-wide announcements repaired per tick. Unlike a course, an
# announcement is translated here and now rather than queued — there are
# two short fields and no tree behind them — so this is a count of
# provider work inside the invocation, and it is small for the same
# reason the pool sweep's limit is.
DEFAULT_ANNOUNCEMENT_SWEEP_LIMIT = 5

_ANNOUNCEMENT_CONTEXT = "Site-wide announcement shown to every Equip user."

# Read from the registry rather than restated: the announcement's fields
# and their content kinds are declared once, in ``registry.py``, and a
# second list here would be a second list that drifts.
_ANNOUNCEMENT_FIELD_KINDS: dict[str, ContentKind] = {fs.name: fs.content_kind for fs in REGISTRY["announcement"].fields}


@dataclass(frozen=True, slots=True)
class SweepReport:
    """What one sweep looked at and what it started."""

    examined: int = 0
    queued: int = 0
    complete: int = 0
    #: Courses with a gap that looked actionable and that the pass the
    #: worker would run does not address — see ``_gaps_the_plan_can_close``.
    #: Counted because "queued 0, complete 0" is otherwise indistinguishable
    #: from "queued 0, everything fine", and the difference is a course
    #: that will never finish.
    stalled: int = 0
    #: Rows written by the platform-wide announcement pass. Courses are
    #: queued and translated on a later tick; announcements are done in
    #: this one, so they are counted in rows and not in jobs.
    announcement_rows: OrchestratorReport = dataclass_field(default_factory=OrchestratorReport)

    @property
    def found_work(self) -> bool:
        return self.queued > 0


def sweep_courses(
    db: Session,
    *,
    limit: int = DEFAULT_SWEEP_LIMIT,
    provider: TranslationProvider | None = None,
    budget: TranslationBudget | None = None,
) -> SweepReport:
    """Examine the least recently checked live courses; queue any with gaps.

    Safe to call every tick and safe to call when everything is fine:
    a complete course costs one walk and one timestamp write, and
    ``enqueue_course_translation`` is idempotent, so a course already in
    the queue is not queued twice.

    Two things stop a course being queued, and they are different. A gap
    only a person can move (``UNACTIONABLE_GAP_REASONS``) is named: we
    know what it is and who has to act. A gap the plan produces no task
    for is unnamed — it means the check and the pass disagree, which is a
    bug in one of them — so it is refused *and* logged at WARNING, and
    counted in ``SweepReport.stalled``. See ``_gaps_the_plan_can_close``.

    Also runs ``sweep_global_announcements``, because this is the one
    thing the worker calls when the queue is empty and a platform-wide
    announcement is reachable from nowhere else — not from a save hook,
    which needs a published course, and not from the course walk, which
    is bounded by ``course_id``. A pass nothing calls is a pass that does
    not exist.
    """
    if not is_translation_enabled():
        logger.warning("translation disabled: no provider configured; sweep did nothing")
        return SweepReport()

    announcement_rows = sweep_global_announcements(db, provider=provider, budget=budget)

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
        return SweepReport(announcement_rows=announcement_rows)

    examined = queued = complete = stalled = 0
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

        # A row parked for review, or one that spent its five attempts,
        # is a gap — and it is not this sweep's gap. Sampling runs at
        # temperature 0, so asking again returns the same text and the
        # same verdict; the executor will not retry a ``failed_permanent``
        # row at all. Both move when a person acts through the admin
        # surface, and neither moves for a worker tick.
        #
        # Queueing them anyway is how the worker ends up running once a
        # minute, planning a thousand fields, skipping all of them and
        # reporting success — which is precisely what production did.
        # The course stays incomplete, which is true and is what keeps
        # it out of the catalogue; it just stops being re-queued for a
        # job with nothing to do.
        #
        # And the cost is not confined to the one course. ``sweep_courses``
        # and the idle Daily Challenge pool sweep both run only when
        # ``claim_next_job`` returns None. A course that re-queues itself
        # every cycle keeps the queue non-empty, so the pool sweep never
        # gets a tick: one permanently-broken course switches off the
        # self-healing layer for the whole platform.
        actionable = [gap for gap in completeness.gaps if gap.reason not in UNACTIONABLE_GAP_REASONS]
        if not actionable:
            logger.info(
                "sweep: course %s is waiting on a person for %d field(s), not on the pipeline",
                course.id,
                len(completeness.gaps),
            )
            continue

        # The last question, and the general one: of the gaps that look
        # like work, is any of them work *this* pipeline would do?
        #
        # ``UNACTIONABLE_GAP_REASONS`` above answers that by enumerating
        # the shapes we already know about, and each of the four
        # occurrences so far arrived in a shape the previous enumeration
        # did not cover. So this asks the plan instead of guessing: the
        # pass the worker is about to run is ``plan_course_tasks``, and a
        # gap it produces no task for is a gap the job cannot close, for
        # whatever reason — one nobody has to have thought of first.
        closable = _gaps_the_plan_can_close(db, course, actionable)
        if not closable:
            stalled += 1
            # WARNING, not INFO: on this deployment INFO from application
            # loggers does not reach the log drain, and this is the exact
            # condition that spent a day looking healthy. Every job it
            # produced finished ``done``.
            logger.warning(
                "sweep: course %s has %d gap(s) the pipeline plans no work for %s; not queued",
                course.id,
                len(actionable),
                completeness.by_locale(),
            )
            continue

        enqueue_course_translation(db, str(course.id))
        queued += 1
        logger.info(
            "sweep: course %s is missing %d of %d translations %s; queued",
            course.id,
            len(actionable),
            completeness.required,
            completeness.by_locale(),
        )

    db.commit()
    if queued:
        logger.info("sweep: examined %d courses, queued %d, %d already whole", examined, queued, complete)
    return SweepReport(
        examined=examined,
        queued=queued,
        complete=complete,
        stalled=stalled,
        announcement_rows=announcement_rows,
    )


def _gaps_the_plan_can_close(db: Session, course: Course, gaps: list[TranslationGap]) -> list[TranslationGap]:
    """Which of ``gaps`` the worker's own pass produces a task for.

    The check and the plan are built from the same walk and the same
    field specs, so in a healthy course this returns everything it was
    given and costs one tree walk. It exists for the case where they
    disagree — which has now happened four times, each time in a shape
    the previous fix did not anticipate:

    * a course fetched two different ways, so the check counted binned
      chapters the plan skipped (``course_tree``);
    * a field whose only human row was filed under a locale the reader
      resolver would not answer at, so the check required nothing
      (``registry._authored_texts``);
    * ``failed_permanent`` collapsed into ``failed``, so a terminal row
      read as retryable (``completeness``);
    * a hydrated ``course.title == ""`` against an un-hydrated
      ``AttributeError``, so the check required three languages of a
      title the plan had dropped (``registry.entity_field_specs``).

    Each was fixed at its own root, and each was invisible until somebody
    counted jobs. This is the backstop for the fifth: not a diagnosis,
    just the refusal to queue a job that provably has nothing to do.

    Deliberately a *necessary* condition and not a sufficient one. A task
    can exist and still be skipped — the executor decides that from rows
    this function does not read — so a course is queued whenever the plan
    so much as mentions one of its gaps. Erring that way is the point:
    queueing a job that turns out to be a no-op costs two seconds, and
    refusing to queue one that would have worked stops a course being
    translated at all, silently. A provider outage stays on the queueing
    side, which is what makes the catalogue resume the minute the
    provider does — the plan is built from source text and knows nothing
    about whether the provider is answering.
    """
    from app.services.translation.course_pipeline import plan_course_tasks

    planned = {
        (task.entity_type, task.entity_id, task.field, task.target_locale) for task in plan_course_tasks(db, course)
    }
    return [gap for gap in gaps if (gap.entity_type, gap.entity_id, gap.field, gap.locale) in planned]


def _global_announcement_sources(db: Session) -> dict[str, list[TranslationFieldSpec]]:
    """Every platform-wide announcement's source text, in two queries.

    ``announcements.title`` and ``.content`` are dropped columns — both
    texts live in ``content_versions`` — so the source of a global
    announcement is its active human row, and the language it is in is
    the language that row is stored under. Re-detecting per field on top
    of that is what lets a Russian admin posting in Russian from an
    English interface still be translated in the right direction.

    Why this reads the rows itself instead of calling
    ``entity_field_specs``: that helper fetches the text at ONE declared
    locale, and a global announcement has no course to declare one. Ask
    it with the wrong guess and ``fetch_cv_entity_texts_with_fallback``
    resolves ``fallback="auto"`` to ``"none"`` wherever a provider is
    configured and hands back nothing — which is the same read that
    served a German reader ``title=''`` and ``content=''``. The sweep has
    to read these rows anyway to find the gap; it passes them on rather
    than asking again with a guess.

    ``content_versions.entity_id`` is text while ``announcements.id`` is
    a uuid, and the dialects disagree about that join: Postgres refuses
    it, SQLite accepts it and matches nothing — the worse failure,
    because the sweep would go quiet and look healthy. Bridged in Python,
    deliberately, exactly as the Daily Challenge sweep does.
    """
    ids = [str(row[0]) for row in db.query(Announcement.id).filter(Announcement.course_id.is_(None)).all()]
    if not ids:
        return {}

    rows = (
        db.query(
            ContentVersion.entity_id,
            ContentVersion.field,
            ContentVersion.locale,
            ContentVersion.text,
        )
        .filter(
            ContentVersion.entity_type == "announcement",
            ContentVersion.entity_id.in_(ids),
            ContentVersion.origin == "human",
            ContentVersion.status == ContentVersionStatus.OK,
            ContentVersion.superseded_by.is_(None),
        )
        .all()
    )

    sources: dict[str, list[TranslationFieldSpec]] = {}
    for entity_id, field, locale, text in rows:
        kind = _ANNOUNCEMENT_FIELD_KINDS.get(field)
        if kind is None or not text or not str(text).strip():
            continue
        stored: LocaleCode = normalize_locale(locale)
        detected = detect_locale(str(text))
        sources.setdefault(entity_id, []).append(
            TranslationFieldSpec(
                field=field,
                text=text,
                content_kind=kind,
                source_locale=detected or stored,
            )
        )
    return sources


def sweep_global_announcements(
    db: Session,
    *,
    limit: int = DEFAULT_ANNOUNCEMENT_SWEEP_LIMIT,
    provider: TranslationProvider | None = None,
    budget: TranslationBudget | None = None,
) -> OrchestratorReport:
    """Translate the platform-wide announcements that are behind.

    A global announcement (``course_id IS NULL``) is admin-authored, goes
    to every dashboard on the platform, and had no translation path at
    all: the create route only reconciles when ``data.course_id`` is set,
    the registry resolves an announcement's language through its course
    and returns ``None`` without one, and ``course_tree`` yields only the
    rows bound to the course being walked. So the banner every user sees
    was the one piece of reader-facing text that stayed in whatever
    language the admin typed — and since a reader is never served a
    language they did not choose, everyone else got a blank.

    Only announcements with a gap the pipeline can actually close are
    touched, and only ``limit`` of them per tick. Already-translated ones
    cost nothing anyway (``source_hash`` short-circuits), but finding
    that out costs a plan each, and a growing archive of settled
    announcements should not slowly become the tick's whole budget.
    """
    if not is_translation_enabled():
        return OrchestratorReport()

    sources = _global_announcement_sources(db)
    if not sources:
        return OrchestratorReport()

    wanted: dict[tuple[str, str, str], set[str]] = {}
    for entity_id, specs in sources.items():
        for spec in specs:
            targets: set[str] = {code for code in LOCALE_CODES if code != spec.source_locale}
            if targets:
                wanted[("announcement", entity_id, spec.field)] = targets

    completeness = completeness_of(db, wanted)
    # Same rule the course sweep applies one level up: a row a person has
    # to read, or one that has spent its attempts, is a real gap and not
    # one another tick will close. Without this the oldest broken
    # announcement would be re-planned every minute forever.
    behind: list[str] = []
    for gap in completeness.gaps:
        if gap.reason in UNACTIONABLE_GAP_REASONS:
            continue
        if gap.entity_id not in behind:
            behind.append(gap.entity_id)

    total = OrchestratorReport()
    for entity_id in behind[:limit]:
        if budget is not None and not budget.can_afford_one_call():
            break
        specs = sources[entity_id]
        report = translate_entity_fields(
            db,
            entity_type="announcement",
            entity_id=entity_id,
            # The entity-level fallback only applies to a field whose own
            # language could not be detected; every spec above carries
            # its own, so a two-language announcement still travels in
            # the right direction per field.
            source_locale=specs[0].source_locale or normalize_locale(None),
            fields=specs,
            context=_ANNOUNCEMENT_CONTEXT,
            provider=provider,
            budget=budget,
        )
        total = OrchestratorReport(
            translated=total.translated + report.translated,
            skipped=total.skipped + report.skipped,
            failed=total.failed + report.failed,
            needs_review=total.needs_review + report.needs_review,
        )

    if total.translated or total.failed or total.needs_review:
        logger.info(
            "sweep: platform-wide announcements translated=%d failed=%d needs_review=%d",
            total.translated,
            total.failed,
            total.needs_review,
        )
    return total


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


__all__ = [
    "DEFAULT_ANNOUNCEMENT_SWEEP_LIMIT",
    "DEFAULT_SWEEP_LIMIT",
    "SweepReport",
    "courses_with_gaps",
    "sweep_courses",
    "sweep_global_announcements",
]
