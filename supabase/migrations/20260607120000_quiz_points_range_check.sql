-- Tighten quiz_questions.points CHECK to match the API contract.
--
-- schemas/quiz.py QuizQuestionBase.points = Field(1, ge=1, le=100), but the DB
-- constraint (20260522004659) only enforced `points >= 0` with no upper bound
-- and a comment that wrongly claimed it mirrored `ge=0`. A direct / admin write
-- could persist 0 or > 100, violating the 4-way enum/range mirror. Verified
-- prod has 0 rows outside [1, 100] before tightening (min=1, max=20 over 86 rows).
ALTER TABLE public.quiz_questions DROP CONSTRAINT IF EXISTS quiz_questions_points_nonneg;
ALTER TABLE public.quiz_questions
  ADD CONSTRAINT quiz_questions_points_range CHECK (points >= 1 AND points <= 100);
COMMENT ON CONSTRAINT quiz_questions_points_range ON public.quiz_questions IS
  'Mirrors app.schemas.quiz.QuizQuestionBase.points Field(ge=1, le=100).';
