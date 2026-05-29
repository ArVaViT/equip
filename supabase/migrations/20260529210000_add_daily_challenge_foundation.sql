-- =====================================================================
-- Phase 5c — Daily Challenge MVP foundation.
--
-- Five tables. Platform-wide (one question per UTC date for everyone).
-- Question types: multiple_choice + true_false ONLY (auto-validatable by
-- option_id; no string-match fuzziness). Pre-built bank — editorial team
-- creates questions; daily rotation picks from the approved pool.
-- =====================================================================
--
-- Architecture decisions locked 2026-05-29 by Vadym after a 4-agent
-- parallel design review (memory:
-- project-equip-daily-challenge-decisions.md). Highlights load-bearing
-- to read before changing this schema:
--
--   1. Platform-wide, NOT school-scoped. challenge_date is the natural
--      key on the schedule table — exactly one question per UTC date.
--   2. Streak = YouVersion-style. ANY submission (correct or wrong)
--      counts as a streak day. No grace tokens in MVP — if streak
--      semantics ever tighten, that's an additive migration.
--   3. No XP table in MVP. Vadym wants XP later; deliberately deferred
--      until the design is locked. Add via append-only migration.
--   4. 5-stage editorial pipeline before a question publishes:
--        draft -> scripture_validated -> doctrinally_reviewed
--              -> bilingually_reviewed -> pilot_passed -> published.
--      Rejection is orthogonal to stage progression — captured by
--      ``rejected`` boolean + ``rejection_reason`` text columns. A
--      rejected question stays at whatever stage killed it but is
--      excluded from publishing forever.
--   5. Translatable text lives in ``content_versions`` via new entity
--      types ``daily_challenge_question`` + ``daily_challenge_option``.
--      No text columns on the tables below. Source-locale detection +
--      dual-write follow the existing pattern used by courses, quizzes,
--      announcements.
--   6. Canonical answer-key text is KJV (1769) + Synodal (1876). The
--      correct option must be defensible from BOTH translations. That
--      rule is enforced in the editorial pipeline (Stage 2 =
--      scripture_validated), not by the DB.
--   7. Archive = full calendar of past questions; users can replay
--      historical questions. Archive attempts carry zero streak impact
--      via the ``is_archive`` flag + the partial unique index that only
--      enforces uniqueness on live attempts.
--
-- This migration ships the FOUNDATION (tables, RLS, indexes,
-- constraints). The 6-round AI question-generation flow + its audit
-- trail table land in a follow-up migration in Sprint 3. Service layer
-- + API endpoints land in Sprint 2.

-- ---------------------------------------------------------------------
-- 1. daily_challenge_questions
-- ---------------------------------------------------------------------
-- The editorial bank. Translatable fields (question_text, explanation)
-- live in content_versions — entity_type='daily_challenge_question'.
-- The ``status`` column drives the editorial workflow; the ``rejected``
-- flag is the orthogonal kill-switch.

CREATE TABLE daily_challenge_questions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Auto-validatable types only. Adding new types is an enum bump
    -- via append-only migration; the CHECK constraint catches drift
    -- against the Pydantic ``Literal`` at the API edge.
    question_type   TEXT NOT NULL
                    CHECK (question_type IN ('multiple_choice', 'true_false')),

    -- Forward progression through the editorial pipeline. Status
    -- NEVER moves backward; a rejected question stays at its current
    -- stage but with ``rejected=true``. Only ``status='published'
    -- AND rejected=false`` is eligible to be scheduled.
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN (
                        'draft',
                        'scripture_validated',
                        'doctrinally_reviewed',
                        'bilingually_reviewed',
                        'pilot_passed',
                        'published',
                        'archived'
                    )),

    -- Orthogonal to ``status``. When ``rejected=true``, the question is
    -- terminally out of the rotation regardless of stage. The reason
    -- is free-text rather than an enum so the editor can capture a
    -- 1-2 line note ("answer ambiguous in NIV", "doctrinal lean toward
    -- dispensationalism") without us pre-enumerating every shape.
    rejected         BOOLEAN NOT NULL DEFAULT FALSE,
    rejection_reason TEXT,
    rejected_by      UUID REFERENCES profiles(id) ON DELETE SET NULL,
    rejected_at      TIMESTAMPTZ,

    -- Lifecycle audit: who promoted to each terminal-ish stage?
    -- ``published_at`` doubles as the second gate that scheduling
    -- enforces. ``approved_*`` is the moment the editor flipped the
    -- bilingually_reviewed → pilot_passed → published terminal sequence;
    -- the schedule trigger needs to see published_at set.
    published_at    TIMESTAMPTZ,
    published_by    UUID REFERENCES profiles(id) ON DELETE SET NULL,

    -- Author / provenance. ``created_by`` may be NULL when an AI-only
    -- draft hasn't been claimed by a human yet (Sprint 3).
    created_by      UUID REFERENCES profiles(id) ON DELETE SET NULL,

    -- Scripture anchor — every question must cite a verse range. Used
    -- by Stage 2 (scripture_validated) to verify the cited passage
    -- exists and supports the answer. The bible book set is fixed
    -- across history — a 64-char text column covers UTF-8 names in
    -- both EN ('Romans') and RU ('Послание к Римлянам'). Verse numbers
    -- nullable so a question can reference a whole chapter
    -- ('Romans 8') if it really must.
    bible_book       TEXT NOT NULL,
    bible_chapter    INT NOT NULL CHECK (bible_chapter > 0),
    bible_verse_from INT CHECK (bible_verse_from IS NULL OR bible_verse_from > 0),
    bible_verse_to   INT CHECK (bible_verse_to IS NULL
                                OR (bible_verse_from IS NOT NULL
                                    AND bible_verse_to >= bible_verse_from)),

    -- Editorial category. Drives the launch-mix composition (see Agent
    -- C's brief — ~40% narrative, ~35% exegesis, ~15% cross-reference,
    -- ~10% historical-cultural). No CHECK constraint because we want
    -- categories to evolve without a migration; Pydantic Literal at
    -- the API edge is the gate.
    category         TEXT,

    -- Source locale of the human-authored text. Detected by the
    -- write helper via ``detect_locale`` on question text +
    -- explanation, same pattern as ``courses.source_locale``.
    source_locale    TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- "Show me drafts / scripture-validated / ... / published" editorial
-- queue. Partial keeps the working set hot — archived + rejected
-- rows are the cold tail.
CREATE INDEX ix_dc_questions_status_created
    ON daily_challenge_questions (status, created_at DESC)
    WHERE rejected = FALSE AND status <> 'archived';

-- Schedulable pool: only published, not rejected, not archived. Drives
-- the editorial "pick a question for date X" UI and the schedule
-- trigger.
CREATE INDEX ix_dc_questions_publishable
    ON daily_challenge_questions (published_at)
    WHERE status = 'published' AND rejected = FALSE;

-- Reverse-lookup from a scripture reference. Used by the editorial
-- "have we already written a question on this passage?" duplicate
-- check.
CREATE INDEX ix_dc_questions_scripture
    ON daily_challenge_questions (bible_book, bible_chapter, bible_verse_from);

-- ---------------------------------------------------------------------
-- 2. daily_challenge_options
-- ---------------------------------------------------------------------
-- One row per option. ``option_text`` lives in ``content_versions``
-- (entity_type='daily_challenge_option', field='option_text'). For
-- true_false questions: exactly 2 options, ``order_index`` 0 = True /
-- 1 = False. For multiple_choice: 3-6 options typically; ``order_index``
-- determines render order. Application-level invariant: exactly one
-- option per question has ``is_correct=true``. Not a DB trigger because
-- it would fight transactional INSERTs that build the question +
-- options in one batch; the service layer enforces it at commit time.

CREATE TABLE daily_challenge_options (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id   UUID NOT NULL REFERENCES daily_challenge_questions(id)
                    ON DELETE CASCADE,
    is_correct    BOOLEAN NOT NULL DEFAULT FALSE,
    -- Bounded so a malformed import can't blow up the render. Six
    -- options is more than any Bible MCQ should ever need; tighter at
    -- the Pydantic edge.
    order_index   INT NOT NULL DEFAULT 0
                    CHECK (order_index BETWEEN 0 AND 5),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_dc_options_question
    ON daily_challenge_options (question_id, order_index);

-- ---------------------------------------------------------------------
-- 3. daily_challenge_schedule
-- ---------------------------------------------------------------------
-- One row per UTC date. PK is the date itself — at most one question
-- live per day. The schedule trigger enforces the "only
-- published+non-rejected questions can be scheduled" gate; ON DELETE
-- RESTRICT on the FK to questions ensures a scheduled question can't
-- vanish under the day it's scheduled for.

CREATE TABLE daily_challenge_schedule (
    challenge_date  DATE PRIMARY KEY,
    question_id     UUID NOT NULL REFERENCES daily_challenge_questions(id)
                    ON DELETE RESTRICT,
    scheduled_by    UUID REFERENCES profiles(id) ON DELETE SET NULL,
    scheduled_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Reverse lookup: "show me every date this question has been on".
-- Editorial uses this to surface re-use (we may eventually allow a
-- question to be re-aired after a long cooldown).
CREATE INDEX ix_dc_schedule_question
    ON daily_challenge_schedule (question_id);

-- Trigger-enforced "only published, not rejected, not archived
-- questions can be scheduled". Done via a trigger because Postgres
-- CHECK constraints cannot reference another table's columns.
CREATE OR REPLACE FUNCTION dc_schedule_assert_publishable()
RETURNS trigger AS $$
DECLARE
    q_status TEXT;
    q_rejected BOOLEAN;
    q_pub TIMESTAMPTZ;
BEGIN
    SELECT status, rejected, published_at
      INTO q_status, q_rejected, q_pub
      FROM daily_challenge_questions
     WHERE id = NEW.question_id;

    IF q_status IS DISTINCT FROM 'published' THEN
        RAISE EXCEPTION 'daily_challenge_schedule.question_id % is not at status=published (current: %)',
            NEW.question_id, q_status
            USING ERRCODE = 'check_violation';
    END IF;
    IF q_rejected THEN
        RAISE EXCEPTION 'daily_challenge_schedule.question_id % is rejected; cannot schedule', NEW.question_id
            USING ERRCODE = 'check_violation';
    END IF;
    IF q_pub IS NULL THEN
        RAISE EXCEPTION 'daily_challenge_schedule.question_id % has NULL published_at', NEW.question_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER dc_schedule_publishable_guard
    BEFORE INSERT OR UPDATE OF question_id ON daily_challenge_schedule
    FOR EACH ROW EXECUTE FUNCTION dc_schedule_assert_publishable();

-- ---------------------------------------------------------------------
-- 4. daily_challenge_attempts
-- ---------------------------------------------------------------------
-- Per-user attempt. Live attempts (is_archive=false) impact the
-- streak; archive replays (is_archive=true) never do — that's the
-- "you can revisit yesterday's question without resetting your
-- streak math" guarantee.

CREATE TABLE daily_challenge_attempts (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id              UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    question_id          UUID NOT NULL REFERENCES daily_challenge_questions(id)
                            ON DELETE CASCADE,
    -- For live attempts: equals daily_challenge_schedule.challenge_date
    -- (the UTC date the question was the daily question). For archive
    -- attempts: the historical date the user is replaying. Stored, not
    -- derived, so the partial unique index can include it cheaply.
    challenge_date       DATE NOT NULL,
    is_archive           BOOLEAN NOT NULL DEFAULT FALSE,
    selected_option_id   UUID REFERENCES daily_challenge_options(id) ON DELETE SET NULL,
    is_correct           BOOLEAN NOT NULL,
    -- Materialised post-attempt for observability — "what was the
    -- streak right after this submit?" The streak service writes this
    -- under the same FOR UPDATE lock as the streak row update.
    -- NULL on archive attempts (enforced by CHECK below).
    streak_after         INT,
    submitted_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Archive attempts never touch the streak.
    CHECK (NOT is_archive OR streak_after IS NULL)
);

-- The race-resolving partial unique. At most ONE live attempt per
-- (user_id, challenge_date) — the second INSERT raises IntegrityError
-- and the route returns the existing attempt. Archive replays are
-- allowed unlimited times so the partial WHERE excludes them.
CREATE UNIQUE INDEX uniq_dc_attempts_live_per_day
    ON daily_challenge_attempts (user_id, challenge_date)
    WHERE is_archive = FALSE;

-- Profile / history view.
CREATE INDEX ix_dc_attempts_user_date
    ON daily_challenge_attempts (user_id, challenge_date DESC);

-- "How hard was this question?" editorial difficulty heatmap.
CREATE INDEX ix_dc_attempts_question
    ON daily_challenge_attempts (question_id);

-- ---------------------------------------------------------------------
-- 5. daily_challenge_streaks
-- ---------------------------------------------------------------------
-- Per-user counter. One row per user — created lazily on first
-- attempt via ON CONFLICT DO UPDATE in the streak service.
--
-- YouVersion-style semantics (Vadym 2026-05-29):
--   * Any submission (right or wrong) counts as engagement.
--   * On submit: if last_engaged_date < challenge_date, increment
--     current_streak by 1 (idempotent via uniqueness check).
--   * If last_engaged_date < challenge_date - 1 (i.e. missed at least
--     one full day in between), current_streak resets to 1 (today's
--     attempt is itself the start of a new streak).
--   * No grace tokens in MVP — strictness is acceptable because the
--     bar for "engagement" is just attempting (not getting it right).
--   * longest_streak tracks all-time so the user has a permanent
--     accomplishment even after a reset.
--   * No XP. Vadym wants XP added later via an additive migration
--     once the rules are designed; intentionally absent here.

CREATE TABLE daily_challenge_streaks (
    user_id                  UUID PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
    current_streak           INT NOT NULL DEFAULT 0
                                CHECK (current_streak >= 0),
    longest_streak           INT NOT NULL DEFAULT 0
                                CHECK (longest_streak >= 0),
    last_engaged_date        DATE,
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Cohort-style "everyone with active recent streaks" query. Used by
-- the at-risk notification job: "find users with current_streak >= 3
-- who haven't engaged today." Partial keeps the index tight.
CREATE INDEX ix_dc_streaks_last_engaged
    ON daily_challenge_streaks (last_engaged_date)
    WHERE current_streak >= 1;

-- =====================================================================
-- Row-Level Security
-- =====================================================================
--
-- service_role bypasses RLS automatically — backend writes flow
-- through it. The policies below cover the PostgREST surface that an
-- authenticated user JWT can hit directly.

ALTER TABLE daily_challenge_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_challenge_options   ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_challenge_schedule  ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_challenge_attempts  ENABLE ROW LEVEL SECURITY;
ALTER TABLE daily_challenge_streaks   ENABLE ROW LEVEL SECURITY;

-- Questions: students see archive (past dates' published questions) +
-- today's question (but the backend slices off ``options.is_correct``
-- and the answer-key fields before responding). Editorial role (teacher
-- + admin) sees everything including drafts. The "today's question"
-- read is routed through the backend service_role for the answer-key
-- redaction; the direct PostgREST read is for the archive surface.

CREATE POLICY dc_questions_select_archive ON daily_challenge_questions
    FOR SELECT TO authenticated
    USING (
        status = 'published'
        AND rejected = FALSE
        AND EXISTS (
            SELECT 1 FROM daily_challenge_schedule s
             WHERE s.question_id = daily_challenge_questions.id
               AND s.challenge_date <= (now() AT TIME ZONE 'UTC')::date
        )
    );

CREATE POLICY dc_questions_select_editorial ON daily_challenge_questions
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM profiles p
             WHERE p.id = (SELECT auth.uid())
               AND p.role IN ('teacher', 'admin')
        )
    );

-- Options: piggy-back on the parent question's visibility.
CREATE POLICY dc_options_select_via_question ON daily_challenge_options
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM daily_challenge_questions q
             WHERE q.id = daily_challenge_options.question_id
               AND (
                    (q.status = 'published' AND q.rejected = FALSE
                     AND EXISTS (
                         SELECT 1 FROM daily_challenge_schedule s
                          WHERE s.question_id = q.id
                            AND s.challenge_date <= (now() AT TIME ZONE 'UTC')::date
                     ))
                    OR EXISTS (
                         SELECT 1 FROM profiles p
                          WHERE p.id = (SELECT auth.uid())
                            AND p.role IN ('teacher', 'admin')
                     )
               )
        )
    );

-- Schedule: students see past + today (today's question_id is needed
-- to JOIN on options for rendering). The backend redacts the answer
-- key in the API response.
CREATE POLICY dc_schedule_select_visible ON daily_challenge_schedule
    FOR SELECT TO authenticated
    USING (
        challenge_date <= (now() AT TIME ZONE 'UTC')::date
        OR EXISTS (
            SELECT 1 FROM profiles p
             WHERE p.id = (SELECT auth.uid())
               AND p.role IN ('teacher', 'admin')
        )
    );

-- Attempts + streaks: each user sees only their own row.
CREATE POLICY dc_attempts_select_own ON daily_challenge_attempts
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

CREATE POLICY dc_streaks_select_own ON daily_challenge_streaks
    FOR SELECT TO authenticated
    USING (user_id = (SELECT auth.uid()));

-- All writes go through the backend (service_role). Belt-and-suspenders
-- REVOKE mirrors the 20260515184512_rls_tighten_write_policies.sql
-- pattern.
REVOKE INSERT, UPDATE, DELETE ON daily_challenge_questions FROM authenticated, anon;
REVOKE INSERT, UPDATE, DELETE ON daily_challenge_options   FROM authenticated, anon;
REVOKE INSERT, UPDATE, DELETE ON daily_challenge_schedule  FROM authenticated, anon;
REVOKE INSERT, UPDATE, DELETE ON daily_challenge_attempts  FROM authenticated, anon;
REVOKE INSERT, UPDATE, DELETE ON daily_challenge_streaks   FROM authenticated, anon;

-- Column-level defence on the answer key. Even if a student knows
-- today's question_id and bypasses the API to query options directly
-- via PostgREST, the ``is_correct`` column is hidden from them. The
-- backend, running under service_role, still sees the column.
-- Without this, an RLS SELECT policy that lets authenticated users
-- read options (necessary for archive rendering) would leak the
-- answer key.
--
-- Editorial role (teacher + admin) needs ``is_correct`` to manage the
-- question. Granting back to authenticated WHERE role IN
-- ('teacher','admin') is not expressible via column-level GRANT — RLS
-- already controls which rows they see, but column-level grants are
-- per-role, not per-policy. The right pattern: keep ``is_correct``
-- revoked from ``authenticated`` entirely, and have the editorial UI
-- read through a backend route (which uses service_role).
REVOKE SELECT (is_correct) ON daily_challenge_options FROM authenticated, anon;
