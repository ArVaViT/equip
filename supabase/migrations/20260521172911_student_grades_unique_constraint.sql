-- Supabase migration: student_grades_unique_constraint
--
-- ``api/v1/grades.py::upsert_student_grade`` is shaped as a read-then-
-- write: SELECT for an existing row, UPDATE if found, INSERT otherwise.
-- The endpoint has no row lock and no IntegrityError handling around
-- the INSERT, AND ``student_grades`` has no UNIQUE constraint on
-- ``(student_id, course_id, cohort_id)`` -- only a plain index. Two
-- teachers (or two browser tabs of the same teacher) submitting a grade
-- for the same student at the same time can both miss the SELECT and
-- both INSERT, silently producing duplicate rows. From then on,
-- ``get_student_grade`` returns whichever row ``.first()`` finds, and
-- the gradebook reports an inconsistent grade depending on physical
-- row order.
--
-- Fix: pin (student_id, course_id, cohort_id) as unique. Postgres
-- treats two rows where ``cohort_id IS NULL`` as distinct (NULLs are
-- not equal), which matches the "one grade per course-wide record"
-- intent for cohort=NULL grades. For NULL cohorts we want explicit
-- de-duplication, so use ``UNIQUE NULLS NOT DISTINCT`` (Postgres 15+,
-- which Supabase ships).
--
-- Audit ran 2026-05-21: zero existing duplicates in prod -- safe to
-- add without backfilling. The companion application-side change in
-- ``upsert_student_grade`` adds IntegrityError handling that converts a
-- concurrent-insert race into a re-read-and-update, so the unique
-- index becomes a defense-in-depth guarantee instead of a 503-emitter.

CREATE UNIQUE INDEX IF NOT EXISTS student_grades_student_course_cohort_unique
  ON public.student_grades (student_id, course_id, cohort_id)
  NULLS NOT DISTINCT;

COMMENT ON INDEX public.student_grades_student_course_cohort_unique IS
  'Prevents duplicate grade rows from races in upsert_student_grade. '
  'NULLS NOT DISTINCT collapses (student, course, NULL) rows so the '
  '"course-wide grade" path is also protected.';
