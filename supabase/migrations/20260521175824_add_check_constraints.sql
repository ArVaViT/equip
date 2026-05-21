-- Supabase migration: add_check_constraints
--
-- Defence-in-depth: Pydantic ``Literal`` types are the API contract
-- for enum-shaped string columns. The backend connects as the
-- ``postgres`` role which bypasses RLS, so a direct SQL write
-- (dashboard, migration script, service-role caller) trusts Pydantic
-- as the only validator. CHECK constraints close that gap.
--
-- Audit 2026-05-21 verified every column already conforms to the
-- proposed value set, AND that all but one of the constraints we
-- thought were missing actually already exist under different names
-- (chk_courses_status, courses_access_mode_check, etc.). Only
-- ``quizzes.quiz_type`` is genuinely missing a CHECK on the DB side
-- though Pydantic has enforced ``Literal["quiz","exam"]`` since the
-- schema was introduced.
--
-- Existing CHECKs verified present and equivalent to the Pydantic
-- contract (audited 2026-05-21):
--   * chk_courses_status              status IN ('draft','published')
--   * courses_access_mode_check       access_mode IN ('public','institute')
--   * chapters_chapter_type_check     ('reading','quiz','exam','assignment')
--   * chapter_blocks_block_type_check ('text','quiz','assignment','file')
--   * cohorts_status_check            ('upcoming','active','completed','archived')
--   * assignment_submissions_status_check ('submitted','graded','returned')
-- (The chapter_blocks CHECK is wider than the Pydantic schema
-- ``Literal["text","file"]`` — that's a tightening discussion for
-- another migration once we confirm zero ``quiz``/``assignment`` rows
-- in chapter_blocks.)

ALTER TABLE public.quizzes
  ADD CONSTRAINT quizzes_quiz_type_check
  CHECK (quiz_type IN ('quiz', 'exam'));

COMMENT ON CONSTRAINT quizzes_quiz_type_check ON public.quizzes IS
  'Mirrors app.schemas.quiz.QuizBase.quiz_type Literal["quiz","exam"].';
