-- ============================================================================
-- Translation retry cap: add ``attempts`` counter + ``failed_permanent`` status.
-- ----------------------------------------------------------------------------
-- ``content_translations`` rows with ``status='failed'`` were retried on
-- every course publish + every reconcile cycle. A row that fails for a
-- *permanent* reason (Gemini safety-filter trip, content too large, bad
-- encoding) therefore burned a paid API call per retry indefinitely.
--
-- The fix is two-part:
--   1. Add an ``attempts INTEGER NOT NULL DEFAULT 0`` column. The
--      orchestrator increments it on every failed attempt.
--   2. Extend the CHECK constraint on ``status`` to allow
--      ``failed_permanent``. After ``attempts >= max_attempts`` (currently
--      5, defined in code), the orchestrator promotes the row to
--      ``failed_permanent`` and the reconcile loop skips it.
--
-- An admin / worker can re-queue a permanently-failed row by manually
-- resetting ``status='pending'`` and ``attempts=0`` (or any non-terminal
-- status; the orchestrator only treats ``failed_permanent`` as terminal).
-- ============================================================================

-- 1. Counter column. Backfills to 0 for existing rows — they have no failure
--    history yet, so they start with a clean budget.
ALTER TABLE public.content_translations
  ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;

-- 2. Replace the status CHECK to allow ``failed_permanent``.
ALTER TABLE public.content_translations
  DROP CONSTRAINT IF EXISTS content_translations_status_check;

ALTER TABLE public.content_translations
  ADD CONSTRAINT content_translations_status_check
    CHECK (status IN ('ok', 'stale', 'failed', 'failed_permanent'));
