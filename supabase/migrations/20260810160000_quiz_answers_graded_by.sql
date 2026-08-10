-- Who marked this answer.
--
-- An essay or short-answer score is a person's judgement, and it decides a
-- student's grade: `recompute_attempt_grade` re-aggregates the attempt from
-- these rows, the attempt feeds the course grade, and the course grade goes on
-- a certificate. Every other link in that chain records its author —
-- `assignment_submissions.graded_by`, `student_grades.graded_by`,
-- `chapter_progress.completed_by`, and since this week the audit log for
-- exemptions and manual completions. This one did not.
--
-- The gap was invisible because the information existed and was thrown away:
-- the grading route already tags its throughput metric with the teacher's id,
-- so Datadog could answer "who marked this" and the database could not. A
-- disputed grade is exactly the case where a metrics dashboard is the wrong
-- place to look.
--
-- Nullable, and nothing is backfilled: answers marked before this were marked
-- by someone the platform did not record. NULL says that. Auto-marked answers
-- keep NULL for a different and equally true reason — nobody marked them.

ALTER TABLE public.quiz_answers
    ADD COLUMN graded_by UUID REFERENCES public.profiles(id) ON DELETE SET NULL;

-- "Show me everything this teacher marked" — the question a director asks when
-- a grade is disputed, and the only query this column exists to serve.
CREATE INDEX ix_quiz_answers_graded_by ON public.quiz_answers (graded_by) WHERE graded_by IS NOT NULL;
