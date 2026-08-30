-- RLS learns about organizations.
--
-- Step 5 of engineering/organizations-engineering-plan.md, and the last
-- of the three isolation layers described in its §4. The order matters:
-- the route asserts, the query filters, and RLS is the backstop. This
-- file is only the backstop — the backend holds the service-role key,
-- which bypasses RLS entirely, so an organization check that existed
-- *only* here would protect nothing on the path that actually serves
-- users. Steps 3 and 3b did that work; this closes the door behind it,
-- for anything reaching Postgres as `authenticated` rather than through
-- the API.
--
-- What was open at the policy layer before this: `cohorts_select_all`
-- was literally `USING (true)` for every signed-in account, and
-- `courses_select_published` let any authenticated reader see an
-- `institute` course belonging to somebody else's school. The rest of
-- the tables carrying `organization_id` — grade_sheets, invitations,
-- org_settings — have RLS enabled with no SELECT policy for
-- `authenticated` at all, which is already closed; they are listed here
-- so the next reader does not have to prove that twice.

-- ---------------------------------------------------------------------
-- Who is asking, and where do they sit
-- ---------------------------------------------------------------------
--
-- SECURITY DEFINER on purpose. Reading `profiles` from inside a policy
-- would apply `profiles`' own RLS to the lookup, which is both slower
-- and a recursion waiting for the first person who writes a policy on
-- `profiles` that reads another table. The function is STABLE, so the
-- planner evaluates it once per statement rather than once per row.
--
-- `search_path` is pinned: a SECURITY DEFINER function without it runs
-- whatever `public` happens to mean to the caller.

CREATE OR REPLACE FUNCTION public.current_organization_id()
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT organization_id FROM public.profiles WHERE id = (SELECT auth.uid());
$$;

COMMENT ON FUNCTION public.current_organization_id() IS
    'The organization of the signed-in account, or NULL for platform staff '
    'and for a student who joined from the catalogue and belongs nowhere yet. '
    'NULL must never satisfy an organization comparison: every policy below '
    'writes `IS NOT NULL AND =` rather than `=` alone.';

CREATE OR REPLACE FUNCTION public.is_platform_staff()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.profiles
        WHERE id = (SELECT auth.uid()) AND role = 'admin'
    );
$$;

COMMENT ON FUNCTION public.is_platform_staff() IS
    'Platform administration, deliberately not the same as running an '
    'organization (see 20260826120000_a_director_is_not_a_platform_admin). '
    'Checked by role rather than by organization_id because staff may also '
    'belong somewhere: the role says what you may do, the column says where '
    'you sit.';

REVOKE EXECUTE ON FUNCTION public.current_organization_id() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.is_platform_staff() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.current_organization_id() TO authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.is_platform_staff() TO authenticated, service_role;

-- ---------------------------------------------------------------------
-- cohorts: was `USING (true)`
-- ---------------------------------------------------------------------
--
-- A cohort names a class: its dates, its size, and through the junction
-- the students in it. Every signed-in account on the platform could read
-- every school's.

DROP POLICY IF EXISTS cohorts_select_all ON public.cohorts;
DROP POLICY IF EXISTS cohorts_select_own_organization ON public.cohorts;

CREATE POLICY cohorts_select_own_organization ON public.cohorts
    FOR SELECT TO authenticated
    USING (
        public.is_platform_staff()
        OR (
            public.current_organization_id() IS NOT NULL
            AND organization_id = public.current_organization_id()
        )
    );

-- ---------------------------------------------------------------------
-- courses: a published `institute` course is not public reading
-- ---------------------------------------------------------------------
--
-- The catalogue route already filters on `access_mode = 'public'`
-- (#1166). The policy did not, so a reader going straight to Postgres
-- saw another school's internal course tree. Public courses stay
-- readable by everyone signed in — that is the catalogue — and an
-- `institute` course is readable by its own organization, its author,
-- and staff.

DROP POLICY IF EXISTS courses_select_published ON public.courses;

CREATE POLICY courses_select_published ON public.courses
    FOR SELECT TO authenticated
    USING (
        created_by = (SELECT auth.uid())
        OR public.is_platform_staff()
        OR (
            status = 'published'
            AND (
                access_mode = 'public'
                OR (
                    public.current_organization_id() IS NOT NULL
                    AND organization_id = public.current_organization_id()
                )
            )
        )
    );

-- ---------------------------------------------------------------------
-- certificates: a student keeps theirs; a reviewer sees their own school
-- ---------------------------------------------------------------------
--
-- The existing policy let any teacher or director read every
-- certificate on the platform, which is a student's name against a
-- course they took at a school the reader has nothing to do with. The
-- student's own row stays readable unconditionally — it is theirs, and
-- a student who has left an organization must not lose sight of the
-- diploma they earned.

DROP POLICY IF EXISTS certificates_select_own_or_teacher ON public.certificates;
DROP POLICY IF EXISTS certificates_select_own_or_reviewer ON public.certificates;

CREATE POLICY certificates_select_own_or_reviewer ON public.certificates
    FOR SELECT TO authenticated
    USING (
        user_id = (SELECT auth.uid())
        OR public.is_platform_staff()
        OR (
            public.current_organization_id() IS NOT NULL
            AND organization_id = public.current_organization_id()
            AND EXISTS (
                SELECT 1 FROM public.profiles p
                WHERE p.id = (SELECT auth.uid())
                  AND p.role IN ('teacher', 'director', 'admin')
            )
        )
    );
