-- Phase 5bo: enable RLS on translation_jobs.
--
-- Why
-- ===
-- The 5av queue migration (20260529150000_translation_jobs_table.sql)
-- created the table without ALTER TABLE ... ENABLE ROW LEVEL SECURITY.
-- Equip's standard is "RLS on by default, policies explicit" — every
-- other newer user-visible table (notifications, course_events,
-- audit_logs, content_versions, ...) follows this. Internal-only
-- tables don't get a free pass because:
--
--   * The cron worker authenticates with the service_role key, which
--     bypasses RLS — so locking down to service_role only costs
--     nothing at runtime.
--   * Any future Supabase Edge Function or anon-key client that
--     accidentally inherits SELECT/INSERT/DELETE permission would
--     otherwise see the full queue (course publish history is a
--     low-value but real info disclosure).
--   * The architectural invariant is more valuable than the table's
--     current risk profile — keeping RLS-by-default consistent means
--     a future contributor adding a similar internal table doesn't
--     also forget.
--
-- The 5bn audit (auth + perf) flagged this gap. Fix is one ALTER + a
-- single restrictive policy.

ALTER TABLE public.translation_jobs ENABLE ROW LEVEL SECURITY;

-- service_role bypasses RLS automatically, so we don't need a policy
-- for the cron worker. The only policy we add is an explicit DENY for
-- the authenticated and anon roles: an empty USING clause (no rows
-- match) on a SELECT/INSERT/UPDATE/DELETE policy is the standard
-- Postgres pattern for "RLS is on, no one matches" — equivalent to
-- "no policy" but with the intent documented in source.
--
-- Admin observability still goes through ``GET /admin/translations/
-- queue-status`` which runs server-side under service_role; admins do
-- NOT need direct table access via the Supabase client.

CREATE POLICY translation_jobs_no_client_access ON public.translation_jobs
  FOR ALL TO authenticated, anon
  USING (false)
  WITH CHECK (false);
