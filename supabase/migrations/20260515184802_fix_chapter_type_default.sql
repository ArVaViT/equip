-- Repair a schema-drift bug surfaced by the 2026-05-15 DB audit.
--
-- chapters.chapter_type has DEFAULT 'content' but the CHECK constraint
-- (chapters_chapter_type_check, last edited in
-- 20260422234516_drop_legacy_chapter_course_columns.sql) only allows
-- ('reading', 'quiz', 'exam', 'assignment'). That migration tightened
-- the CHECK to match CHAPTER_TYPES in backend/app/schemas/course.py
-- but forgot to update the column default.
--
-- Effect: any INSERT INTO public.chapters that omits chapter_type
-- relies on the 'content' default, which then violates the CHECK. The
-- failure has been latent because the SQLAlchemy Chapter model passes
-- chapter_type='reading' explicitly via its Python-side default, so
-- the bad default is never exercised through the app. A raw INSERT
-- (psql, MCP, future script) would fail with:
--     ERROR: new row for relation "chapters" violates check constraint
--            "chapters_chapter_type_check"
--
-- Data is already clean: pre-flight on 2026-05-15 returned only
-- 'reading' (21), 'quiz' (5), 'exam' (1) for existing rows. No
-- 'content' values exist.

ALTER TABLE public.chapters
  ALTER COLUMN chapter_type SET DEFAULT 'reading';
