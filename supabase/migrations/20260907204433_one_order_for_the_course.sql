-- One order for the course.
--
-- The complaint
-- =============
-- `chapters.order_index` says two different things depending on when the
-- row was written, and one of them is a lie the readers have started to
-- believe.
--
-- Every chapter in production today was numbered *inside its module*:
-- each module restarts at zero. In "Книга Деяний" the four modules hold
-- lessons numbered 0-3, 0-4, 0-4 and 0-3; in "Карта в кармане" the five
-- hold 0-3, 0-2, 0-2, 0-2, 0-2; in "Глоссарий в кармане" the seven hold
-- 0-2, 0-3, 0-3, 0-4, 0-2, 0-1 and 0. Every module's range overlaps
-- every other module's range, in all three courses.
--
-- Since 2026-09-07 the write path numbers a new chapter differently:
-- `_next_chapter_order` takes the course-wide maximum plus one,
-- whichever module the chapter lands in. So the column is now half one
-- scheme and half the other, and nothing has reconciled the two.
--
-- What it already broke
-- =====================
-- The PDF export (#1234) walks `course.chapters` sorted by
-- `order_index` alone. On per-module numbering that sort is
-- 0,0,0,0,1,1,1,1,... with the ties settled by whatever order the rows
-- come back in, and the export gives each module the position of the
-- first of its lessons it meets. Run against production rows it prints
-- the headings of all three published courses out of the order their
-- author gave them — "Книга Деяний" as modules 4, 2, 1, 3; "Карта в
-- кармане" as 3, 5, 4, 2, 1; "Глоссарий" as 2, 1, 7, 6, 4, 5, 3. Valid
-- PDFs, every lesson present, the course rearranged.
--
-- What it would break next
-- ========================
-- A lesson that belongs to no module is the point of steps 1-4, and
-- there is exactly one number that can say where such a lesson sits:
-- its own. `course_structure.build_spine` places it before the first
-- heading whose lessons start above it. With per-module numbering there
-- is nothing to compare: the headings of "Книга Деяний" all start at 0,
-- so no number a teacher could give a loose lesson would put it between
-- module 1 and module 2. Appending one works by luck (the course-wide
-- maximum plus one lands past every module); dragging one into the
-- middle cannot be expressed at all.
--
-- What this file does
-- ===================
-- Renumbers every live chapter into one sequence per course, 0..n-1, in
-- the order the course reads today: modules by `modules.order_index`,
-- lessons by `chapters.order_index` inside each module, and a lesson
-- whose module is missing or NULL after all of them — which is exactly
-- where the board and the readiness checklist have been putting it, and
-- exactly what the three published courses already show. No lesson
-- changes place. Only the numbers change, from meaning "third in this
-- module" to meaning "third in this course".
--
-- Production has no loose lessons at all right now (0 rows with a NULL
-- or dangling `module_id`), so for the three courses with students the
-- ordering key reduces to (module.order_index, chapter.order_index) and
-- the resulting sequence is the one on screen. The `2147483647`
-- sentinel is there for correctness on any course that acquires a loose
-- lesson between this file being written and being run.
--
-- Soft-deleted chapters keep their old numbers on purpose: they are
-- filtered out of every read path, they take no place in the sequence,
-- and renumbering a binned row would only invent a position for
-- something that has none.
--
-- Re-runnable: the ordering key is stable under its own result, so a
-- second run computes the same numbers and updates nothing (the
-- `IS DISTINCT FROM` guard makes that literal — zero rows touched).
--
-- Not applied by `supabase db push` — the migration markers in this
-- directory and in production have diverged. Run this file by hand in
-- the SQL editor and then insert its version into
-- `supabase_migrations.schema_migrations`.

WITH ordered AS (
    SELECT c.id,
           ROW_NUMBER() OVER (
               PARTITION BY c.course_id
               ORDER BY COALESCE(m.order_index, 2147483647),
                        COALESCE(m.id, ''),
                        c.order_index,
                        c.id
           ) - 1 AS new_index
    FROM public.chapters AS c
    LEFT JOIN public.modules AS m
           ON m.id = c.module_id
          AND m.deleted_at IS NULL
    WHERE c.deleted_at IS NULL
)
UPDATE public.chapters AS c
SET order_index = o.new_index
FROM ordered AS o
WHERE o.id = c.id
  AND c.order_index IS DISTINCT FROM o.new_index;

COMMENT ON COLUMN public.chapters.order_index IS
    'Where this chapter reads in its course, counting from 0 across the whole course — not within its module. A module keeps its chapters consecutive and is placed by modules.order_index; this number orders the chapters inside a module, and places a chapter that has no module between the modules. See app/services/course_structure.build_spine.';
