-- Supabase migration: missing_fk_indexes_v2
-- Version: 20260603140100
--
-- Follow-up to 20260521230202_missing_fk_indexes.sql. Tables added
-- after that batch (content_versions, daily_challenge_*, the new
-- translation_jobs) carry FK constraints without covering indexes,
-- per Supabase performance advisor 0001.
--
-- Same opinion as the prior migration: at pre-pilot row counts the
-- planner picks seq_scan and the indexes look unused — but every FK
-- without an index is a 100ms ceiling waiting to break the moment
-- the parent table hits 10k+ rows. Each index here is a few KB on
-- disk; cheap insurance.

-- content_versions — authored_by + superseded_by are user FKs hit by
-- the editorial audit views.
CREATE INDEX IF NOT EXISTS ix_content_versions_authored_by
    ON content_versions(authored_by)
    WHERE authored_by IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_content_versions_superseded_by
    ON content_versions(superseded_by)
    WHERE superseded_by IS NOT NULL;

-- daily_challenge_attempts — selected_option_id is what answer-correctness
-- joins on at result-render time.
CREATE INDEX IF NOT EXISTS ix_dc_attempts_selected_option_id
    ON daily_challenge_attempts(selected_option_id)
    WHERE selected_option_id IS NOT NULL;

-- daily_challenge_question_events — actor_id powers the editorial
-- audit-log "what did X do" filter.
CREATE INDEX IF NOT EXISTS ix_dc_q_events_actor_id
    ON daily_challenge_question_events(actor_id)
    WHERE actor_id IS NOT NULL;

-- daily_challenge_questions — created_by / published_by / rejected_by
-- all power the editorial dashboards (the questions tab filters by
-- "who wrote this", "who shipped this", "who pulled this").
CREATE INDEX IF NOT EXISTS ix_dc_questions_created_by
    ON daily_challenge_questions(created_by)
    WHERE created_by IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_dc_questions_published_by
    ON daily_challenge_questions(published_by)
    WHERE published_by IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_dc_questions_rejected_by
    ON daily_challenge_questions(rejected_by)
    WHERE rejected_by IS NOT NULL;

-- daily_challenge_schedule — scheduled_by powers the same editorial
-- audit cuts.
CREATE INDEX IF NOT EXISTS ix_dc_schedule_scheduled_by
    ON daily_challenge_schedule(scheduled_by)
    WHERE scheduled_by IS NOT NULL;

-- translation_jobs — requested_by is filtered when an admin views
-- "translations I queued".
CREATE INDEX IF NOT EXISTS ix_translation_jobs_requested_by
    ON translation_jobs(requested_by)
    WHERE requested_by IS NOT NULL;
