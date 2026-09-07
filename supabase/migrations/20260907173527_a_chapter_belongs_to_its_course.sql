-- A chapter belongs to its course.
--
-- The complaint
-- =============
-- The first teacher to build a course on the platform had four lessons and
-- no use for modules. The model made them mandatory — a chapter could only
-- hang off a module — so the teacher invented some: an empty «Lesson 2»,
-- «Lesson 3», «Lesson 4» to hold one chapter each, then a single «Module 1»
-- to hold the lot, then deleted three chapters trying to make the tree look
-- like the course in their head. The model did not match how a person
-- thinks about a course: chapters are the course; a module is a heading a
-- longer course may want and a short one does not.
--
-- The change, in steps
-- ====================
-- Chapters will belong to the course directly, with the module an optional
-- grouping. This file is step 1 of 6 and is purely additive: every chapter
-- gains a second parent, `course_id`, filled from the module it already
-- has. Nothing reads it yet; every write path sets it alongside
-- `module_id`, and the invariant `chapters.course_id = modules.course_id`
-- holds for every row. `module_id` stays NOT NULL and keeps its FK — making
-- the module optional is the next step, once every reader knows the course
-- can hold chapters on its own.
--
-- Backfill
-- ========
-- Unambiguous: every one of the 131 chapters on production references an
-- existing module, and no live chapter sits under a trashed module
-- (`delete_module` has always trashed the chapters with it). So the
-- module's course is the chapter's course, for trashed and live rows alike,
-- and NOT NULL can be set in the same file.
--
-- The index
-- =========
-- `(course_id, order_index)` on live rows is the read every course-level
-- path will make from step 2 on — the chapters of this course, in order,
-- skipping the trash. The existing `ix_chapters_module_id` stays for the
-- module walk, which every reader still takes today.
--
-- Not applied by `supabase db push` — the migration markers in this
-- directory and in production have diverged. Run this file by hand in the
-- SQL editor and then insert its version into
-- `supabase_migrations.schema_migrations`.

ALTER TABLE public.chapters
    ADD COLUMN IF NOT EXISTS course_id character varying
        REFERENCES public.courses(id) ON DELETE CASCADE;

COMMENT ON COLUMN public.chapters.course_id IS
    'The course this chapter belongs to. Equal to modules.course_id of its module while every chapter still has one; the module becomes optional in a later step.';

UPDATE public.chapters AS c
SET course_id = m.course_id
FROM public.modules AS m
WHERE m.id = c.module_id
  AND c.course_id IS NULL;

ALTER TABLE public.chapters
    ALTER COLUMN course_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS ix_chapters_course_id_order_active
    ON public.chapters (course_id, order_index)
    WHERE deleted_at IS NULL;

COMMENT ON INDEX public.ix_chapters_course_id_order_active IS
    'The chapters of one course in order, live rows only — the read every course-level path takes once a chapter no longer needs a module.';
