-- Add an explicit ``graded_at`` timestamp to ``quiz_answers`` so the
-- teacher-pending grading queue stops relying on a fragile
-- ``(grader_comment IS NULL AND points_earned = 0)`` heuristic.
--
-- Why this exists
-- ---------------
-- Open-ended answers (``essay`` / ``short_answer``) are submitted with
-- ``points_earned = 0`` + ``grader_comment IS NULL`` and stay that way
-- until a teacher hits PATCH /api/v1/quizzes/answers/{id}. The pending
-- queue at GET /quizzes/{id}/pending-answers filtered on those two
-- columns to spot un-graded rows. That works for the common case
-- ("teacher awarded N>0 points" or "teacher left a comment") but
-- silently breaks when a teacher legitimately grades an answer as
-- 0 points with no feedback — the row stays in the queue forever and
-- next page-load shows it back as if untouched.
--
-- ``graded_at`` is the unambiguous "this has been touched by a grader"
-- signal. Backend now treats ``graded_at IS NOT NULL`` as the
-- source of truth for "this open-ended answer was graded".
--
-- Backfill semantics
-- ------------------
-- 1. Auto-graded answers (multiple_choice / true_false) are scored
--    deterministically at submit time — they have no "pending" state.
--    Stamp them with NOW() so the column reads as "graded".
-- 2. Open-ended answers (essay / short_answer) keep ``graded_at`` NULL
--    when their state still looks pending (the old heuristic), and
--    get NOW() when anything suggests a teacher already acted (any
--    points awarded, or a comment was left). This preserves the
--    behaviour callers see today: nothing newly appears in or vanishes
--    from the queue on deploy.

ALTER TABLE public.quiz_answers
  ADD COLUMN IF NOT EXISTS graded_at timestamptz;

-- Auto-graded answers: always stamp (they were "graded" at submit).
UPDATE public.quiz_answers AS qa
  SET graded_at = NOW()
  WHERE graded_at IS NULL
    AND EXISTS (
      SELECT 1 FROM public.quiz_questions q
      WHERE q.id = qa.question_id
        AND q.question_type IN ('multiple_choice', 'true_false')
    );

-- Open-ended answers: stamp only the ones the old heuristic already
-- treated as "graded" (any points or any comment present).
UPDATE public.quiz_answers
  SET graded_at = NOW()
  WHERE graded_at IS NULL
    AND (grader_comment IS NOT NULL OR points_earned <> 0);

CREATE INDEX IF NOT EXISTS ix_quiz_answers_graded_at
  ON public.quiz_answers (graded_at);
