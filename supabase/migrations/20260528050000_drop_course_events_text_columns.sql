-- =====================================================================
-- Phase 5e4 — drop ``course_events.title`` and ``course_events.description``.
--
-- After Phase 3 backfill, every course event's title + description is
-- mirrored in ``content_versions`` (entity_type='course_event',
-- field IN ('title', 'description')) which becomes the single source
-- of truth.
--
-- The read path uses ``fetch_cv_entity_texts_with_fallback`` with a
-- three-tier locale resolution (display → source → any-locale).
-- The write paths in ``api/v1/calendar.py`` (create + update event)
-- pass an explicit ``texts={"title": ..., "description": ...}`` arg
-- to ``dual_write_entity_content``.
--
-- Irreversibility: column data is gone after this migration. A
-- pre-merge dump is the rollback artefact.
-- =====================================================================

ALTER TABLE course_events DROP COLUMN IF EXISTS title;
ALTER TABLE course_events DROP COLUMN IF EXISTS description;
