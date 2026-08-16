"""Translate every course into every language the platform serves.

Course content translates on save: the publish hook runs the pipeline
over the tree it just wrote. That covers the language set as it was on
the day of the save, and nothing goes back for a language added later.
So the day German and Ukrainian shipped, every course already in the
catalog stayed exactly as Russian and English as it had been — and the
reader-facing paths, having no spare language any more, had nothing to
show a German visitor at all.

This is the catch-up pass, and it is the same code the publish hook
runs: ``translate_course_content`` walks the course tree, and each
field short-circuits on an unchanged ``source_hash``. Re-running costs
nothing for what is already done, so the run can be stopped and
restarted freely.

Use
---
  # What would run, no LLM calls, no writes:
  python -m scripts.backfill_course_translations --dry-run

  # Everything, paced, in the background:
  python -m scripts.backfill_course_translations --sleep 5

  # One course, when a specific one is behind:
  python -m scripts.backfill_course_translations --course-id <id>

Requires ``GEMINI_API_KEY`` and a ``DATABASE_URL`` pointing at the
target database. ``YOUVERSION_API_KEY`` matters more than it looks:
without it, a quoted verse cannot be resolved in the target language
and the reader gets the source language inside their own prose.

Cost
----
Roughly one provider call per (field, target language). A course with
a dozen lessons is a few hundred; the whole catalog is a few thousand.
``GEMINI_MIN_INTERVAL_SECONDS`` paces the calls; ``--sleep`` paces the
courses.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.core.database import _get_engine
from app.models.course import Course
from app.services.translation.completeness import course_translation_completeness
from app.services.translation.course_pipeline import translate_course_content
from app.services.translation.service import is_translation_enabled
from scripts.db_resilience import run_with_reconnect

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backfill-courses")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--course-id", default=None, help="one course instead of all of them")
    parser.add_argument(
        "--sleep",
        type=float,
        default=5.0,
        help="seconds between courses, on top of the per-call interval",
    )
    parser.add_argument("--dry-run", action="store_true", help="list the work, call nothing")
    args = parser.parse_args()

    if not args.dry_run and not is_translation_enabled():
        logger.error("GEMINI_API_KEY is not set — nothing would be translated")
        return 2

    session_factory = sessionmaker(bind=_get_engine(), expire_on_commit=False)
    db = session_factory()
    done = 0
    failed = 0
    try:
        query = db.query(Course).filter(Course.deleted_at.is_(None))
        if args.course_id:
            query = query.filter(Course.id == args.course_id)
        # Oldest first: the courses students are actually in.
        courses = query.order_by(Course.created_at).all()
        logger.info("%d course(s) to walk", len(courses))

        for course in courses:
            label = f"{course.id} ({course.source_locale})"
            if args.dry_run:
                completeness = course_translation_completeness(db, course)
                logger.info(
                    "would translate %s — %d of %d in place, gaps %s",
                    label,
                    completeness.present,
                    completeness.required,
                    completeness.by_locale(),
                )
                done += 1
                continue

            try:
                report = run_with_reconnect(
                    lambda course=course: translate_course_content(db, course),  # type: ignore[misc]
                    label=label,
                    logger=logger,
                    db=db,
                )
            except DBAPIError:
                # The database never came back. Anything further would
                # fail the same way, and pretending otherwise would end
                # the run reporting success.
                raise
            except Exception as exc:
                # One bad course must not end the run.
                db.rollback()
                failed += 1
                logger.warning("failed %s: %s", label, exc)
                continue
            done += 1
            logger.info(
                "%s: %d translated, %d skipped, %d needs review, %d failed (%d done)",
                label,
                report.translated,
                report.skipped,
                report.needs_review,
                report.failed,
                done,
            )
            if args.sleep:
                time.sleep(args.sleep)
    finally:
        db.close()

    logger.info("finished: %d course(s) processed, %d failed", done, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
