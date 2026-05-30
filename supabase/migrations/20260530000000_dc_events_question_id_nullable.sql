-- Phase 5cg — relax daily_challenge_question_events.question_id to
-- nullable so the AI generation orchestrator can log Round 1-3 events
-- (independent gen, cross-critique, synthesis) BEFORE any
-- ``daily_challenge_questions`` row exists. Once Round 6 persists the
-- surviving questions, the orchestrator logs additional events linking
-- them by question_id; the earlier events stay anchored only by
-- ``generation_run_id``.
--
-- The FK + ON DELETE CASCADE stay: if a question is later created and
-- then deleted, anything linked to it still cascades.

ALTER TABLE daily_challenge_question_events
    ALTER COLUMN question_id DROP NOT NULL;
