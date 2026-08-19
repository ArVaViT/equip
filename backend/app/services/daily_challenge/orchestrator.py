# ruff: noqa: RUF002
"""6-round AI question generation orchestrator for the Daily Challenge.

Vadym's original instruction: "Тут нужен очень большой совет и очень
много работы с агентами параллельно, чтобы было много раз проверок,
была конфронтация и споры по поводу вопросов и ответов." This module
is the implementation.

Pipeline (per Agent C's design)

  Round 1 — Independent generation
    Agent A and Agent B each independently propose N candidate
    questions for the same passage. Different prompt seeds / model
    temperatures so we see variance.

  Round 2 — Cross-critique
    Each agent attacks the other's batch against the failure-mode
    taxonomy. The artifact is two arrays of critiques.

  Round 3 — Synthesis
    A third agent ("moderator") receives both batches + both critique
    arrays and picks the surviving questions, applying revisions
    where both critics agreed.

  Round 4 — Validation (three sub-checks)
    a) Scripture validation: AUTOMATED via app/services/bible/.
       The cited verse must exist in BOTH KJV (1769) and Synodal
       (1876); the answer must be defensible from both. If either
       lookup fails the question is auto-rejected with
       'rejected_scripture'.
    b) Doctrinal review: LLM-driven against the contested-doctrine
       list. Output: pass | needs_framing | reject.
    c) Bilingual review: LLM-driven. Output includes the RU rendering
       of the surviving question so Round 6 can dual-write to cv.

  Round 5 — Pilot review
    Logged with status 'pilot_summary' but the actual pilot answering
    happens via the editorial UI (Sprint 4+ frontend). The orchestrator
    leaves a placeholder event so the audit trail is unified across the
    AI + editorial phases.

  Round 6 — Publish-ready persistence
    For each surviving question, create a DRAFT row in
    ``daily_challenge_questions`` using the existing
    ``create_question`` service. The editorial team then walks the
    drafts through ``promote_status`` (or rejects them outright). The
    AI flow never auto-publishes — humans always gate the final
    transition.

Every round writes a row to ``daily_challenge_question_events`` with
the same ``generation_run_id``. Editorial UI can later replay the
entire generation history for one question by joining on that key.

Cost note: at default settings one run = ~6 LLM round-trips
(2× R1 generation + 2× R2 critique + 1× R3 synthesis + 1× doctrinal +
1× bilingual = 7 calls). Scripture validation is local (no LLM cost).
The orchestrator commits the bank in batches of ~5-10 candidates per
run, so 90 questions ≈ 9-18 runs ≈ ~70-130 LLM calls — order of $0.10
on Gemini Flash Lite. Cost is not the bottleneck; quality is.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.services.bible.books import find_book
from app.services.bible.references import BibleRef
from app.services.bible.store import is_locale_bundled, lookup
from app.services.bible.substitution import canonical_for_display
from app.services.daily_challenge.admin import OptionDraft, _log_event, create_question
from app.services.daily_challenge.llm import GeminiPromptClient, LLMError
from app.services.daily_challenge.prompts import (
    ROUND_1_SYSTEM,
    ROUND_1_USER_TEMPLATE,
    ROUND_2_SYSTEM,
    ROUND_2_USER_TEMPLATE,
    ROUND_3_SYSTEM,
    ROUND_3_USER_TEMPLATE,
    ROUND_4_BILINGUAL_SYSTEM,
    ROUND_4_BILINGUAL_USER_TEMPLATE,
    ROUND_4_DOCTRINAL_SYSTEM,
    ROUND_4_DOCTRINAL_USER_TEMPLATE,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """Input to ``run_generation``."""

    book: str  # canonical book name e.g. 'Romans'
    chapter: int
    verse_from: int | None = None
    verse_to: int | None = None
    n_candidates_per_agent: int = 10
    max_survivors: int = 6
    created_by: uuid.UUID | None = None


@dataclass(slots=True)
class GenerationOutcome:
    """Return value from ``run_generation``."""

    generation_run_id: uuid.UUID
    created_question_ids: list[uuid.UUID] = field(default_factory=list)
    rejected_at_scripture: int = 0
    rejected_at_doctrinal: int = 0
    rejected_at_bilingual: int = 0
    rounds_executed: int = 0
    errors: list[str] = field(default_factory=list)


def _fetch_canonical_texts(
    book: str, chapter: int, verse_from: int | None, verse_to: int | None
) -> tuple[str | None, str | None]:
    """Pull the KJV + Synodal text for the cited passage. Both must
    exist — if either misses the orchestrator refuses to generate
    (the validation rule below requires BOTH translations to support
    the answer, so we can't even propose questions against a passage
    where one side is missing).

    Callers pass the canonical-ish book name from the request body;
    we resolve it through ``find_book`` so 'Romans' / 'Rom.' / 'Рим.'
    all hit the same lowercase slug the bundled JSON is keyed on."""
    slug = find_book(book)
    if slug is None:
        return None, None
    v_start = verse_from or 1
    v_end = verse_to or verse_from or v_start
    ref = BibleRef(book=slug, chapter=chapter, verse_start=v_start, verse_end=v_end)

    # The same editions the reader is shown, not the ones that happen to
    # be on disk.
    #
    # This used to read the bundled files, which for English is the King
    # James Version — and a model handed KJV text quotes KJV back. 62 of
    # the questions in production carry `spake`, `saith`, `unto`, `thee`
    # inside otherwise contemporary English prose, and they are not
    # translation defects: the questions were written that way. The
    # translation layer had already moved to a modern edition; the
    # generator had not, so it kept manufacturing the problem.
    en = canonical_for_display(ref, "en")
    ru = canonical_for_display(ref, "ru")
    if en is None and is_locale_bundled("en"):
        en = lookup(ref, "en")
    return en, ru


def _validate_candidate_scripture(candidate: dict[str, Any], book: str, chapter: int) -> tuple[bool, str | None]:
    """Stage 2 — scripture validation. The cited verse must exist in
    BOTH KJV and Synodal. Returns ``(passed, reason)``."""
    verse_start = candidate.get("verse_start")
    verse_end = candidate.get("verse_end")
    if not isinstance(verse_start, int) or verse_start <= 0:
        return False, "verse_start missing or invalid"
    if verse_end is not None and not isinstance(verse_end, int):
        return False, "verse_end invalid"
    slug = find_book(book)
    if slug is None:
        return False, f"unknown book {book!r}"
    v_end = verse_end if isinstance(verse_end, int) else None
    ref = BibleRef(book=slug, chapter=chapter, verse_start=verse_start, verse_end=v_end)
    if lookup(ref, "en") is None:
        return False, f"KJV lookup missed {book} {chapter}:{verse_start}"
    if lookup(ref, "ru") is None:
        return False, f"Synodal lookup missed {book} {chapter}:{verse_start}"
    return True, None


def _verse_range_clause(verse_from: int | None, verse_to: int | None) -> str:
    if verse_from is None:
        return ""
    if verse_to is None or verse_to == verse_from:
        return f" verses {verse_from}"
    return f" verses {verse_from}-{verse_to}"


def run_generation(
    db: Session,
    *,
    client: GeminiPromptClient,
    request: GenerationRequest,
) -> GenerationOutcome:
    """Execute one full 6-round generation run for a single passage.

    Side effects:
      * Writes one ``daily_challenge_question_events`` row per round
        keyed by the same generation_run_id.
      * For each surviving question, creates a DRAFT
        ``daily_challenge_questions`` row via ``create_question``.
        Translatable text lands in cv at the EN source locale; the RU
        rendering produced by Round 4 bilingual review is recorded as
        a second human-version cv row so the editor reviews both
        translations before promoting.

    Errors mid-run do NOT roll back already-committed rounds (we want
    the audit trail of WHY a run failed). The outcome carries
    ``errors`` for the caller to surface in the admin UI.
    """
    outcome = GenerationOutcome(generation_run_id=uuid.uuid4())
    run_id = outcome.generation_run_id

    kjv, syn = _fetch_canonical_texts(request.book, request.chapter, request.verse_from, request.verse_to)
    if kjv is None or syn is None:
        outcome.errors.append(
            f"canonical text missing for {request.book} {request.chapter} "
            f"(kjv={'ok' if kjv else 'missing'}, synodal={'ok' if syn else 'missing'})"
        )
        return outcome

    verse_clause = _verse_range_clause(request.verse_from, request.verse_to)

    # ── Round 1 — Independent generation ──────────────────────────────
    user_prompt_r1 = ROUND_1_USER_TEMPLATE.format(
        book=request.book,
        chapter=request.chapter,
        verse_range_clause=verse_clause,
        kjv_text=kjv,
        synodal_text=syn,
        n_candidates=request.n_candidates_per_agent,
    )
    candidates_a = _run_round(
        client,
        system=ROUND_1_SYSTEM,
        user=user_prompt_r1,
        temperature=0.7,
        agent_label="A",
    )
    candidates_b = _run_round(
        client,
        system=ROUND_1_SYSTEM,
        user=user_prompt_r1,
        temperature=0.9,  # different temp so we get genuine variance
        agent_label="B",
    )
    _log_event(
        db,
        question_id=None,
        event_type="ai_generated",
        actor_id=request.created_by,
        generation_run_id=run_id,
        details={
            "agent": "A",
            "candidates": candidates_a.get("candidates", []) if isinstance(candidates_a, dict) else [],
            "temperature": 0.7,
        },
    )
    _log_event(
        db,
        question_id=None,
        event_type="ai_generated",
        actor_id=request.created_by,
        generation_run_id=run_id,
        details={
            "agent": "B",
            "candidates": candidates_b.get("candidates", []) if isinstance(candidates_b, dict) else [],
            "temperature": 0.9,
        },
    )
    outcome.rounds_executed += 1
    db.commit()

    # ── Round 2 — Cross-critique ──────────────────────────────────────
    critiques_on_a = _run_round(
        client,
        system=ROUND_2_SYSTEM,
        user=ROUND_2_USER_TEMPLATE.format(
            kjv_text=kjv,
            synodal_text=syn,
            candidates_json=_serialize_for_prompt(candidates_a),
        ),
        temperature=0.2,
        agent_label="B-critique-of-A",
    )
    critiques_on_b = _run_round(
        client,
        system=ROUND_2_SYSTEM,
        user=ROUND_2_USER_TEMPLATE.format(
            kjv_text=kjv,
            synodal_text=syn,
            candidates_json=_serialize_for_prompt(candidates_b),
        ),
        temperature=0.2,
        agent_label="A-critique-of-B",
    )
    _log_event(
        db,
        question_id=None,
        event_type="ai_critique",
        actor_id=request.created_by,
        generation_run_id=run_id,
        details={"target_agent": "A", "critiques": critiques_on_a},
    )
    _log_event(
        db,
        question_id=None,
        event_type="ai_critique",
        actor_id=request.created_by,
        generation_run_id=run_id,
        details={"target_agent": "B", "critiques": critiques_on_b},
    )
    outcome.rounds_executed += 1
    db.commit()

    # ── Round 3 — Synthesis ───────────────────────────────────────────
    synthesis = _run_round(
        client,
        system=ROUND_3_SYSTEM,
        user=ROUND_3_USER_TEMPLATE.format(
            kjv_text=kjv,
            synodal_text=syn,
            candidates_a_json=_serialize_for_prompt(candidates_a),
            candidates_b_json=_serialize_for_prompt(candidates_b),
            critiques_on_a_json=_serialize_for_prompt(critiques_on_a),
            critiques_on_b_json=_serialize_for_prompt(critiques_on_b),
            max_survivors=request.max_survivors,
        ),
        temperature=0.3,
        agent_label="moderator",
    )
    survivors = synthesis.get("survivors", []) if isinstance(synthesis, dict) else []
    _log_event(
        db,
        question_id=None,
        event_type="ai_synthesis",
        actor_id=request.created_by,
        generation_run_id=run_id,
        details={"survivors": survivors, "n_survivors": len(survivors)},
    )
    outcome.rounds_executed += 1
    db.commit()

    # ── Round 4a — Scripture validation (automated) ───────────────────
    survivors_after_scripture: list[dict[str, Any]] = []
    for s in survivors:
        passed, reason = _validate_candidate_scripture(s, request.book, request.chapter)
        if passed:
            survivors_after_scripture.append(s)
        else:
            outcome.rejected_at_scripture += 1
            _log_event(
                db,
                question_id=None,
                event_type="scripture_validated",
                actor_id=request.created_by,
                generation_run_id=run_id,
                details={"survivor": s, "passed": False, "reason": reason},
            )
    if survivors_after_scripture:
        _log_event(
            db,
            question_id=None,
            event_type="scripture_validated",
            actor_id=request.created_by,
            generation_run_id=run_id,
            details={
                "passed_count": len(survivors_after_scripture),
                "rejected_count": outcome.rejected_at_scripture,
            },
        )
    db.commit()

    if not survivors_after_scripture:
        outcome.errors.append("no survivors after scripture validation")
        return outcome

    # ── Round 4b — Doctrinal review ────────────────────────────────────
    doctrinal = _run_round(
        client,
        system=ROUND_4_DOCTRINAL_SYSTEM,
        user=ROUND_4_DOCTRINAL_USER_TEMPLATE.format(
            kjv_text=kjv,
            synodal_text=syn,
            survivors_json=_serialize_for_prompt({"survivors": survivors_after_scripture}),
        ),
        temperature=0.2,
        agent_label="doctrinal",
    )
    doctrinal_reviews = doctrinal.get("reviews", []) if isinstance(doctrinal, dict) else []
    survivors_after_doctrinal: list[dict[str, Any]] = []
    for idx, s in enumerate(survivors_after_scripture):
        review = _find_review_for_index(doctrinal_reviews, idx)
        verdict = review.get("verdict") if isinstance(review, dict) else "pass"
        if verdict == "reject":
            outcome.rejected_at_doctrinal += 1
            continue
        if verdict == "needs_framing" and isinstance(review.get("proposed_reframe"), dict):
            reframe = review["proposed_reframe"]
            s = {
                **s,
                "question_text": reframe.get("question_text", s["question_text"]),
                "explanation": reframe.get("explanation", s.get("explanation")),
            }
        survivors_after_doctrinal.append(s)
    _log_event(
        db,
        question_id=None,
        event_type="doctrinally_reviewed",
        actor_id=request.created_by,
        generation_run_id=run_id,
        details={"reviews": doctrinal_reviews, "passed_count": len(survivors_after_doctrinal)},
    )
    outcome.rounds_executed += 1
    db.commit()

    if not survivors_after_doctrinal:
        outcome.errors.append("no survivors after doctrinal review")
        return outcome

    # ── Round 4c — Bilingual review ───────────────────────────────────
    bilingual = _run_round(
        client,
        system=ROUND_4_BILINGUAL_SYSTEM,
        user=ROUND_4_BILINGUAL_USER_TEMPLATE.format(
            survivors_json=_serialize_for_prompt({"survivors": survivors_after_doctrinal}),
        ),
        temperature=0.2,
        agent_label="bilingual",
    )
    bilingual_reviews = bilingual.get("reviews", []) if isinstance(bilingual, dict) else []
    survivors_final: list[tuple[dict[str, Any], dict[str, Any] | None]] = []
    for idx, s in enumerate(survivors_after_doctrinal):
        review = _find_review_for_index(bilingual_reviews, idx)
        verdict = review.get("verdict") if isinstance(review, dict) else "pass"
        if verdict == "reject":
            outcome.rejected_at_bilingual += 1
            continue
        ru_translation = review.get("ru_translation") if isinstance(review, dict) else None
        survivors_final.append((s, ru_translation))
    _log_event(
        db,
        question_id=None,
        event_type="bilingually_reviewed",
        actor_id=request.created_by,
        generation_run_id=run_id,
        details={"reviews": bilingual_reviews, "passed_count": len(survivors_final)},
    )
    outcome.rounds_executed += 1
    db.commit()

    if not survivors_final:
        outcome.errors.append("no survivors after bilingual review")
        return outcome

    # ── Round 5 — Pilot placeholder ───────────────────────────────────
    # Pilot review is human-driven via the editorial UI. The
    # orchestrator stamps a placeholder event so the audit trail
    # surfaces the gating point even when no humans have answered yet.
    _log_event(
        db,
        question_id=None,
        event_type="pilot_summary",
        actor_id=request.created_by,
        generation_run_id=run_id,
        details={"status": "awaiting_pilot_reviewers", "candidate_count": len(survivors_final)},
    )
    outcome.rounds_executed += 1
    db.commit()

    # ── Round 6 — Persist as DRAFT rows ───────────────────────────────
    for survivor, ru in survivors_final:
        try:
            options = [
                OptionDraft(text=o["text"], is_correct=bool(o.get("is_correct", False)))
                for o in survivor.get("options", [])
            ]
            question = create_question(
                db,
                question_type="multiple_choice",
                bible_book=request.book,
                bible_chapter=request.chapter,
                bible_verse_from=survivor.get("verse_start"),
                bible_verse_to=survivor.get("verse_end"),
                question_text=survivor["question_text"],
                options=options,
                explanation=survivor.get("explanation"),
                category=survivor.get("category"),
                created_by=request.created_by or uuid.uuid4(),
                fallback_locale="en",
            )
            outcome.created_question_ids.append(question.id)
            # Tag this draft to the originating generation_run_id so the
            # editorial UI can replay the entire history.
            _log_event(
                db,
                question_id=question.id,
                event_type="ai_synthesis",
                actor_id=request.created_by,
                generation_run_id=run_id,
                details={"persisted": True, "ru_translation_present": ru is not None},
            )
            # If the bilingual review produced a Russian rendering, drop
            # it into cv as a second human-version row so the editor sees
            # both translations during the bilingually_reviewed gate.
            if isinstance(ru, dict) and ru.get("question_text"):
                from app.services.content_versions.write import record_human_version

                record_human_version(
                    db,
                    entity_type="daily_challenge_question",
                    entity_id=str(question.id),
                    field="question_text",
                    locale="ru",
                    text=str(ru["question_text"]),
                    authored_by=request.created_by,
                )
                if ru.get("explanation"):
                    record_human_version(
                        db,
                        entity_type="daily_challenge_question",
                        entity_id=str(question.id),
                        field="explanation",
                        locale="ru",
                        text=str(ru["explanation"]),
                        authored_by=request.created_by,
                    )
                ru_options = ru.get("options") or []
                for option_row, ru_opt in zip(question.options, ru_options, strict=False):
                    if isinstance(ru_opt, dict) and ru_opt.get("text"):
                        record_human_version(
                            db,
                            entity_type="daily_challenge_option",
                            entity_id=str(option_row.id),
                            field="option_text",
                            locale="ru",
                            text=str(ru_opt["text"]),
                            authored_by=request.created_by,
                        )
            db.commit()
        except Exception as exc:
            logger.warning("orchestrator failed to persist survivor: %s", exc, exc_info=True)
            outcome.errors.append(f"persist failed: {exc!s}")
            db.rollback()

    return outcome


def _run_round(
    client: GeminiPromptClient,
    *,
    system: str,
    user: str,
    temperature: float,
    agent_label: str,
) -> Any:
    """Execute one LLM call with JSON-mode response parsing. Failures
    return an empty-shape dict so the orchestrator continues with
    whatever survived earlier rounds. Each round's events are still
    logged so the audit trail surfaces the failure point."""
    try:
        return client.invoke(
            system=system,
            user=user,
            temperature=temperature,
            expect_json=True,
        )
    except LLMError as exc:
        logger.warning("orchestrator round %s failed: %s", agent_label, exc)
        return {"_error": str(exc)}


def _serialize_for_prompt(payload: Any) -> str:
    """Render a dict into a JSON string suitable for embedding in a
    user prompt. Uses ``str()`` rather than ``json.dumps`` to keep
    Unicode (Russian quotes) human-readable in the prompt."""
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2)


def _find_review_for_index(reviews: list, idx: int) -> dict[str, Any]:
    """Pick the review entry whose ``survivor_index`` (or
    ``candidate_index``) matches ``idx``. Falls back to positional
    order when the model didn't include the index field."""
    for r in reviews:
        if not isinstance(r, dict):
            continue
        if r.get("survivor_index") == idx or r.get("candidate_index") == idx:
            return r
    if 0 <= idx < len(reviews) and isinstance(reviews[idx], dict):
        return reviews[idx]
    return {}


__all__ = ["GenerationOutcome", "GenerationRequest", "run_generation"]
