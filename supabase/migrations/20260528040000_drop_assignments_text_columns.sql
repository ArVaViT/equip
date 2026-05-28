-- =====================================================================
-- Phase 5e3 — drop ``assignments.title`` and ``assignments.description``.
--
-- After Phase 3 backfill, every assignment's title + description is
-- mirrored in ``content_versions`` (entity_type='assignment',
-- field IN ('title', 'description')) which becomes the single source
-- of truth.
--
-- The read path uses ``fetch_cv_entity_texts_with_fallback`` with a
-- three-tier locale resolution (display → source → any-locale).
-- The write paths in ``api/v1/assignments.py`` pass an explicit
-- ``texts={"title": ..., "description": ...}`` arg to
-- ``dual_write_entity_content``.
--
-- Irreversibility: column data is gone after this migration. A
-- pre-merge dump is the rollback artefact.
-- =====================================================================

ALTER TABLE assignments DROP COLUMN IF EXISTS title;
ALTER TABLE assignments DROP COLUMN IF EXISTS description;
