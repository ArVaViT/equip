-- Restored from prod schema_migrations on 2026-05-21 — this migration was
-- originally applied via Supabase MCP without a corresponding repo file.
--
-- Clean cut: drop the legacy 1:1 cohorts.course_id column. The N:N
-- relationship lives in cohort_courses now. ADR-010 §2.
DROP INDEX IF EXISTS public.ix_cohorts_course_id;
ALTER TABLE public.cohorts DROP CONSTRAINT IF EXISTS cohorts_course_id_fkey;
ALTER TABLE public.cohorts DROP COLUMN IF EXISTS course_id;
