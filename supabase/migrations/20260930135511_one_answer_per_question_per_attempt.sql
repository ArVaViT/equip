-- One answer per question per attempt.
--
-- `persist_answers` scored every answer it was given, and nothing below it
-- said a question could be answered only once: the right option sent five
-- times earned five times its points, past the maximum, and a pass
-- (found 2026-09-30; production had no such rows — 0 duplicate pairs in
-- 127 answers). The request schema and the service now refuse it; this
-- makes the database refuse it too.
--
-- The existing index on the same columns becomes the unique one, so no
-- extra index is added.

-- One DO block, so the check, the DROP and the CREATE are a single
-- statement: however the file is run (one transaction or statement by
-- statement, stopping on errors or not), a failure leaves the old index in
-- place instead of a table with none.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM public.quiz_answers
    GROUP BY attempt_id, question_id
    HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION 'quiz_answers has duplicate (attempt_id, question_id) pairs; resolve them before this migration';
  END IF;
  DROP INDEX IF EXISTS public.ix_quiz_answers_attempt_question;
  CREATE UNIQUE INDEX ix_quiz_answers_attempt_question
    ON public.quiz_answers USING btree (attempt_id, question_id);
END
$$;
