-- Tighten teacher-write RLS to match server-only writes (security audit
-- 2026-05-21, HIGH #10 + #11). All ``*_insert_teacher`` /
-- ``*_update_teacher`` / ``*_delete_teacher`` policies on these tables
-- only checked the caller's role — not whether the caller owns the
-- target course. A teacher could PostgREST-write content into ANY
-- other teacher's course tree, bypassing every ``verify_course_owner``
-- check in the backend.
--
-- Two options the audit suggested:
--   (a) add ownership-via-join WITH CHECK on each policy
--   (b) drop + REVOKE, server is the only writer
--
-- We pick (b): the backend ALWAYS writes via SQLAlchemy on the
-- pooler connection (postgres role, RLS-bypassing), and frontend
-- audit confirms zero ``supabase.from(...).insert/update/delete``
-- calls against these tables. The role-only policies were dead
-- weight that opened a real PostgREST attack vector.
--
-- Same treatment for ``cohort_courses_*_admin``: admin-only check,
-- no membership/ownership constraint, server-mediated in practice.
--
-- SELECT policies are KEPT — those are how the admin dashboard
-- counts and a handful of read paths work via PostgREST.

-- announcements
DROP POLICY IF EXISTS announcements_insert_teacher ON public.announcements;
DROP POLICY IF EXISTS announcements_update_own ON public.announcements;
DROP POLICY IF EXISTS announcements_delete_own ON public.announcements;
REVOKE INSERT, UPDATE, DELETE ON public.announcements FROM authenticated, anon;

-- assignments
DROP POLICY IF EXISTS assignments_insert_teacher ON public.assignments;
DROP POLICY IF EXISTS assignments_update_teacher ON public.assignments;
DROP POLICY IF EXISTS assignments_delete_teacher ON public.assignments;
REVOKE INSERT, UPDATE, DELETE ON public.assignments FROM authenticated, anon;

-- chapter_blocks
DROP POLICY IF EXISTS blocks_insert_teacher ON public.chapter_blocks;
DROP POLICY IF EXISTS blocks_update_teacher ON public.chapter_blocks;
DROP POLICY IF EXISTS blocks_delete_teacher ON public.chapter_blocks;
REVOKE INSERT, UPDATE, DELETE ON public.chapter_blocks FROM authenticated, anon;

-- chapters
DROP POLICY IF EXISTS chapters_insert_teacher ON public.chapters;
DROP POLICY IF EXISTS chapters_update_teacher ON public.chapters;
DROP POLICY IF EXISTS chapters_delete_teacher ON public.chapters;
REVOKE INSERT, UPDATE, DELETE ON public.chapters FROM authenticated, anon;

-- modules
DROP POLICY IF EXISTS modules_insert_teacher ON public.modules;
DROP POLICY IF EXISTS modules_update_teacher ON public.modules;
DROP POLICY IF EXISTS modules_delete_teacher ON public.modules;
REVOKE INSERT, UPDATE, DELETE ON public.modules FROM authenticated, anon;

-- quiz_questions
DROP POLICY IF EXISTS quiz_questions_insert_teacher ON public.quiz_questions;
DROP POLICY IF EXISTS quiz_questions_update_teacher ON public.quiz_questions;
DROP POLICY IF EXISTS quiz_questions_delete_teacher ON public.quiz_questions;
REVOKE INSERT, UPDATE, DELETE ON public.quiz_questions FROM authenticated, anon;

-- quiz_options
DROP POLICY IF EXISTS quiz_options_insert_teacher ON public.quiz_options;
DROP POLICY IF EXISTS quiz_options_update_teacher ON public.quiz_options;
DROP POLICY IF EXISTS quiz_options_delete_teacher ON public.quiz_options;
REVOKE INSERT, UPDATE, DELETE ON public.quiz_options FROM authenticated, anon;

-- student_grades
DROP POLICY IF EXISTS student_grades_insert_teacher ON public.student_grades;
DROP POLICY IF EXISTS student_grades_update_teacher ON public.student_grades;
DROP POLICY IF EXISTS student_grades_delete_teacher ON public.student_grades;
REVOKE INSERT, UPDATE, DELETE ON public.student_grades FROM authenticated, anon;

-- content_translations
DROP POLICY IF EXISTS content_translations_insert_teacher ON public.content_translations;
DROP POLICY IF EXISTS content_translations_update_teacher ON public.content_translations;
DROP POLICY IF EXISTS content_translations_delete_teacher ON public.content_translations;
REVOKE INSERT, UPDATE, DELETE ON public.content_translations FROM authenticated, anon;

-- cohort_courses
DROP POLICY IF EXISTS cohort_courses_insert_admin ON public.cohort_courses;
DROP POLICY IF EXISTS cohort_courses_update_admin ON public.cohort_courses;
DROP POLICY IF EXISTS cohort_courses_delete_admin ON public.cohort_courses;
REVOKE INSERT, UPDATE, DELETE ON public.cohort_courses FROM authenticated, anon;
