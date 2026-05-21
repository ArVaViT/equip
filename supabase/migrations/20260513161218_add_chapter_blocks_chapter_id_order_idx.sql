-- Composite index for the hot read path on chapter_blocks:
--
--   SELECT * FROM chapter_blocks
--   WHERE chapter_id IN (...) ORDER BY chapter_id, order_index
--
-- pg_stat_statements showed this as the single slowest app query (102ms p50
-- though most of that is Vercel-Lambda↔Supabase network RTT). The previous
-- single-column index on chapter_id forced a separate sort step; this
-- composite lets the planner satisfy WHERE + ORDER BY in one index walk.
-- chapter_blocks is read-heavy; write overhead from a 2-column index is
-- negligible.
--
-- The pre-existing ix_chapter_blocks_chapter_id is now redundant (left-prefix
-- of the new index serves any chapter_id-only filter). Drop it to save write
-- overhead on inserts/updates.

CREATE INDEX IF NOT EXISTS ix_chapter_blocks_chapter_id_order
  ON public.chapter_blocks (chapter_id, order_index);

DROP INDEX IF EXISTS public.ix_chapter_blocks_chapter_id;
