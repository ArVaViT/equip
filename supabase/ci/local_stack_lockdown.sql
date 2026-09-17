-- Write-surface lockdown + the auth.users trigger, replayed on top of a
-- freshly loaded `supabase/schema.sql` + `supabase/ci/rls_grants.sql`.
--
-- This is the lockdown + trigger part of step 2 ("Schema") in
-- docs/E2E.md "How the CI stack comes up", used verbatim by `.github/workflows/frontend-e2e.yml` to
-- bring up a local `supabase start` stack for the authenticated e2e specs.
--
-- Why both are needed even though `schema.sql` already carries the current
-- table + RLS-policy shape:
--
--   * `schema.sql` was dumped with `--no-privileges` (see
--     supabase/ci/README.md), so it carries no GRANTs at all. rls_grants.sql
--     (applied before this file) restores the prod grant set — but a fresh
--     Postgres cluster's implicit privileges plus that GRANT list are not
--     provably identical to prod's actual write surface, and this is a
--     security boundary worth stating explicitly rather than trusting by
--     omission. Re-asserting the REVOKE + ALTER DEFAULT PRIVILEGES here
--     costs nothing on an already-locked-down cluster and closes the gap on
--     one that isn't.
--   * `on_auth_user_created` lives on `auth.users`, which is outside the
--     `public` schema `schema.sql` dumps — it is NOT in that file by
--     construction and must be recreated by hand every time.

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
GRANT UPDATE ON public.profiles TO authenticated;
REVOKE SELECT ON public.quiz_options, public.daily_challenge_options, public.content_versions FROM anon, authenticated;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLES FROM anon, authenticated;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
