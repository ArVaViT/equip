-- A second hand-in is a new row, and a second cohort is a new grade.
--
-- Two UNIQUE constraints in production contradict what the application does,
-- and neither exists in the SQLAlchemy models the test suite builds its
-- database from — so every test of the behaviour they break was green.
--
-- 1. assignment_submissions_assignment_id_student_id_key
--    UNIQUE (assignment_id, student_id), from the dashboard era, before
--    migration tracking. `submit_assignment` inserts a NEW row on every hand-in
--    (resubmitting before marking, and again after a teacher returns the
--    work), and `latest_submissions` resolves the newest row as the one that
--    counts. Rubric marks and the integrity declaration hang off the
--    individual submission row, so the history is the design, not an
--    accident (#968, #971). With this constraint the second hand-in is a
--    unique violation → 409. The table is empty in production, which is the
--    only reason nobody has hit it.
--
--    20260514144615 dropped idx_submissions_assignment_id as "covered by"
--    this constraint. The index created below takes over that job, and keys
--    on what the reads actually filter and sort by: the per-assignment list
--    (assignment_id, ORDER BY submitted_at DESC), a student's own submissions
--    for one assignment (assignment_id, student_id, ORDER BY submitted_at
--    DESC), and `latest_submissions` (assignment_id IN (...), student_id).
--    Created before the constraint is dropped so the lookups are never
--    without an index.
--
-- 2. student_grades_student_id_course_id_key
--    UNIQUE (student_id, course_id), also pre-tracking. ADR-010 lets a student
--    take a course again in a later cohort, and 20260521172911 made the grade
--    row unique on (student_id, course_id, cohort_id) NULLS NOT DISTINCT for
--    exactly that. The older two-column constraint was never dropped, so a
--    grade in the second cohort would be refused. Its lookups stay indexed:
--    (student_id, course_id) is the leading prefix of the three-column unique.
--
-- 3. ix_submission_declarations_submission
--    A plain index on (submission_id) beside
--    uq_submission_declarations_submission, a UNIQUE on the same single
--    column. The unique answers every lookup the plain one can; the plain one
--    only costs writes. The UNIQUE stays — one declaration per submission is
--    the rule.
--
-- Idempotent: IF NOT EXISTS / IF EXISTS throughout. No data changes; both
-- tables with dropped constraints are empty at the time of writing.

CREATE INDEX IF NOT EXISTS ix_assignment_submissions_assignment_student_submitted
  ON public.assignment_submissions USING btree (assignment_id, student_id, submitted_at DESC);

ALTER TABLE public.assignment_submissions
  DROP CONSTRAINT IF EXISTS assignment_submissions_assignment_id_student_id_key;

ALTER TABLE public.student_grades
  DROP CONSTRAINT IF EXISTS student_grades_student_id_course_id_key;

DROP INDEX IF EXISTS public.ix_submission_declarations_submission;
