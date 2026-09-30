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

DROP INDEX IF EXISTS public.ix_quiz_answers_attempt_question;
CREATE UNIQUE INDEX IF NOT EXISTS ix_quiz_answers_attempt_question
  ON public.quiz_answers USING btree (attempt_id, question_id);
