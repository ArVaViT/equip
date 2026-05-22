-- Performance pass surfaced by the 2026-05-13 DB audit. Three categories:
--
-- 1. Add a partial composite index for the most-called app query (the
--    public courses catalog) so the planner can satisfy both the soft-delete
--    filter and the ORDER BY in one index walk.
-- 2. Drop three left-prefix-redundant indexes — each is fully covered by an
--    existing UNIQUE composite whose first column matches. Safe to drop;
--    saves write overhead on inserts/updates.
-- 3. Add a composite index supporting the quiz-grading hot path so the
--    answer lookup by (attempt_id, question_id) doesn't fall back to
--    seq-scan as the table grows past planner's seq-scan crossover.
-- 4. Tune autovacuum thresholds on three small but write-active tables
--    (profiles, quiz_attempts, quiz_answers) so stats refresh well before
--    the default 50-row threshold kicks in. Without this, profiles already
--    sits at 25 dead / 13 live tuples with last_autovacuum NULL — fine now,
--    but bad as user count grows.
--
-- Pre-flight checked against pg_stat_user_indexes / pg_stat_statements
-- on 2026-05-13. No data-violation risk (no UNIQUE constraints added,
-- no FK-supporting indexes dropped).


-- 1. Public courses catalog ----------------------------------------------
-- Query shape (catalog.py):
--   SELECT * FROM courses
--   WHERE status = $1 AND deleted_at IS NULL
--   ORDER BY created_at DESC LIMIT/OFFSET
-- Existing ix_courses_status only covers the filter, not the sort, and
-- includes soft-deleted rows. The partial + DESC ordering lets the planner
-- skip both the deleted_at filter AND the sort step.
CREATE INDEX IF NOT EXISTS ix_courses_status_created_at
  ON public.courses (status, created_at DESC)
  WHERE deleted_at IS NULL;

DROP INDEX IF EXISTS public.ix_courses_status;


-- 2. Redundant left-prefix indexes ---------------------------------------
-- Each of these is fully covered by an existing UNIQUE composite whose
-- first column matches. Any query filtering by the first column alone
-- still uses the UNIQUE index's leftmost column at no cost.
DROP INDEX IF EXISTS public.ix_enrollments_user_id;          -- covered by enrollments_user_id_course_id_key
DROP INDEX IF EXISTS public.ix_chapter_progress_user_id;     -- covered by chapter_progress_user_id_chapter_id_key
DROP INDEX IF EXISTS public.idx_certificates_user_id;        -- covered by certificates_user_course_unique


-- 3. Quiz-grading hot path ----------------------------------------------
-- Query shape: lookup answers for a specific attempt's specific question
-- during grading + feedback. (attempt_id, question_id) composite lets
-- the lookup hit one row directly instead of scanning all answers for an
-- attempt then filtering by question.
CREATE INDEX IF NOT EXISTS ix_quiz_answers_attempt_question
  ON public.quiz_answers (attempt_id, question_id);

DROP INDEX IF EXISTS public.idx_quiz_answers_attempt_id;     -- left-prefix covered by new composite


-- 4. Autovacuum tuning for small write-active tables ---------------------
-- Default autovacuum threshold is 50 rows. profiles + quiz_attempts +
-- quiz_answers all live below that today, so autovacuum never fires and
-- planner stats can drift stale as our few rows get updated repeatedly.
ALTER TABLE public.profiles      SET (autovacuum_vacuum_threshold = 25,
                                       autovacuum_analyze_threshold = 25);
ALTER TABLE public.quiz_attempts SET (autovacuum_vacuum_threshold = 10,
                                       autovacuum_analyze_threshold = 10);
ALTER TABLE public.quiz_answers  SET (autovacuum_vacuum_threshold = 25,
                                       autovacuum_analyze_threshold = 25);
