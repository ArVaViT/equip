-- Enable RLS on cohort_courses (created in 20260513205435_cohort_top_level
-- without policies — flagged by the Supabase database linter as an
-- ERROR-level rls_disabled_in_public lint).
--
-- The FastAPI backend uses the service-role key and bypasses RLS, so this
-- is defense in depth against direct PostgREST access via the anon key.
--
-- Policy shape mirrors `public.cohorts`:
--   - SELECT open to everyone (the catalog enroll dialog reads cohorts
--     attached to a course via this junction).
--   - INSERT / UPDATE / DELETE gated to authenticated users whose
--     `profiles.role` is admin. ADR-010 makes cohort management admin-only;
--     RLS enforces that even if the API layer were ever bypassed.

ALTER TABLE public.cohort_courses ENABLE ROW LEVEL SECURITY;

CREATE POLICY cohort_courses_select_all
  ON public.cohort_courses
  FOR SELECT
  USING (true);

CREATE POLICY cohort_courses_insert_admin
  ON public.cohort_courses
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = (SELECT auth.uid())
        AND p.role = 'admin'
    )
  );

CREATE POLICY cohort_courses_update_admin
  ON public.cohort_courses
  FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = (SELECT auth.uid())
        AND p.role = 'admin'
    )
  );

CREATE POLICY cohort_courses_delete_admin
  ON public.cohort_courses
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM public.profiles p
      WHERE p.id = (SELECT auth.uid())
        AND p.role = 'admin'
    )
  );
