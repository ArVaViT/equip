-- Defence-in-depth numeric-range CHECKs from the 2026-05-21 DB audit
-- (MEDIUM #21-#26). The backend connects as the ``postgres`` role
-- (RLS-bypassed); Pydantic enforces these ranges at the API surface
-- via ``Field(ge=..., le=...)``, but a direct SQL write from the
-- Supabase dashboard, a migration script, or a service-role caller
-- trusts Pydantic as the only gate. CHECK constraints close the gap.
--
-- Verified zero existing rows violate any of these on 2026-05-21
-- (queried via MCP before authoring this migration).

ALTER TABLE public.quizzes
  ADD CONSTRAINT quizzes_passing_score_range
  CHECK (passing_score BETWEEN 0 AND 100);
COMMENT ON CONSTRAINT quizzes_passing_score_range ON public.quizzes IS
  'Mirrors app.schemas.quiz.QuizBase.passing_score Field(ge=0, le=100).';

ALTER TABLE public.quizzes
  ADD CONSTRAINT quizzes_max_attempts_positive
  CHECK (max_attempts IS NULL OR max_attempts > 0);
COMMENT ON CONSTRAINT quizzes_max_attempts_positive ON public.quizzes IS
  'A 0 here would deny every attempt silently — surface as a CHECK error.';

ALTER TABLE public.quiz_questions
  ADD CONSTRAINT quiz_questions_points_nonneg
  CHECK (points >= 0);
COMMENT ON CONSTRAINT quiz_questions_points_nonneg ON public.quiz_questions IS
  'Mirrors app.schemas.quiz.QuizQuestionBase.points Field(ge=0).';

ALTER TABLE public.quiz_questions
  ADD CONSTRAINT quiz_questions_min_words_nonneg
  CHECK (min_words IS NULL OR min_words >= 0);

ALTER TABLE public.quiz_attempts
  ADD CONSTRAINT quiz_attempts_score_nonneg
  CHECK (score IS NULL OR score >= 0);

ALTER TABLE public.quiz_attempts
  ADD CONSTRAINT quiz_attempts_max_score_nonneg
  CHECK (max_score IS NULL OR max_score >= 0);

ALTER TABLE public.assignments
  ADD CONSTRAINT assignments_max_score_positive
  CHECK (max_score > 0);
COMMENT ON CONSTRAINT assignments_max_score_positive ON public.assignments IS
  'Mirrors app.schemas.assignment.AssignmentCreate.max_score Field(ge=1).';

ALTER TABLE public.assignment_submissions
  ADD CONSTRAINT assignment_submissions_grade_nonneg
  CHECK (grade IS NULL OR grade >= 0);
COMMENT ON CONSTRAINT assignment_submissions_grade_nonneg ON public.assignment_submissions IS
  'Cross-table grade <= max_score is enforced in the route + a Python clamp in grade_calculator.';

ALTER TABLE public.enrollments
  ADD CONSTRAINT enrollments_progress_range
  CHECK (progress BETWEEN 0 AND 100);
