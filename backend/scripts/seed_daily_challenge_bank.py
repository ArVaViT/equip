"""Seed the Daily Challenge bank by running the 6-round orchestrator
against a manifest of passages.

Usage
-----

  # Default manifest (scripts/data/daily_challenge_seed_passages.json):
  python -m scripts.seed_daily_challenge_bank --created-by <teacher_uuid>

  # Custom manifest:
  python -m scripts.seed_daily_challenge_bank \
      --manifest scripts/data/my_manifest.json \
      --created-by <teacher_uuid>

  # Dry run (skip the LLM calls, just validate the manifest):
  python -m scripts.seed_daily_challenge_bank --created-by <uuid> --dry-run

Requires
--------
- ``GEMINI_API_KEY`` set in the environment.
- ``DATABASE_URL`` pointing at the target DB (prod or staging).
- A teacher UUID with permission to create DRAFTs.

Cost model
----------
Each passage is ~7 LLM calls at default settings (~$0.005 on
Gemini Flash Lite). A 30-passage seed run is roughly $0.15-$0.20.

Output
------
Per-passage JSON line with the GenerationOutcome (run_id, created
question ids, reject counts at each gate, errors). Aggregate summary
at the end. Drafts land in the editorial queue; nothing publishes —
humans walk each draft through the 5-stage pipeline from there.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import _get_engine
from app.services.daily_challenge import (
    GeminiPromptClient,
    GenerationRequest,
    run_generation,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("seed")


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).parent / "data" / "daily_challenge_seed_passages.json",
        help="Path to the passage manifest JSON.",
    )
    parser.add_argument(
        "--created-by",
        required=True,
        help="Teacher UUID to stamp on created drafts.",
    )
    parser.add_argument(
        "--n-candidates",
        type=int,
        default=4,
        help="Candidates per agent in Round 1 (default 4 ⇒ 8 total before synthesis).",
    )
    parser.add_argument(
        "--max-survivors",
        type=int,
        default=3,
        help="Cap on Round 3 survivors per passage (default 3).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip LLM calls and DB writes — just validate the manifest + auth.",
    )
    args = parser.parse_args()

    api_key = settings.GEMINI_API_KEY.get_secret_value() if settings.GEMINI_API_KEY else ""
    if not api_key:
        logger.error("GEMINI_API_KEY is not configured")
        return 1

    try:
        actor_id = uuid.UUID(args.created_by)
    except ValueError:
        logger.error("--created-by must be a UUID, got %r", args.created_by)
        return 2

    passages = _load_manifest(args.manifest)
    logger.info("loaded %d passages from %s", len(passages), args.manifest)

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
        return 0

    engine = _get_engine()
    SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    total_drafted = 0
    total_rejected_scripture = 0
    total_rejected_doctrinal = 0
    total_rejected_bilingual = 0
    runs_with_errors = 0

    with GeminiPromptClient(api_key=api_key) as client, SessionFactory() as db:
        for idx, p in enumerate(passages, start=1):
            request = GenerationRequest(
                book=p["book"],
                chapter=p["chapter"],
                verse_from=p.get("verse_from"),
                verse_to=p.get("verse_to"),
                n_candidates_per_agent=args.n_candidates,
                max_survivors=args.max_survivors,
                created_by=actor_id,
            )
            logger.info(
                "(%d/%d) %s %d:%s-%s — starting",
                idx,
                len(passages),
                request.book,
                request.chapter,
                request.verse_from,
                request.verse_to,
            )
            outcome = run_generation(db, client=client, request=request)
            total_drafted += len(outcome.created_question_ids)
            total_rejected_scripture += outcome.rejected_at_scripture
            total_rejected_doctrinal += outcome.rejected_at_doctrinal
            total_rejected_bilingual += outcome.rejected_at_bilingual
            if outcome.errors:
                runs_with_errors += 1
            # One JSON line per run so the operator can pipe to jq.
            print(
                json.dumps(
                    {
                        "passage": {
                            "book": request.book,
                            "chapter": request.chapter,
                            "verse_from": request.verse_from,
                            "verse_to": request.verse_to,
                            "category": p.get("category"),
                        },
                        "outcome": {
                            "generation_run_id": str(outcome.generation_run_id),
                            "created_question_ids": [str(q) for q in outcome.created_question_ids],
                            "rejected_at_scripture": outcome.rejected_at_scripture,
                            "rejected_at_doctrinal": outcome.rejected_at_doctrinal,
                            "rejected_at_bilingual": outcome.rejected_at_bilingual,
                            "rounds_executed": outcome.rounds_executed,
                            "errors": outcome.errors,
                        },
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    logger.info(
        "seed complete | drafted=%d rejected_scripture=%d rejected_doctrinal=%d "
        "rejected_bilingual=%d runs_with_errors=%d",
        total_drafted,
        total_rejected_scripture,
        total_rejected_doctrinal,
        total_rejected_bilingual,
        runs_with_errors,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
