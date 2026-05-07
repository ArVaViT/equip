-- Supabase migration: extend_translations_to_cohorts
-- Version: 20260507155100
--
-- Adds ``cohort`` to the ``entity_type`` set of ``content_translations``
-- so the translation pipeline can cache machine translations of
-- teacher-authored cohort names. Mirrors the shape used for
-- announcements and course events. Idempotent.

ALTER TABLE public.content_translations
  DROP CONSTRAINT IF EXISTS content_translations_entity_type_check;

ALTER TABLE public.content_translations
  ADD CONSTRAINT content_translations_entity_type_check
  CHECK (entity_type IN (
    'chapter_block',
    'course',
    'module',
    'chapter',
    'quiz',
    'quiz_question',
    'quiz_option',
    'assignment',
    'announcement',
    'course_event',
    'cohort'
  ));
