-- Restored from prod schema_migrations on 2026-05-21 — this migration was
-- originally applied via Supabase MCP without a corresponding repo file.
--
-- HOTFIX: restore cohorts.course_id as nullable so the existing backend
-- (still on main, which references this column via SQLAlchemy) doesn't
-- 503 on cohort queries while the full top-level refactor lands. The
-- column is NULL-allowed and has no rows, so this is non-destructive
-- and fully compatible with the in-flight ADR-010 design — when the
-- new cohort API ships it'll just ignore this column.
ALTER TABLE public.cohorts
  ADD COLUMN course_id text REFERENCES public.courses(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS ix_cohorts_course_id ON public.cohorts (course_id);
