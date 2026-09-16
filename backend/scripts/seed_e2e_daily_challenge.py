"""Seed one published Daily Challenge question for e2e/CI.

The student dashboard card at ``GET /daily-challenge/today`` needs at
least one ``daily_challenge_questions`` row with ``status='published'``,
``rejected=false``, and servable ``content_versions`` text (question +
every option) in the reader's locale
(``app/services/daily_challenge/text.py``). When today has no explicit
schedule row, ``_autofill_today_schedule``
(``app/services/daily_challenge/schedule.py``) deterministically picks
one from that published pool — so this script does not need to touch
``daily_challenge_schedule`` at all, only the question + options.

This mirrors ``_seed_question_with_options`` in
``tests/test_daily_challenge_service.py`` (insert directly at
``status="published"``) rather than driving the AI generation
orchestrator (``scripts/seed_daily_challenge_bank.py``,
``scripts/bootstrap_daily_challenge_bank.py``) — those require
``GEMINI_API_KEY`` and real LLM calls, which cost money and have no
place in CI.

Text is written for both ``en`` and ``ru`` so the card renders
regardless of which locale the e2e browser's ``Accept-Language``
resolves to (``fetch_question_text_bundle`` does not fall back across
locales any more — see ``text.py``).

Idempotent: the question id is derived deterministically from
``--slug``, so re-runs upsert rather than duplicate.

Usage::

    python -m scripts.seed_e2e_daily_challenge --created-by <teacher_uuid>
"""

from __future__ import annotations

import argparse
import logging
import sys
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import sessionmaker

from app.core.database import _get_engine
from app.models.daily_challenge import DailyChallengeOption, DailyChallengeQuestion
from app.services.content_versions.write import record_human_version

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("seed_e2e_daily_challenge")

# Fixed namespace so re-runs with the same --slug upsert instead of
# duplicating (mirrors the pattern in seed_fat_test_course.py).
_QUESTION_NS = uuid.UUID("f0f0f0f0-0000-4000-8000-000000000002")

_TEXTS = {
    "en": {
        "question": "In Romans 8:1, who is free from condemnation?",
        "explanation": "Romans 8:1 -- no condemnation for those in Christ Jesus.",
        "options": [
            ("Those in Christ Jesus", True),
            ("Those who keep the law", False),
            ("Those who are baptized", False),
            ("Those born of God", False),
        ],
    },
    "ru": {
        "question": "Согласно Римлянам 8:1, кто свободен от осуждения?",
        "explanation": "Римлянам 8:1 -- нет осуждения тем, кто во Христе Иисусе.",
        "options": [
            ("Те, кто во Христе Иисусе", True),
            ("Те, кто соблюдает закон", False),
            ("Те, кто крещён", False),
            ("Те, кто рождён от Бога", False),
        ],
    },
}


def seed(db, *, slug: str, created_by: uuid.UUID) -> DailyChallengeQuestion:
    question_id = uuid.uuid5(_QUESTION_NS, slug)
    question = db.query(DailyChallengeQuestion).filter(DailyChallengeQuestion.id == question_id).first()
    if question is None:
        question = DailyChallengeQuestion(
            id=question_id,
            question_type="multiple_choice",
            status="published",
            rejected=False,
            published_at=datetime.now(UTC),
            published_by=created_by,
            created_by=created_by,
            bible_book="Romans",
            bible_chapter=8,
            bible_verse_from=1,
            bible_verse_to=1,
            category="passage_exegesis",
            source_locale="en",
        )
        db.add(question)
        db.flush()
        logger.info("Created daily_challenge_question %s", question_id)
    else:
        logger.info("daily_challenge_question %s exists; reusing", question_id)

    en_options = _TEXTS["en"]["options"]
    options = (
        db.query(DailyChallengeOption)
        .filter(DailyChallengeOption.question_id == question.id)
        .order_by(DailyChallengeOption.order_index)
        .all()
    )
    if not options:
        options = []
        for idx in range(len(en_options)):
            opt = DailyChallengeOption(
                question_id=question.id,
                is_correct=en_options[idx][1],
                order_index=idx,
            )
            db.add(opt)
            db.flush()
            options.append(opt)
        logger.info("Created %d daily_challenge_options for %s", len(options), question_id)

    for locale, bundle in _TEXTS.items():
        record_human_version(
            db,
            entity_type="daily_challenge_question",
            entity_id=str(question.id),
            field="question_text",
            locale=locale,
            text=bundle["question"],
            authored_by=created_by,
        )
        record_human_version(
            db,
            entity_type="daily_challenge_question",
            entity_id=str(question.id),
            field="explanation",
            locale=locale,
            text=bundle["explanation"],
            authored_by=created_by,
        )
        for idx, opt in enumerate(options):
            record_human_version(
                db,
                entity_type="daily_challenge_option",
                entity_id=str(opt.id),
                field="option_text",
                locale=locale,
                text=bundle["options"][idx][0],
                authored_by=created_by,
            )

    db.commit()
    db.refresh(question)
    return question


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", default="e2e-daily-challenge", help="Deterministic seed slug (idempotency key)")
    parser.add_argument("--created-by", required=True, help="UUID of an existing profiles row (author of record)")
    args = parser.parse_args()

    try:
        created_by = uuid.UUID(args.created_by)
    except ValueError:
        logger.error("--created-by must be a UUID, got %r", args.created_by)
        return 1

    engine = _get_engine()
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with session_factory() as db:
        question = seed(db, slug=args.slug, created_by=created_by)
        logger.info("Daily Challenge question ready: %s (published)", question.id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
