-- =====================================================================
-- Phase 5e2 — drop ``chapter_blocks.content`` column.
--
-- After Phase 3 backfill, every chapter_block's HTML content is
-- mirrored in ``content_versions`` (entity_type='chapter_block',
-- field='content') which becomes the single source of truth.
--
-- The read path in ``localize_chapter_block_rows`` builds responses
-- from two Localizer.build queries (display locale + source locale
-- fallback). The write path in ``api/v1/blocks.py`` sanitises the
-- HTML and passes it as an explicit ``texts={"content": ...}`` arg
-- to ``dual_write_entity_content`` (Phase 5e signature extension).
--
-- Irreversibility: column data is gone after this migration. A
-- pre-merge dump is the rollback artefact.
-- =====================================================================

ALTER TABLE chapter_blocks DROP COLUMN IF EXISTS content;
