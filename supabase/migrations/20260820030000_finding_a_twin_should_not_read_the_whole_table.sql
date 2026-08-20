-- Reusing a translation must not cost a full table scan.
--
-- `_load_twins` asks: has this exact text already been translated into this
-- language, anywhere? It is what makes 27% of the corpus free — answer options
-- repeat across quizzes, and asking the provider once for all of them is most
-- of the saving in a pass. The query filters on `source_hash IN (…)` plus
-- locale, status and the active-row condition.
--
-- There is no index on source_hash. At 23,000 rows nobody notices; the planner
-- scans and the tick still finishes. At a hundred courses (~400,000 rows) a
-- single course of three thousand fields drives six full scans per tick, and
-- the scans are what the tick spends its budget on rather than translating. At
-- a thousand courses it does not finish.
--
-- The index is partial on exactly the rows the lookup can use — active, ok —
-- because a superseded or parked row is never a twin worth copying, and
-- indexing them would double the index for nothing.

CREATE INDEX ix_content_versions_twin_lookup
    ON public.content_versions (source_hash, locale)
    WHERE superseded_by IS NULL AND status = 'ok' AND source_hash IS NOT NULL;

COMMENT ON INDEX public.ix_content_versions_twin_lookup IS
    'Serves _load_twins: identical source text already translated into this locale. Partial because only active ok rows are ever reused.';
