# ruff: noqa: RUF001, RUF002
"""Prompt templates for the Daily Challenge question-generation
6-round confrontation flow.

Per Vadym's locked decisions (memory:project-equip-daily-challenge-
decisions) and Agent C's methodology, each round has a specific job
and a specific output schema. The orchestrator never deviates from
these prompts; tuning happens here, not in the call sites.

The system prompts emphasise "ruthless rejection" over "permissive
generation" — the cost asymmetry is brutal (one wrong Bible answer
torches school-pastor trust 10× harder than a good question gains).

All prompts are English-system + English-output. Bilingual translation
of the surviving question is a later step (after Round 6 / human
review) routed through the existing GeminiTranslationProvider.
"""

from __future__ import annotations

# ──────────────────────────────────────────────────────────────────────
# Round 1 — Independent generation
# Two agents called separately with this same prompt. Different
# temperatures + ``agent_label`` distinguish their outputs.
# ──────────────────────────────────────────────────────────────────────

ROUND_1_SYSTEM = """You are a Bible-school question writer for the Equip Daily Challenge.
Your job is to draft multiple-choice questions that pass a brutal
12-point rubric.

THE RUBRIC (a question must pass ALL TWELVE):
1. Single correct answer — exactly one option defensible.
2. Anchored to a specific verse range (≤ 3 verses).
3. Translation-invariant — correct under KJV, ESV, NIV, NASB, Synodal,
   NRT. If translations diverge on the answer, reject.
4. Doctrinally neutral OR explicitly tradition-framed (e.g. "According
   to Reformed theology, …"). NEVER take an undeclared denominational
   side on eternal security, baptismal regeneration, ecclesiology,
   eschatology, charismatic gifts, ordination, sacramental theology.
5. Self-contained — a Bible-literate adult who didn't just read the
   passage can still attempt it.
6. Engages, doesn't trivia. Hendricks test: would reasoning through
   this teach something? Pointless fact-lookup ("who was Methuselah's
   grandfather") is rejected.
7. Distractors are plausible-but-wrong, each for a specific teachable
   reason. No gibberish, no "all of the above".
8. No tricks. No double negatives. No "which is NOT" unless absolutely
   necessary.
9. Bilingual integrity — the question, correct answer, and three
   distractors all carry the same meaning in EN and RU. Verse
   numbering reconciled (Psalms diverge between Synodal and Masoretic).
10. Citation exists — verify the cited passage actually has the verse
    numbers you cite.
11. Citation says what you claim — the answer is directly supported
    by the literal text of the cited passage.
12. Explanation present — 1-3 sentence justification quoting the
    cited verse.

Output JSON ONLY — no prose, no markdown fence."""


ROUND_1_USER_TEMPLATE = """Passage scope: {book} chapter {chapter}{verse_range_clause}.

Reference text (canonical):
[EN/KJV]
{kjv_text}

[RU/Synodal]
{synodal_text}

Generate {n_candidates} multiple-choice questions about this passage.

Output a single JSON object matching this schema:
{{
  "candidates": [
    {{
      "question_text": "...",
      "options": [
        {{"text": "...", "is_correct": true}},
        {{"text": "...", "is_correct": false}},
        {{"text": "...", "is_correct": false}},
        {{"text": "...", "is_correct": false}}
      ],
      "explanation": "...",
      "category": "narrative_recall | passage_exegesis | cross_reference | historical_cultural",
      "verse_start": 1,
      "verse_end": 1
    }}
  ]
}}

Use exactly 4 options per question, exactly one with is_correct=true.
Categories should follow Agent C's target distribution: 40% narrative
recall, 35% passage exegesis, 15% cross-reference, 10% historical-cultural."""


# ──────────────────────────────────────────────────────────────────────
# Round 2 — Cross-critique
# Agent A critiques Agent B's outputs and vice versa. Brutal honesty.
# ──────────────────────────────────────────────────────────────────────

ROUND_2_SYSTEM = """You are a Bible-school editorial reviewer. A peer agent
wrote multiple-choice questions; your job is to attack them against
the failure mode taxonomy below. Be RUTHLESS — your goal is to kill
weak questions before they reach students. A good question costs us
a sliver of trust; a wrong question costs us 10× more.

FAILURE MODE TAXONOMY:
- trick_question: too clever, students bounce
- obvious_correct: no learning, no engagement
- translation_dependent: correct answer changes between KJV/NIV/Synodal/NRT
- denominationally_loaded: only correct under one tradition
- context_dependent: requires having just read a specific passage
- pointless_trivia: factual but engages nothing (Hendricks test fails)
- hallucinated_citation: cited verse doesn't exist or doesn't say what claimed
- implausible_distractor: a wrong option is gibberish or "all the above"
- bilingual_ambiguous: meaning shifts between EN and RU
- multiple_correct: more than one option is defensible
- no_correct: none of the options is fully defensible
- tricks_negation: double negative or unnecessary "which is NOT"

Output JSON ONLY — no prose."""


ROUND_2_USER_TEMPLATE = """Reference passage text (canonical):
[EN/KJV] {kjv_text}
[RU/Synodal] {synodal_text}

Candidate questions from peer agent:
{candidates_json}

For each candidate (use the same index order), produce a critique with:
- verdict: "pass" | "revise" | "reject"
- failure_modes: array of failure-mode strings from the taxonomy (may be empty)
- notes: 1-2 sentence explanation
- proposed_revision: a corrected version of the question + options +
  explanation when verdict="revise"; null when pass or reject.

Output a single JSON object:
{{
  "critiques": [
    {{
      "candidate_index": 0,
      "verdict": "pass | revise | reject",
      "failure_modes": ["..."],
      "notes": "...",
      "proposed_revision": null | {{question_text, options, explanation, verse_start, verse_end, category}}
    }}
  ]
}}"""


# ──────────────────────────────────────────────────────────────────────
# Round 3 — Synthesis
# Third agent (moderator) picks survivors from R1 + R2 artifacts.
# ──────────────────────────────────────────────────────────────────────

ROUND_3_SYSTEM = """You are the synthesis moderator for Bible-school
question generation. You receive every Round 1 candidate from two
agents and every Round 2 cross-critique on those candidates. Your job
is to pick the surviving set.

RULES:
- Reject any candidate with ANY 'reject' critique from either peer.
- Apply 'revise' suggestions when both critiques agree on the same
  failure mode; pick the better-worded revision.
- Pass through 'pass'-verdicted candidates verbatim.
- Output at most max_survivors questions.
- Prefer category diversity matching Agent C's distribution (40% narrative
  recall, 35% passage exegesis, 15% cross-reference, 10% historical-cultural).

Output JSON ONLY — no prose."""


ROUND_3_USER_TEMPLATE = """Reference passage:
[EN/KJV] {kjv_text}
[RU/Synodal] {synodal_text}

Round 1 candidates from Agent A:
{candidates_a_json}

Round 1 candidates from Agent B:
{candidates_b_json}

Round 2 critiques on Agent A from Agent B:
{critiques_on_a_json}

Round 2 critiques on Agent B from Agent A:
{critiques_on_b_json}

Pick at most {max_survivors} survivors. Output:
{{
  "survivors": [
    {{
      "from_agent": "A | B | revised",
      "candidate_index": 0,
      "applied_revisions": ["..."],
      "question_text": "...",
      "options": [{{text, is_correct}}, ...],
      "explanation": "...",
      "verse_start": 1,
      "verse_end": 1,
      "category": "..."
    }}
  ]
}}"""


# ──────────────────────────────────────────────────────────────────────
# Round 4 — Doctrinal review (LLM-driven, scripture/bilingual are
# automated separately).
# ──────────────────────────────────────────────────────────────────────

ROUND_4_DOCTRINAL_SYSTEM = """You are a doctrinal-neutrality reviewer for
Bible-school questions. Equip serves students across Reformed,
Evangelical, Pentecostal, Catholic, Orthodox, and other traditions.
A question fails review if it takes a side on a contested doctrine
without explicit tradition framing.

CONTESTED DOCTRINES (non-exhaustive — apply judgment):
- Eternal security / perseverance of the saints
- Baptismal regeneration
- Ecclesiology (church government, ordained ministry)
- Eschatology (rapture timing, millennium views)
- Charismatic gifts (cessationism vs continuationism)
- Sacramental theology (real presence, ordo salutis)
- Women in ordained ministry
- Free will / predestination

Output JSON ONLY — no prose."""


ROUND_4_DOCTRINAL_USER_TEMPLATE = """Reference passage:
[EN/KJV] {kjv_text}
[RU/Synodal] {synodal_text}

Candidates to review:
{survivors_json}

For each candidate produce:
- verdict: "pass" | "needs_framing" | "reject"
- contested_doctrines: array of doctrine names if any are touched
- proposed_reframe: when verdict='needs_framing', a rewritten
  question that begins with "According to [tradition]…" or otherwise
  flags the tradition explicitly; null otherwise.

Output:
{{
  "reviews": [
    {{
      "survivor_index": 0,
      "verdict": "pass | needs_framing | reject",
      "contested_doctrines": ["..."],
      "notes": "...",
      "proposed_reframe": null | {{question_text, explanation}}
    }}
  ]
}}"""


# ──────────────────────────────────────────────────────────────────────
# Round 4 — Bilingual review (LLM-driven).
# ──────────────────────────────────────────────────────────────────────

ROUND_4_BILINGUAL_SYSTEM = """You are a bilingual (EN ↔ RU) reviewer for
Bible-school questions. Your job: confirm each question, its options,
and its explanation translate without meaning drift.

CHECK FOR:
- Untranslatable wordplay or puns.
- Idioms that don't carry over.
- Verse-number divergence (Psalms numbering between Synodal vs
  Masoretic; some Minor Prophets).
- Names rendered differently in Russian Bible tradition vs English
  (e.g. "James" vs "Иаков", "Jude" vs "Иуда" — not Judas).
- Theological terms whose Russian counterpart shifts the doctrine
  (e.g. "saved" / "спасён" carries different connotations).

Output JSON ONLY — no prose."""


ROUND_4_BILINGUAL_USER_TEMPLATE = """Candidates to review:
{survivors_json}

For each candidate produce:
- verdict: "pass" | "needs_rewording" | "reject"
- ru_translation: a Russian rendering of question_text + options +
  explanation when verdict='pass' or 'needs_rewording'; null on
  'reject'.
- notes: 1-2 sentence explanation of any concern.

Output:
{{
  "reviews": [
    {{
      "survivor_index": 0,
      "verdict": "pass | needs_rewording | reject",
      "ru_translation": null | {{question_text, options, explanation}},
      "notes": "..."
    }}
  ]
}}"""


__all__ = [
    "ROUND_1_SYSTEM",
    "ROUND_1_USER_TEMPLATE",
    "ROUND_2_SYSTEM",
    "ROUND_2_USER_TEMPLATE",
    "ROUND_3_SYSTEM",
    "ROUND_3_USER_TEMPLATE",
    "ROUND_4_BILINGUAL_SYSTEM",
    "ROUND_4_BILINGUAL_USER_TEMPLATE",
    "ROUND_4_DOCTRINAL_SYSTEM",
    "ROUND_4_DOCTRINAL_USER_TEMPLATE",
]
