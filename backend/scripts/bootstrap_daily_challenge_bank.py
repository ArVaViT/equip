"""One-shot bootstrap for the Daily Challenge bank.

Runs the seed orchestrator against the passage manifest, then walks
every surviving DRAFT through the 5-stage editorial pipeline up to
``published`` and schedules each one forward from today.

This script bypasses the normal human editorial gate. It's the
launch-batch shortcut: AI-vetted (6-round confrontation + scripture
validation + doctrinal review + bilingual review), pre-pilot. The
human-pilot review stage is replaced by editor rejection retroactively
(``POST /admin/daily-challenge/questions/{id}/reject``) for any
question that doesn't pass eyeball review post-publish.

Use
---
  python -m scripts.bootstrap_daily_challenge_bank \
      --created-by <admin_uuid> \
      --manifest scripts/data/daily_challenge_seed_passages.json \
      --max-passages 10 \
      --start-date 2026-05-31

  # Dry run: validate manifest + auth, no LLM, no DB writes.
  python -m scripts.bootstrap_daily_challenge_bank \
      --created-by <admin_uuid> --dry-run

Requires:
- GEMINI_API_KEY (orchestrator)
- DATABASE_URL pointing at the target DB

Cost
----
~$0.005 per passage on Gemini Flash Lite; default ``--max-passages
10`` is roughly $0.05 - $0.10. Bumping to 45 (the full manifest) ≈
$0.20 - $0.25.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import _get_engine
from app.models.daily_challenge import (
    DailyChallengeQuestion,
    DailyChallengeQuestionStatus,
    DailyChallengeSchedule,
)
from app.services.daily_challenge import (
    GeminiPromptClient,
    GenerationRequest,
    promote_status,
    publish_question,
    run_generation,
    schedule_for_date,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("bootstrap-dc")

_PROMOTE_STAGES_FROM_DRAFT = 4  # draft → ... → pilot_passed


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        logger.error("manifest not found: %s", path)
        sys.exit(2)
    data = json.loads(path.read_text(encoding="utf-8"))
    passages = data.get("passages") if isinstance(data, dict) else None
    if not isinstance(passages, list) or not passages:
        logger.error("manifest %s missing non-empty 'passages' array", path)
        sys.exit(2)
    return passages


def _next_unscheduled_date(db, *, start: date) -> date:
    """Return the earliest date ``>= start`` that has no schedule row.

    Scheduling forward only — we never overwrite an existing day."""
    taken = {
        s.challenge_date
        for s in db.query(DailyChallengeSchedule).filter(DailyChallengeSchedule.challenge_date >= start).all()
    }
    d = start
    while d in taken:
        d += timedelta(days=1)
    return d


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).parent / "data" / "daily_challenge_seed_passages.json",
    )
    parser.add_argument("--created-by", required=True, help="Admin/teacher UUID")
    parser.add_argument(
        "--max-passages",
        type=int,
        default=10,
        help="Cap on how many manifest passages to feed (cost guard).",
    )
    parser.add_argument(
        "--n-candidates",
        type=int,
        default=4,
        help="Round-1 candidates per agent (8 total before synthesis).",
    )
    parser.add_argument(
        "--max-survivors",
        type=int,
        default=3,
        help="Round-3 survivor cap per passage.",
    )
    parser.add_argument(
        "--start-date",
        type=date.fromisoformat,
        default=datetime.now(UTC).date(),
        help="First date to schedule from (UTC). Default today.",
    )
    parser.add_argument(
        "--throttle-seconds",
        type=float,
        default=0.0,
        help="Min seconds between Gemini calls (free-tier RPM guard; 0 = no throttle).",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="Per-call Gemini retry budget (bump when throttling a free-tier key).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No LLM calls, no DB writes; just exercise manifest + auth.",
    )
    args = parser.parse_args()

    api_key = settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else ""
    if not api_key:
        logger.error("GEMINI_API_KEY missing")
        return 1
    try:
        actor_id = uuid.UUID(args.created_by)
    except ValueError:
        logger.error("--created-by must be a UUID, got %r", args.created_by)
        return 2

    passages = _load_manifest(args.manifest)[: args.max_passages]
    logger.info("loaded %d passages (capped at --max-passages)", len(passages))

    if args.dry_run:
        for p in passages:
            logger.info(
                "dry-run | %s %d:%s-%s (%s)",
                p.get("book"),
                p.get("chapter"),
                p.get("verse_from"),
                p.get("verse_to"),
                p.get("category"),
            )
        logger.info("dry-run | start-date=%s", args.start_date)
        return 0

    engine = _get_engine()
    SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    drafted_total = 0
    published_total = 0
    scheduled_total = 0
    publish_failures: list[str] = []
    schedule_failures: list[str] = []

    client_kwargs: dict[str, Any] = {"api_key": api_key, "max_retries": args.max_retries}
    if args.throttle_seconds > 0:
        # Free-tier RPM guard: space calls out, and give 429s a real cooldown
        # (default 0.5s cap is useless against a per-minute quota).
        client_kwargs["min_request_interval_seconds"] = args.throttle_seconds
        client_kwargs["retry_backoff_seconds"] = max(2.0, args.throttle_seconds)
        client_kwargs["retry_backoff_cap_seconds"] = 60.0
    with GeminiPromptClient(**client_kwargs) as client, SessionFactory() as db:
        cursor_date = _next_unscheduled_date(db, start=args.start_date)

        for idx, p in enumerate(passages, start=1):
            req = GenerationRequest(
                book=p["book"],
                chapter=p["chapter"],
                verse_from=p.get("verse_from"),
                verse_to=p.get("verse_to"),
                n_candidates_per_agent=args.n_candidates,
                max_survivors=args.max_survivors,
                created_by=actor_id,
            )
            logger.info(
                "(%d/%d) generating %s %d:%s-%s",
                idx,
                len(passages),
                req.book,
                req.chapter,
                req.verse_from,
                req.verse_to,
            )
            outcome = run_generation(db, client=client, request=req)
            drafted = len(outcome.created_question_ids)
            drafted_total += drafted
            logger.info(
                "  generated drafts=%d rejected_scripture=%d rejected_doctrinal=%d rejected_bilingual=%d errors=%d",
                drafted,
                outcome.rejected_at_scripture,
                outcome.rejected_at_doctrinal,
                outcome.rejected_at_bilingual,
                len(outcome.errors),
            )

            # Walk each draft draft → ... → pilot_passed → published,
            # then schedule it for ``cursor_date``.
            for qid in outcome.created_question_ids:
                q = db.query(DailyChallengeQuestion).filter_by(id=qid).one()
                try:
                    for _ in range(_PROMOTE_STAGES_FROM_DRAFT):
                        q = promote_status(db, question=q, actor_id=actor_id)
                    if q.status != DailyChallengeQuestionStatus.PILOT_PASSED.value:
                        publish_failures.append(
                            f"{qid}: ended at status={q.status} after {_PROMOTE_STAGES_FROM_DRAFT} promotes"
                        )
                        continue
                    q = publish_question(db, question=q, actor_id=actor_id)
                    published_total += 1
                except Exception as exc:
                    publish_failures.append(f"{qid}: {exc!s}")
                    logger.warning("publish failed for %s: %s", qid, exc)
                    db.rollback()
                    continue

                try:
                    schedule_for_date(
                        db,
                        question=q,
                        on_date=cursor_date,
                        actor_id=actor_id,
                    )
                    scheduled_total += 1
                    logger.info("  scheduled %s for %s", qid, cursor_date.isoformat())
                    cursor_date = _next_unscheduled_date(db, start=cursor_date + timedelta(days=1))
                except Exception as exc:
                    schedule_failures.append(f"{qid} → {cursor_date.isoformat()}: {exc!s}")
                    logger.warning("schedule failed for %s on %s: %s", qid, cursor_date, exc)
                    db.rollback()

    logger.info(
        "bootstrap complete | drafted=%d published=%d scheduled=%d publish_failures=%d schedule_failures=%d",
        drafted_total,
        published_total,
        scheduled_total,
        len(publish_failures),
        len(schedule_failures),
    )
    for failure in publish_failures:
        logger.warning("  publish-fail: %s", failure)
    for failure in schedule_failures:
        logger.warning("  schedule-fail: %s", failure)
    return 0


if __name__ == "__main__":
    sys.exit(main())
