-- Close a model↔prod CHECK drift found by the 2026-06-11 audit.
--
-- backend/app/models/course.py has declared
--   CheckConstraint("quiz_weight + assignment_weight + participation_weight = 100",
--                   name="ck_courses_weights_sum_100")
-- since the grade-weights feature, so SQLite tests and the schema-smoke CI
-- job enforce the invariant — but no migration ever shipped it to prod. The
-- grade calculator divides by the sum assuming it is 100; the API's Pydantic
-- validator enforces it on the write path, but a direct DB write (service
-- script, MCP) could persist weights that break the math silently.
--
-- Prod data verified compliant before this migration: 12 courses, 0 rows
-- where the three weights do not sum to 100.

ALTER TABLE public.courses
  ADD CONSTRAINT ck_courses_weights_sum_100
  CHECK (quiz_weight + assignment_weight + participation_weight = 100);
