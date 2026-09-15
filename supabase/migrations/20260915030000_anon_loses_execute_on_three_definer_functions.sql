-- Take EXECUTE on the three SECURITY DEFINER helpers away from `anon`.
--
-- Supabase grants EXECUTE on every new function in `public` to `anon` and
-- `authenticated` directly — separately from the PUBLIC pseudo-role. So the
-- `REVOKE ... FROM PUBLIC` in 20260830040000_rls_learns_about_organizations
-- did not do what it looks like it does: it removed the PUBLIC grant and left
-- the one Supabase had handed to `anon`. can_teach(), added later without any
-- revoke at all, simply inherited the default. pg_proc.proacl still carries
-- `anon=X/postgres` for all three.
--
-- Nothing leaks through them today. Called as `anon` they return, verified
-- against production inside a rolled-back transaction:
--
--   can_teach()               false
--   current_organization_id() null
--   is_platform_staff()       false
--
-- All three hang off auth.uid(), which is null without a JWT, and `id = null`
-- is never true. So this is hygiene, not a hole — but it is hygiene the
-- authors clearly intended (hence the revoke that missed, and the comment in
-- 20260910120214 noting anonymous callers gain nothing), and a function that
-- runs as its owner should not be callable by someone who never signed in.
-- The next change to one of these bodies should not have to re-derive that
-- an anonymous caller cannot reach anything.
--
-- `authenticated` and `service_role` hold their own explicit grants; revoking
-- from `anon` does not touch them. The RLS policies that call these helpers
-- (cohorts_select_own_organization, courses_select_published,
-- certificates_select_own_or_reviewer) are all `TO authenticated`, and the
-- storage policies on course-assets evaluate to false for `anon` regardless.

REVOKE EXECUTE ON FUNCTION public.can_teach() FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.current_organization_id() FROM anon;
REVOKE EXECUTE ON FUNCTION public.is_platform_staff() FROM anon;
