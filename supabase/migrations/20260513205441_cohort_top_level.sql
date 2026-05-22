-- ADR-010: Cohorts become top-level admin entities; courses gain access_mode.
--
-- Full design + rationale in equipbible-docs/product/decisions/ADR-010.
-- Summary of schema deltas, in dependency order:
--   1. courses.access_mode (public | institute) — solo-enrollment gate
--   2. cohorts: drop course_id (was 1:1 FK), add created_by
--   3. cohort_courses: new junction (cohort × course)
--   4. enrollments: relax UNIQUE so retake-in-another-cohort works
--
-- All four are safe on current prod data (0 cohort rows, 16 enrollments
-- all with cohort_id=NULL, every existing course defaults to 'public').


-- 1. Course access mode -------------------------------------------------
-- 'public'    = catalog Enroll button works for any student (subject to
--               course.enrollment_start/_end window)
-- 'institute' = catalog shows description but Enroll is disabled; access
--               only via admin (cohort enrollment or direct add)
ALTER TABLE public.courses
  ADD COLUMN access_mode text NOT NULL DEFAULT 'public'
  CHECK (access_mode IN ('public', 'institute'));

CREATE INDEX IF NOT EXISTS ix_courses_access_mode ON public.courses (access_mode);


-- 2. Cohorts: drop course_id, add created_by ---------------------------
-- The FK + index on course_id are orphans after this — cohort is no longer
-- scoped to a single course. The N:N relationship lives in cohort_courses
-- (created below).
DROP INDEX IF EXISTS public.ix_cohorts_course_id;
ALTER TABLE public.cohorts DROP CONSTRAINT IF EXISTS cohorts_course_id_fkey;
ALTER TABLE public.cohorts DROP COLUMN course_id;

ALTER TABLE public.cohorts
  ADD COLUMN created_by uuid REFERENCES public.profiles(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_cohorts_created_by ON public.cohorts (created_by);


-- 3. cohort_courses junction (cohort × course, N:N) --------------------
CREATE TABLE IF NOT EXISTS public.cohort_courses (
  cohort_id uuid    NOT NULL REFERENCES public.cohorts(id) ON DELETE CASCADE,
  course_id text    NOT NULL REFERENCES public.courses(id) ON DELETE CASCADE,
  added_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (cohort_id, course_id)
);

-- Most queries land on cohort_id (list courses of a cohort); the PK's
-- left-prefix covers that. The reverse direction (which cohorts contain
-- course X) is rarer but worth one explicit index.
CREATE INDEX IF NOT EXISTS ix_cohort_courses_course_id
  ON public.cohort_courses (course_id);


-- 4. Enrollment UNIQUE: (user, course) → (user, course, cohort) ---------
-- Retake-in-a-different-cohort needs to write a NEW enrollment row
-- rather than overwrite the old one. COALESCE maps NULL cohort_id to a
-- sentinel UUID so two solo enrollments to the same course are still
-- rejected (we don't want a user accidentally enrolling themselves twice).
ALTER TABLE public.enrollments DROP CONSTRAINT IF EXISTS uq_enrollment_user_course;

CREATE UNIQUE INDEX uq_enrollment_user_course_cohort
  ON public.enrollments (
    user_id,
    course_id,
    COALESCE(cohort_id, '00000000-0000-0000-0000-000000000000'::uuid)
  );
