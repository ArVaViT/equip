-- Two RLS hardenings flagged by the 2026-05-21 security audit:
--
-- 1. ``profiles_select_authenticated`` exposed every user's email + role
--    to ANY authenticated user via PostgREST. A student could enumerate
--    admin emails for spear-phishing or scrape the whole member list.
--    Restrict to self only. Backend service-role reads still work
--    (service-role bypasses RLS); the three frontend PostgREST
--    consumers (AuthContext.enrichProfile, usersService.updateProfile,
--    and the implicit SELECT after UPDATE) all already key on
--    ``id = auth.uid()`` and continue to work.
--
-- 2. ``enrollments_insert_own`` let a student self-enroll into ANY
--    course via PostgREST, bypassing the publish / access_mode /
--    cohort / enrollment-window gates in the backend's
--    ``POST /api/v1/courses/{id}/enroll`` route. Drop the policy and
--    REVOKE INSERT — server is the only legitimate writer.
--
-- 3. Drop the legacy ``Allow full access for postgres role`` policies
--    on chapters / courses / enrollments / modules. The ``postgres``
--    superuser bypasses RLS anyway; these policies are dead weight
--    from the initial ``enable_rls_all_tables`` migration.

DROP POLICY IF EXISTS profiles_select_authenticated ON public.profiles;

CREATE POLICY profiles_select_self
    ON public.profiles
    FOR SELECT
    TO authenticated
    USING (id = (SELECT auth.uid()));

DROP POLICY IF EXISTS enrollments_insert_own ON public.enrollments;

REVOKE INSERT ON public.enrollments FROM authenticated, anon;

DROP POLICY IF EXISTS "Allow full access for postgres role" ON public.chapters;
DROP POLICY IF EXISTS "Allow full access for postgres role" ON public.courses;
DROP POLICY IF EXISTS "Allow full access for postgres role" ON public.enrollments;
DROP POLICY IF EXISTS "Allow full access for postgres role" ON public.modules;
