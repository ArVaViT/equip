-- A course's insides are read through the API.
--
-- Eleven SELECT policies opened the tables of a course's structure to
-- anyone signed in — any student of any school, and registration is open:
--
--   chapters_select_public, modules_select_public       USING (true)
--   blocks_select_all (chapter_blocks), quizzes_select_all,
--   quiz_questions_select_all, quiz_options_select_all,
--   assignments_select_all, prereqs_select_all
--   (course_prerequisites), announcements_select_authenticated,
--   reviews_select_all (course_reviews)                 USING (auth.uid() IS NOT NULL)
--   cohort_courses_select_all                           USING (true), no TO — anon too
--
-- (`quiz_options` had the policy but never the grant, so it was already
-- closed; the policy goes with the rest so nobody grants it back open.)
--
-- With the publishable key and their own session, a person could read
-- through PostgREST what the API hides from them: the module and lesson
-- titles of other schools' closed courses and of drafts, the storage paths
-- of their files, the quizzes and assignments of courses they are not in,
-- who reviewed what (security review, 2026-10-15). The texts themselves
-- live in `content_versions`, which no client may read, so it was the
-- outline that leaked, not the lessons.
--
-- No client reads any of these tables. The frontend queries `profiles`,
-- `courses` and `enrollments` directly and nothing else; every other read
-- goes through the backend, which connects as the table owner and answers
-- to `course_a_reader_may_see` and the ownership checks, not to these
-- policies. No other policy reads these tables either. So the policies are
-- dropped rather than rewritten: RLS stays on, and with no policy for a
-- client role the answer is no rows — the same deliberate deny-all as the
-- other backend-only tables (`rls_enabled_no_policy` in
-- `.github/scripts/supabase_advisors.py`).
--
-- If a client ever needs to read one of them directly, the policy to write
-- is the course's own visibility — `EXISTS (SELECT 1 FROM public.courses c
-- WHERE c.id = <table>.course_id)`, which inherits `courses_select_published`
-- — not "signed in".

DROP POLICY IF EXISTS chapters_select_public ON public.chapters;
DROP POLICY IF EXISTS modules_select_public ON public.modules;
DROP POLICY IF EXISTS blocks_select_all ON public.chapter_blocks;
DROP POLICY IF EXISTS quiz_questions_select_all ON public.quiz_questions;
DROP POLICY IF EXISTS announcements_select_authenticated ON public.announcements;
DROP POLICY IF EXISTS reviews_select_all ON public.course_reviews;
DROP POLICY IF EXISTS cohort_courses_select_all ON public.cohort_courses;
DROP POLICY IF EXISTS quizzes_select_all ON public.quizzes;
DROP POLICY IF EXISTS quiz_options_select_all ON public.quiz_options;
DROP POLICY IF EXISTS assignments_select_all ON public.assignments;
DROP POLICY IF EXISTS prereqs_select_all ON public.course_prerequisites;
