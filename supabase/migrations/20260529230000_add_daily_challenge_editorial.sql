-- =====================================================================
-- Phase 5c Sprint 3 — Daily Challenge editorial pipeline tables.
--
-- Two tables that back the 5-stage editorial review and the (future)
-- 6-round AI generation flow:
--
--   * daily_challenge_question_events: append-only audit trail of
--     every stage transition + every AI-generation round artifact.
--     Each row carries a JSONB ``details`` payload so we can add new
--     event types without DDL churn — the schema is the index, the
--     details are the contents.
--
--   * daily_challenge_pilot_reviews: Stage 5 pilot answers + ratings.
--     One row per reviewer-per-question. The aggregate threshold
--     (≥80% correct + ≥3.5/5 mean engagement with n≥5) is computed
--     in the service layer, not persisted as a denormalised column,
--     because the threshold is an editorial knob we may tune.
--
-- The 6-round AI generation flow itself (independent gen, cross-
-- critique, synthesis, scripture/doctrine/bilingual validation, pilot,
-- publish) is service-layer code that lands later. This migration
-- ships only the storage so the AI orchestrator can write to it
-- without a migration block.
-- =====================================================================

-- ---------------------------------------------------------------------
-- daily_challenge_question_events
-- ---------------------------------------------------------------------

CREATE TABLE daily_challenge_question_events (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id         UUID NOT NULL
                            REFERENCES daily_challenge_questions(id)
                            ON DELETE CASCADE,

    -- High-level event type. The set covers both editorial transitions
    -- (status change, rejection, publishing, scheduling) AND AI
    -- generation rounds (independent generation, cross-critique,
    -- synthesis, scripture/doctrine/bilingual validation, pilot
    -- review aggregate). Extending the set is an additive migration
    -- (drop the CHECK + re-add with new value), so the cost of being
    -- conservative here is low.
    event_type          TEXT NOT NULL
                            CHECK (event_type IN (
                                'status_change',
                                'rejected',
                                'published',
                                'scheduled',
                                'unscheduled',
                                'ai_generated',
                                'ai_critique',
                                'ai_synthesis',
                                'scripture_validated',
                                'doctrinally_reviewed',
                                'bilingually_reviewed',
                                'pilot_summary'
                            )),

    -- ``generation_run_id`` groups every AI artifact that came out of
    -- one orchestrator invocation. NULL for purely-editorial events
    -- (status_change, scheduled, etc.). Lets the editorial UI walk
    -- "show me everything from this generation run."
    generation_run_id   UUID,

    -- Who triggered the event. NULL when an automated AI step ran
    -- under service_role with no human actor.
    actor_id            UUID REFERENCES profiles(id) ON DELETE SET NULL,

    -- The free-form payload. Schema lives in the service layer per
    -- event_type — e.g.:
    --   status_change: {"from": "draft", "to": "scripture_validated"}
    --   rejected: {"reason": "answer ambiguous in NIV"}
    --   ai_critique: {"reviewer_agent": "B", "verdict": "reject",
    --                  "failure_modes": ["translation_dependent"], ...}
    --   pilot_summary: {"n": 5, "correct_rate": 0.80, "engagement": 4.0}
    details             JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- "Walk the timeline of one question" — the editorial UI lands on
-- this index for every audit-trail view.
CREATE INDEX ix_dc_q_events_question_created
    ON daily_challenge_question_events (question_id, created_at);

-- "Walk every event from one AI generation run" — used by the
-- orchestrator to assemble the round-N → round-N+1 input from the
-- previous round's artifacts. Partial keeps the index hot on AI
-- events only.
CREATE INDEX ix_dc_q_events_generation_run
    ON daily_challenge_question_events (generation_run_id, created_at)
    WHERE generation_run_id IS NOT NULL;

-- ---------------------------------------------------------------------
-- daily_challenge_pilot_reviews
-- ---------------------------------------------------------------------

CREATE TABLE daily_challenge_pilot_reviews (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id         UUID NOT NULL
                            REFERENCES daily_challenge_questions(id)
                            ON DELETE CASCADE,
    reviewer_id         UUID NOT NULL
                            REFERENCES profiles(id)
                            ON DELETE SET NULL,

    -- Cold-answer test: did the reviewer get it right without seeing
    -- the answer key first?
    answered_correctly  BOOLEAN NOT NULL,

    -- Engagement Likert 1-5 ("how worth-reading was this question?").
    engagement_rating   INT NOT NULL CHECK (engagement_rating BETWEEN 1 AND 5),

    -- Optional reviewer note. The aggregate threshold is computed in
    -- the service layer; this column is for editor-readable nuance.
    notes               TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- One review per (question, reviewer). A reviewer who wants to
    -- update their take overwrites the previous row in the service
    -- layer; the DB enforces uniqueness.
    UNIQUE (question_id, reviewer_id)
);

CREATE INDEX ix_dc_pilot_reviews_question
    ON daily_challenge_pilot_reviews (question_id);

-- =====================================================================
-- Row-Level Security
-- =====================================================================

ALTER TABLE daily_challenge_question_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_challenge_pilot_reviews    ENABLE ROW LEVEL SECURITY;

-- Editorial role (teacher + admin) sees everything. Students never
-- need to see the editorial audit trail or the pilot reviews — both
-- contain the answer-key reasoning and would leak the spec of the
-- correct option.

CREATE POLICY dc_q_events_select_editorial ON daily_challenge_question_events
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM profiles p
             WHERE p.id = (SELECT auth.uid())
               AND p.role IN ('teacher', 'admin')
        )
    );

CREATE POLICY dc_pilot_reviews_select_editorial ON daily_challenge_pilot_reviews
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM profiles p
             WHERE p.id = (SELECT auth.uid())
               AND p.role IN ('teacher', 'admin')
        )
    );

-- All writes through service_role.
REVOKE INSERT, UPDATE, DELETE ON daily_challenge_question_events FROM authenticated, anon;
REVOKE INSERT, UPDATE, DELETE ON daily_challenge_pilot_reviews    FROM authenticated, anon;
