-- A machine's old drafts are not history.
--
-- What this is for
-- ================
-- `content_versions` supersedes rather than overwrites, so a text's history
-- survives every edit. For rows a person wrote, that is the point. For rows
-- Gemini produced it is storage spent on something reproducible: the source is
-- still there, and re-translating a string costs about half a second.
--
-- Production on 2026-09-20 carried 16 604 superseded machine rows — 9 MB of a
-- 14 MB table, two thirds of it — accumulated in six weeks of editing. The
-- retention pass in `app/services/content_versions/prune.py` deletes them once
-- they are older than `TRANSLATION_HISTORY_RETENTION_DAYS` (30 by default) and
-- nothing points at them. Superseded rows a *human* wrote are never touched;
-- there are 93 of them, and they weigh 65 kB.
--
-- Why an index
-- ============
-- The pass runs on an idle worker tick, every minute, and asks exactly one
-- question: which superseded machine rows are older than the cutoff. Without an
-- index that is a sequential scan of the whole table each time — tolerable at
-- 31 539 rows, not at the 2.9 million rows 500 courses would put here.
--
-- Partial, because the predicate is the query: `origin = 'mt'` and superseded.
-- That is two thirds of the table today, but the index carries one timestamp
-- per row rather than the text, and the rows it covers are the only ones the
-- pass ever reads.

CREATE INDEX IF NOT EXISTS ix_content_versions_prunable
    ON public.content_versions (updated_at)
    WHERE origin = 'mt' AND superseded_by IS NOT NULL;

COMMENT ON INDEX public.ix_content_versions_prunable IS
    'Retention pass over superseded machine translations; see services/content_versions/prune.py.';
