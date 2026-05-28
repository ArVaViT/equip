-- =====================================================================
-- Phase 5e5 — drop ``announcements.title`` and ``announcements.content``.
--
-- After Phase 3 backfill, every announcement's title + content is
-- mirrored in ``content_versions`` (entity_type='announcement',
-- field IN ('title', 'content')) which becomes the single source of
-- truth.
--
-- The read path uses ``fetch_cv_entity_texts_with_fallback`` with a
-- three-tier locale resolution (display → source → any-locale).
-- The write paths in ``api/v1/announcements.py`` pass an explicit
-- ``texts={"title": ..., "content": ...}`` arg to
-- ``dual_write_entity_content``.
--
-- Irreversibility: column data is gone after this migration. A
-- pre-merge dump is the rollback artefact.
-- =====================================================================

ALTER TABLE announcements DROP COLUMN IF EXISTS title;
ALTER TABLE announcements DROP COLUMN IF EXISTS content;
