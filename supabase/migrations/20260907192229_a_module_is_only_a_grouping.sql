-- A module is only a grouping.
--
-- The complaint
-- =============
-- The first teacher to build a course on the platform had four lessons and
-- no use for modules. The model made them mandatory — a chapter could only
-- hang off a module — so the teacher invented empty ones to hold a chapter
-- each, recut the tree twice, and deleted three lessons trying to make it
-- look like the course in their head.
--
-- Step 3 of 6
-- ===========
-- Step 1 gave every chapter a second parent, `course_id`, and filled it
-- from the module (131 rows, no disagreement). Step 2 taught every reader
-- — the translation walk, the registry resolvers, the access gate, the
-- grading denominators, credit, certificates, the review queue, the
-- delete / restore / purge cascades, the clone, the calendar, the progress
-- board — to reach a chapter through `chapters.course_id`, so nothing
-- depends on the module being there any more.
--
-- This file is where a chapter without a module becomes legal in the
-- database. Two changes, and they say the same thing.
--
-- 1. `module_id` drops NOT NULL
-- =============================
-- A chapter belongs to its course. Naming a module is optional — a heading
-- a longer course may want and a short one does not. Until now the column
-- was already `Mapped[str | None]` on the SQLAlchemy side (so the tests
-- that prove the readers work without a module could build such a row) and
-- NOT NULL here: the one place the model was deliberately a step ahead of
-- the database. This closes the gap.
--
-- 2. The foreign key becomes ON DELETE SET NULL
-- =============================================
-- It is ON DELETE CASCADE today, which means physically deleting a module
-- takes its chapters with it. That was coherent while a chapter could not
-- exist without a module; under the new model it is exactly backwards. The
-- grouping is the disposable part — when it goes, the lessons stay and
-- surface at the course. SET NULL is that sentence in DDL, and it makes
-- the database agree with `delete_module`, which from this step on detaches
-- live chapters (`module_id = NULL`) instead of binning them.
--
-- The purge path is unaffected: physically deleting a *course* still takes
-- its chapters, through `chapters_course_id_fkey`, which stays CASCADE.
--
-- 3. The heal, which should touch nothing
-- =======================================
-- Until this step a soft-deleted module kept hiding its chapters, enforced
-- in one explicit predicate (`chapter_module_is_live_or_absent`). That
-- predicate goes away in the same PR, because the new answer for a live
-- chapter under a binned module is to show it at its course, not to hide it
-- for good. The UPDATE below makes that removal provably safe instead of
-- merely likely-safe: it detaches any such row so none is left relying on
-- the vanishing rule. Production has zero of them (`delete_module` has
-- always binned the chapters with the module, checked again on 2026-09-07),
-- so this is expected to report `UPDATE 0`.
--
-- Every statement is re-runnable; running the file twice changes nothing
-- the second time.
--
-- Not applied by `supabase db push` — the migration markers in this
-- directory and in production have diverged. Run this file by hand in the
-- SQL editor and then insert its version into
-- `supabase_migrations.schema_migrations`.

ALTER TABLE public.chapters
    ALTER COLUMN module_id DROP NOT NULL;

COMMENT ON COLUMN public.chapters.module_id IS
    'The module grouping this chapter under its course, or NULL when the course groups nothing. Optional: the chapter belongs to the course via course_id, and deleting the module only removes the heading.';

ALTER TABLE public.chapters
    DROP CONSTRAINT IF EXISTS chapters_module_id_fkey;

ALTER TABLE public.chapters
    ADD CONSTRAINT chapters_module_id_fkey
        FOREIGN KEY (module_id) REFERENCES public.modules(id) ON DELETE SET NULL;

UPDATE public.chapters AS c
SET module_id = NULL
FROM public.modules AS m
WHERE m.id = c.module_id
  AND c.deleted_at IS NULL
  AND m.deleted_at IS NOT NULL;
