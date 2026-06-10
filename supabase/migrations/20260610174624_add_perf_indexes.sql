-- Performance indexes surfaced by the fat-course scale audit (240-chapter,
-- multi-hundred-student course). All three are additive and transparent to
-- application code — they only speed up existing read paths.
--
-- 1. quiz_attempts: _aggregate_quiz_results (teacher progress board + gradebook)
--    filters `quiz_id IN (...) AND completed_at IS NOT NULL` then windows by
--    (user_id, quiz_id). A partial composite on (quiz_id, user_id) over only
--    completed attempts serves the IN-list + the completed predicate directly,
--    instead of scanning ix_quiz_attempts_quiz_id and filtering rows out.
CREATE INDEX IF NOT EXISTS ix_quiz_attempts_quiz_user_completed
  ON public.quiz_attempts USING btree (quiz_id, user_id)
  WHERE completed_at IS NOT NULL;

-- 2. chapter_progress: _load_completed_progress filters
--    `chapter_id IN (...) AND completed = true [AND user_id IN (...)]`. A partial
--    composite on (chapter_id, user_id) over completed rows matches that access
--    pattern; ix_chapter_progress_chapter_id alone can't skip incomplete rows.
CREATE INDEX IF NOT EXISTS ix_chapter_progress_chapter_user_completed
  ON public.chapter_progress USING btree (chapter_id, user_id)
  WHERE completed;

-- 3. certificates: the SQLAlchemy model has declared ix_certificates_status
--    (status) for a while, but it was never migrated onto prod — a model<->prod
--    drift. Add it so the pending-certificate admin query (status = 'pending')
--    has its index and the schema matches the model's 4-way mirror.
CREATE INDEX IF NOT EXISTS ix_certificates_status
  ON public.certificates USING btree (status);
