-- Named leases for background work that must not run twice at once.
--
-- The idle translation tick sweeps the Daily Challenge question pool. Ticks
-- overlap by design (a cron every minute, functions allowed five), so the
-- sweep took pg_try_advisory_xact_lock — and the sweep commits after every
-- question, which releases a transaction-scoped lock at the first commit.
-- From the second question on, an overlapping tick could take the "lock" and
-- translate the same question: the double work and the UniqueViolation the
-- lock was added to stop. A session-scoped advisory lock is not an answer
-- here either: Supabase's pooler hands the server connection to another
-- client after each transaction, lock and all.
--
-- A lease is a row: claimed by an upsert that only succeeds when the row is
-- absent or expired, released by its holder, and harmless if the holder dies
-- (it expires). Only the backend's own connection touches it.

CREATE TABLE IF NOT EXISTS public.worker_leases (
  name text PRIMARY KEY,
  holder uuid NOT NULL,
  expires_at timestamptz NOT NULL
);

ALTER TABLE public.worker_leases ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.worker_leases FROM anon, authenticated;
