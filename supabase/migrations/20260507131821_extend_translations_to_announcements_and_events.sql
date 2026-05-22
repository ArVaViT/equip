-- Supabase migration: extend_translations_to_announcements_and_events
-- Version: 20260507131800
--
-- Adds ``announcement`` and ``course_event`` to the ``entity_type`` set of
-- ``content_translations`` so the translation pipeline can cache machine
-- translations of teacher-authored announcements (title + content) and
-- calendar events (title + description). The corresponding ``field`` values
-- (``title``, ``content``, ``description``) are already in the existing
-- ``content_translations_field_check`` constraint — no update needed there.
--
-- Idempotent: drops the existing CHECK by name first, then recreates with
-- the expanded set. Safe to replay on a clean project.

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
    'course_event'
  ));
