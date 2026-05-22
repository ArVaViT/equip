-- ============================================================================
-- Ensure ``certificates.cohort_id`` carries a FK to ``cohorts(id)``.
-- ----------------------------------------------------------------------------
-- Audit found: the SQLAlchemy model declared ``cohort_id`` as a plain
-- ``Mapped[uuid.UUID | None]`` with no ``ForeignKey(…)``, so the CI
-- schema-smoke job that materialises models against a fresh Postgres did
-- not emit the FK either. The live prod DB does have a FK
-- (``certificates_cohort_id_fkey`` ON DELETE SET NULL), added implicitly
-- during the cohort-top-level rollout, but we want the model + smoke to
-- agree so the next person reading the schema doesn't see an orphan-risk
-- column.
--
-- This migration is idempotent: if the constraint is already in place
-- (current prod), it's a no-op; if it was somehow dropped or absent on a
-- branch DB, we recreate it with the desired shape.
-- ============================================================================

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'certificates_cohort_id_fkey'
      AND conrelid = 'public.certificates'::regclass
  ) THEN
    ALTER TABLE public.certificates
      ADD CONSTRAINT certificates_cohort_id_fkey
        FOREIGN KEY (cohort_id) REFERENCES public.cohorts(id) ON DELETE SET NULL;
  END IF;
END
$$;
