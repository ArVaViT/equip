-- Supabase migration: dc_questions_consolidate_select_policies
-- Version: 20260603140200
--
-- Supabase performance advisor 0006_multiple_permissive_policies:
-- ``daily_challenge_questions`` carries TWO permissive SELECT
-- policies for the ``authenticated`` role
-- (``dc_questions_select_archive`` + ``dc_questions_select_editorial``).
-- Postgres has to evaluate BOTH per query, OR them, then apply the
-- result — that's avoidable overhead.
--
-- Fix: collapse to one policy whose USING expression is the same OR
-- the two used to compute implicitly. Semantics unchanged:
--   * Published, scheduled, non-rejected questions visible to everyone
--     authenticated (the archive surface).
--   * Teachers + admins see everything (the editorial dashboard).

DROP POLICY IF EXISTS dc_questions_select_archive ON public.daily_challenge_questions;
DROP POLICY IF EXISTS dc_questions_select_editorial ON public.daily_challenge_questions;

CREATE POLICY dc_questions_select
    ON public.daily_challenge_questions
    FOR SELECT
    TO authenticated
    USING (
        -- Editorial: teachers + admins always see all rows.
        (EXISTS (
            SELECT 1
            FROM public.profiles p
            WHERE p.id = (SELECT auth.uid())
              AND p.role = ANY (ARRAY['teacher'::text, 'admin'::text])
        ))
        OR
        -- Public archive: published + not-rejected, on or after a
        -- scheduled day that already arrived.
        (
            status = 'published'
            AND rejected = false
            AND EXISTS (
                SELECT 1
                FROM public.daily_challenge_schedule s
                WHERE s.question_id = daily_challenge_questions.id
                  AND s.challenge_date <= ((now() AT TIME ZONE 'UTC')::date)
            )
        )
    );
