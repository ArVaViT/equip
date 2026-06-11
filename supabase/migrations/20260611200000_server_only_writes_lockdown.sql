-- Server-only writes lockdown (2026-06-11 full audit).
--
-- With the anon key shipped to every browser, Postgres GRANTs + RLS policies
-- ARE the security boundary for direct supabase-js access — the same lesson
-- as the answer-key leak fixed in 20260608200000. This audit found the
-- remaining client WRITE surface still open (grant + permissive policy):
--
--   * certificates: the INSERT policy only checked user_id = auth.uid(), so
--     any logged-in user could insert a row with status='approved' and a
--     self-chosen certificate_number — which the public /verify endpoint
--     honored as a genuine credential. (Not exploited: all 4 prod rows carry
--     legitimate approval trails.)
--   * quiz_attempts / quiz_answers: INSERT-own → fabricate passed attempts
--     with arbitrary score / is_correct / points_earned.
--   * chapter_progress: INSERT/UPDATE/DELETE-own → fake course progress,
--     which feeds certificate eligibility and the gradebook.
--   * assignment_submissions (INSERT-own), course_reviews (INSERT/DELETE-own),
--     enrollments (DELETE-own), notifications (UPDATE-own), and the
--     teacher-gated write policies on courses / quizzes / cohorts /
--     course_prerequisites.
--
-- Every legitimate write already goes through the FastAPI backend (which
-- connects as postgres and is not subject to these grants); the SPA's only
-- direct table write is the profiles safe-fields UPDATE (guarded by the
-- trg_profiles_protect_immutable_fields trigger). So:
--
--   1. Revoke INSERT/UPDATE/DELETE from anon + authenticated on every public
--      table, then grant back the single sanctioned write (profiles UPDATE).
--      TRUNCATE is included because RLS does not apply to it; it is not
--      reachable through PostgREST today, but there is no reason to keep it.
--   2. Drop the write policies made inert by (1) so pg_policies reflects the
--      real surface instead of advertising writes that grants deny.
--   3. Flip DEFAULT PRIVILEGES so tables created by future migrations are
--      born without client write grants (this gap kept reappearing because
--      Supabase's defaults grant ALL to anon/authenticated on new tables).
--
-- The SELECT surface is intentionally untouched.

-- 1) Revoke all client write grants on the current public tables.
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
    EXECUTE format(
      'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON public.%I FROM anon, authenticated',
      t.tablename
    );
  END LOOP;
END $$;

-- The one sanctioned client write: own-profile safe fields (display name,
-- avatar, locale…). Row scoping via profiles_update_own_safe_fields; column
-- protection via trg_profiles_protect_immutable_fields (id/role/email/created_at).
GRANT UPDATE ON public.profiles TO authenticated;

-- 2) Drop the now-inert write policies (server-only tables need no write
--    policies at all; their absence *is* the documentation).
DROP POLICY IF EXISTS certificates_insert_request ON public.certificates;
DROP POLICY IF EXISTS quiz_attempts_insert_own ON public.quiz_attempts;
DROP POLICY IF EXISTS quiz_answers_insert_own ON public.quiz_answers;
DROP POLICY IF EXISTS chapter_progress_insert_own ON public.chapter_progress;
DROP POLICY IF EXISTS chapter_progress_update_own ON public.chapter_progress;
DROP POLICY IF EXISTS chapter_progress_delete_own ON public.chapter_progress;
DROP POLICY IF EXISTS submissions_insert_own ON public.assignment_submissions;
DROP POLICY IF EXISTS reviews_insert_own ON public.course_reviews;
DROP POLICY IF EXISTS reviews_delete_own ON public.course_reviews;
DROP POLICY IF EXISTS enrollments_delete_own ON public.enrollments;
DROP POLICY IF EXISTS notifications_update_own ON public.notifications;
DROP POLICY IF EXISTS courses_insert_teacher ON public.courses;
DROP POLICY IF EXISTS courses_update_teacher ON public.courses;
DROP POLICY IF EXISTS courses_delete_teacher ON public.courses;
DROP POLICY IF EXISTS quizzes_insert_teacher ON public.quizzes;
DROP POLICY IF EXISTS quizzes_update_teacher ON public.quizzes;
DROP POLICY IF EXISTS quizzes_delete_teacher ON public.quizzes;
DROP POLICY IF EXISTS cohorts_insert_teacher ON public.cohorts;
DROP POLICY IF EXISTS cohorts_update_teacher ON public.cohorts;
DROP POLICY IF EXISTS cohorts_delete_teacher ON public.cohorts;
DROP POLICY IF EXISTS prereqs_insert_teacher ON public.course_prerequisites;
DROP POLICY IF EXISTS prereqs_delete_teacher ON public.course_prerequisites;

-- 3) Future tables: no client write grants by default. Applies to objects
--    created by the role running migrations (postgres via MCP / dashboard).
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLES FROM anon, authenticated;
