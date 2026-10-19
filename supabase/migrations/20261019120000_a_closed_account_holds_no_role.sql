-- A closed account holds no role.
--
-- An account its owner deleted (`DELETE /users/me`, 20261016130000) or an
-- administrator switched off keeps its Supabase session on purpose: a
-- deleted account is not banned in GoTrue, because the ban would tell
-- anybody typing the address that it belongs to a deleted Equip account,
-- and the session is the door back for a restore. The API refuses every
-- call of such a session (`refuse_if_closed`), and the profile trigger
-- freezes its row (20261016130000).
--
-- The policies did not know. Every one of them asks a SECURITY DEFINER
-- helper -- `can_teach()`, `is_platform_staff()`, `is_staff_of()`,
-- `is_member_of()` -- and the helpers read `profiles.role` and the
-- membership rows, neither of which deletion or deactivation touches. So
-- with the publishable key and the session it still held, a closed account
-- read as the teacher, director or administrator it used to be (security
-- review, 2026-10-19):
--
--   * a director switched off for cause still read the school's
--     certificates (student names), cohorts and closed courses through
--     PostgREST, for as long as the refresh token lived;
--   * a teacher who deleted their account still passed `can_teach()`, which
--     is the whole of `course_assets_teacher_insert`: new files into the
--     public bucket the site serves from its own origin, and the covers of
--     courses that now belong to the school deleted or overwritten;
--   * an administrator switched off still read the audit trail and the
--     Daily Challenge editorial.
--
-- Each helper now also asks whether the account is open
-- (`profiles.deactivated_at IS NULL`; a deleted account is always a
-- deactivated one, by `profiles_deleted_is_deactivated_check`). Two policies
-- that spelled the administrator check out by hand instead of calling the
-- helper -- `audit_logs_select_admin` and `course_events_select` -- now call
-- it. Own rows (`user_id = auth.uid()`) stay readable: the export and the
-- restore screen need them, and they are the person's own.
--
-- The backend connects as `postgres` and is not touched by any of this;
-- `is_director_of()` and `member_organization_ids()` have no policy reader
-- today and are closed with the rest so a future one cannot reopen the door.
--
-- CREATE OR REPLACE keeps each function's grants (20260915030000: no
-- EXECUTE for anon on the definer helpers). Idempotent; a brief lock on
-- each function's catalog entry.
--
-- Asserted in supabase/ci/rls_assertions.sql, section 18.

CREATE OR REPLACE FUNCTION public.can_teach() RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.profiles
        WHERE id = (SELECT auth.uid()) AND role IN ('teacher', 'director', 'admin')
          AND deactivated_at IS NULL
    );
$$;

CREATE OR REPLACE FUNCTION public.is_platform_staff() RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.profiles
        WHERE id = (SELECT auth.uid()) AND role = 'admin'
          AND deactivated_at IS NULL
    );
$$;

CREATE OR REPLACE FUNCTION public.is_director_of(org uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
    SELECT org IS NOT NULL AND EXISTS (
        SELECT 1 FROM public.organization_members m
        JOIN public.profiles p ON p.id = m.user_id AND p.deactivated_at IS NULL
        WHERE m.user_id = (SELECT auth.uid()) AND m.organization_id = org AND m.status = 'active'
          AND m.role = 'director'
    );
$$;

CREATE OR REPLACE FUNCTION public.is_member_of(org uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
    SELECT org IS NOT NULL AND EXISTS (
        SELECT 1 FROM public.organization_members m
        JOIN public.profiles p ON p.id = m.user_id AND p.deactivated_at IS NULL
        WHERE m.user_id = (SELECT auth.uid()) AND m.organization_id = org AND m.status = 'active'
    );
$$;

CREATE OR REPLACE FUNCTION public.is_staff_of(org uuid) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
    SELECT org IS NOT NULL AND EXISTS (
        SELECT 1 FROM public.organization_members m
        JOIN public.profiles p ON p.id = m.user_id AND p.deactivated_at IS NULL
        WHERE m.user_id = (SELECT auth.uid()) AND m.organization_id = org AND m.status = 'active'
          AND m.role IN ('teacher', 'director')
    );
$$;

CREATE OR REPLACE FUNCTION public.member_organization_ids() RETURNS SETOF uuid
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
    SELECT m.organization_id FROM public.organization_members m
    JOIN public.profiles p ON p.id = m.user_id AND p.deactivated_at IS NULL
    WHERE m.user_id = (SELECT auth.uid()) AND m.status = 'active';
$$;

COMMENT ON FUNCTION public.can_teach() IS
  'Teacher, director or platform admin, by profiles.role -- and the account is open (deactivated_at IS NULL). See 20261019120000.';
COMMENT ON FUNCTION public.is_platform_staff() IS
  'Platform admin, by profiles.role -- and the account is open (deactivated_at IS NULL). See 20261019120000.';
COMMENT ON FUNCTION public.is_director_of(org uuid) IS
  'Active director of this organization, with an open account. false for NULL. Platform admin is not a membership role: policies say is_platform_staff() OR is_director_of().';
COMMENT ON FUNCTION public.is_member_of(org uuid) IS
  'Active member of this organization in any role, with an open account. false for NULL -- a NULL organization must never satisfy a comparison.';
COMMENT ON FUNCTION public.is_staff_of(org uuid) IS
  'Active teacher or director of this organization, with an open account. false for NULL.';

-- `(SELECT ...)`: the helper takes no argument from the row, and wrapped in
-- a scalar subquery the planner evaluates it once per statement (InitPlan)
-- instead of once per row -- which is what the inline EXISTS it replaces
-- already did, and what audit_logs, the largest table here, needs.
ALTER POLICY audit_logs_select_admin ON public.audit_logs
  USING ((SELECT public.is_platform_staff()));

ALTER POLICY course_events_select ON public.course_events
  USING (
    created_by = (SELECT auth.uid())
    OR EXISTS (
      SELECT 1 FROM public.enrollments e
      WHERE e.course_id::text = course_events.course_id::text
        AND e.user_id = (SELECT auth.uid())
    )
    OR (SELECT public.is_platform_staff())
  );
