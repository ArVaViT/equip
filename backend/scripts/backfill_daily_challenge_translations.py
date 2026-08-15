"""Translate the Daily Challenge bank into every language the platform serves.

The nightly worker repairs two questions a tick, which is the right pace
for keeping up and the wrong pace for catching up: a bank of 490 written
before German and Ukrainian existed would take most of a year. This is
the catch-up run.

It is the same code path as the worker — ``translate_question`` per
question, idempotent by ``source_hash`` — with a throttle and a resume,
so it can be stopped and restarted without re-billing work already done.

Use
---
  # What would run, no LLM calls, no writes:
  python -m scripts.backfill_daily_challenge_translations --dry-run

  # The questions readers actually reach first: today's, the days
  # already scheduled ahead, and the recent archive.
  python -m scripts.backfill_daily_challenge_translations --limit 60

  # Everything, slowly, in the background:
  python -m scripts.backfill_daily_challenge_translations \
      --limit 0 --sleep 2.0

Requires ``GEMINI_API_KEY`` and a ``DATABASE_URL`` pointing at the
target database. Order is oldest-question-first, which is also
roughly schedule order.

Cost
----
One question is ~12 provider calls (question text, explanation, four
options, each into the three languages it is not written in). On Gemini
Flash Lite that is well under a cent per question; the whole 490-question
bank lands around $2. The binding constraint is the daily request cap on
a free key, not the money — ``--sleep`` exists so a run can be paced
under it rather than dying at 429 halfway through.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from sqlalchemy.orm import sessionmaker

from app.core.database import _get_engine
from app.services.daily_challenge.translate import (
    question_translation_completeness,
    questions_missing_a_language,
    translate_question,
)
from app.services.translation.service import is_translation_enabled

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backfill-dc-translations")

# Large enough to be worth the round trip, small enough that a stopped
# run has not read a thousand rows it will never use.
_PAGE = 25


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="how many questions to repair; 0 means every one that needs it",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=1.0,
        help="seconds between questions, to stay under the key's request cap",
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
        while args.limit == 0 or done < args.limit:
            wanted = _PAGE if args.limit == 0 else min(_PAGE, args.limit - done)
            batch = questions_missing_a_language(db, limit=wanted)
            if not batch:
                logger.info("nothing left to translate")
                break

            for question in batch:
                label = f"{question.bible_book} {question.bible_chapter} ({question.id})"
                if args.dry_run:
                    gaps = question_translation_completeness(db, question)
                    logger.info("would translate %s — %d gaps %s", label, len(gaps.gaps), gaps.by_locale())
                    done += 1
                    continue
                try:
                    report = translate_question(db, question)
                except Exception as exc:
                    # One bad question must not end the run — the point of
                    # a catch-up pass is that it finishes.
                    db.rollback()
                    failed += 1
                    logger.warning("failed %s: %s", label, exc)
                    continue
                done += 1
                logger.info(
                    "%s: %d translated, %d needs review, %d failed (%d done)",
                    label,
                    report.translated,
                    report.needs_review,
                    report.failed,
                    done,
                )
                if args.sleep:
                    time.sleep(args.sleep)

            if args.dry_run:
                # ``questions_missing_a_language`` would return the same
                # page forever when nothing is written.
                break
    finally:
        db.close()

    logger.info("finished: %d questions processed, %d failed", done, failed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
