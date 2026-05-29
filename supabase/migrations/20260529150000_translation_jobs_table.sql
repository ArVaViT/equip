-- Phase 5av: translation_jobs queue table.
--
-- Why
-- ===
-- Today publishing a course with 100 chapter blocks fires 100 Gemini
-- calls SYNCHRONOUSLY in the request path. The teacher's POST blocks
-- on the slowest Gemini round-trip; the Vercel function risks the
-- 60-second limit; a partial failure leaves the route owning broken
-- session state.
--
-- The right shape is a queue: publish enqueues ONE row (cheap), and
-- a cron-driven worker drains the queue out-of-band. Postgres gives
-- us everything we need without a new service:
--
--   * Durable state survives Vercel cold starts.
--   * ``FOR UPDATE SKIP LOCKED`` provides correct concurrency without
--     a Redis-lite dance.
--   * Worker observability is one SELECT.
--   * Retry semantics are explicit (``attempts`` counter, terminal
--     ``failed_permanent`` state mirroring ``content_versions``).
--
-- Schema
-- ======
-- One row per publish-triggered translation request. The worker
-- claims a row by flipping ``status`` from ``queued`` to ``processing``;
-- on success it writes ``done`` + ``finished_at``; on failure it
-- bumps ``attempts`` and either re-queues (``failed``) or terminates
-- (``failed_permanent`` after the same 5-attempt cap as cv rows).
--
-- The ``status`` enum mirrors ``content_versions.status`` plus an
-- explicit ``processing`` state because a queue distinguishes
-- "currently being worked on" from "waiting to be picked up", which
-- the cv lifecycle doesn't need.

CREATE TABLE translation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'processing', 'done', 'failed', 'failed_permanent')),
    enqueued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    attempts INT NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error TEXT,
    requested_by UUID REFERENCES profiles(id) ON DELETE SET NULL
);

-- Worker poll predicate: claim the oldest queued job. The partial
-- index keeps the index hot on the rare ``queued`` set instead of
-- bloating with every historical ``done`` row.
CREATE INDEX ix_translation_jobs_queued
    ON translation_jobs (enqueued_at)
    WHERE status = 'queued';

-- Course-level observability: 'show me the recent jobs for course X'
-- + course-deletion CASCADE walks this index.
CREATE INDEX ix_translation_jobs_course
    ON translation_jobs (course_id, enqueued_at DESC);

-- Worker liveness signal: jobs stuck in ``processing`` for too long
-- (Vercel function killed mid-flight) need to be re-queued by a
-- janitor pass. Surface them cheaply.
CREATE INDEX ix_translation_jobs_processing
    ON translation_jobs (started_at)
    WHERE status = 'processing';
