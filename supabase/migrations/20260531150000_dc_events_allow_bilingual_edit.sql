-- Add 'bilingual_edit' to the daily_challenge_question_events
-- event_type CHECK constraint. The bilingual review UI (Sprint 7)
-- logs one of these per cv upsert so the editor's translation edits
-- show up in the audit trail next to status changes and AI rounds.

ALTER TABLE daily_challenge_question_events
    DROP CONSTRAINT IF EXISTS dc_q_events_type_check;

ALTER TABLE daily_challenge_question_events
    ADD CONSTRAINT dc_q_events_type_check
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
        'pilot_summary',
        'bilingual_edit'
    ));
