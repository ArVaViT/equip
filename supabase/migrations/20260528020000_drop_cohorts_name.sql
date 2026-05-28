-- =====================================================================
-- Phase 5e1 — drop ``cohorts.name`` column.
--
-- The column was the legacy storage for the cohort's display name.
-- After Phase 3 backfill, every live cohort's name is mirrored in
-- ``content_versions`` (entity_type='cohort', field='title') which
-- becomes the single source of truth.
--
-- Read path: ``api/v1/cohorts.py::_fetch_cohort_names`` bulk-queries cv.
-- Write path: ``_write_cohort_name`` takes explicit text + admin
-- locale fallback (cohorts have no parent course locale).
--
-- Irreversibility: column data is gone after this migration. A
-- pre-merge dump (``pg_dump --table=cohorts --column-inserts``) is the
-- rollback artefact. PITR also works inside the retention window.
-- =====================================================================

ALTER TABLE cohorts DROP COLUMN IF EXISTS name;
