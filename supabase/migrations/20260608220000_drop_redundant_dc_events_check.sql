-- Drop the redundant, STALE event_type CHECK on daily_challenge_question_events.
--
-- The table carries two overlapping CHECKs: the older
-- ``daily_challenge_question_events_event_type_check`` (12 values, missing
-- ``bilingual_edit``) and the newer ``dc_q_events_type_check`` (13 values,
-- the superset the SQLAlchemy model declares). Both must pass, so the narrower
-- one silently REJECTS a ``bilingual_edit`` event — which the bilingual-review
-- code (services/daily_challenge/admin.py) actually writes. On prod this fails
-- the INSERT; SQLite tests miss it because the model only declares the 13-value
-- constraint. Drop the stale one so prod matches the model (4-way mirror).
ALTER TABLE public.daily_challenge_question_events
    DROP CONSTRAINT IF EXISTS daily_challenge_question_events_event_type_check;
