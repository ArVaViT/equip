-- The Daily Challenge editorial reads are platform staff's, not every teacher's.
--
-- PR #1392 (2026-10-15) moved every editorial route to `require_admin`: since
-- organizations, "teacher" means a teacher of any school, and the card is the
-- platform's. Four RLS policies still said `role IN ('teacher', 'admin')`, so
-- any teacher's own session could read straight from PostgREST what the API
-- now refuses them: tomorrow's schedule, unpublished and rejected questions,
-- and the editorial event log.
--
-- Nothing legitimate reads these tables as a teacher: the frontend goes
-- through the API, and the backend connects as `postgres`, which RLS does not
-- apply to. Production check on 2026-10-15: only the platform admin has ever
-- acted on them.
--
-- `daily_challenge_options` has no SELECT grant for `authenticated` at all
-- (the answer key; `supabase/ci/rls_assertions.sql` probes it); its policy is
-- narrowed too so a future grant does not reopen it to teachers.
--
-- ALTER POLICY rewrites only the expression: idempotent, no lock beyond a
-- brief one on each table's catalog entry.

ALTER POLICY dc_schedule_select_visible ON public.daily_challenge_schedule
  USING (
    challenge_date <= (now() AT TIME ZONE 'UTC')::date
    OR public.is_platform_staff()
  );

ALTER POLICY dc_questions_select ON public.daily_challenge_questions
  USING (
    public.is_platform_staff()
    OR (
      status = 'published'
      AND rejected = false
      AND EXISTS (
        SELECT 1
        FROM public.daily_challenge_schedule s
        WHERE s.question_id = daily_challenge_questions.id
          AND s.challenge_date <= (now() AT TIME ZONE 'UTC')::date
      )
    )
  );

ALTER POLICY dc_options_select_via_question ON public.daily_challenge_options
  USING (
    EXISTS (
      SELECT 1
      FROM public.daily_challenge_questions q
      WHERE q.id = daily_challenge_options.question_id
        AND (
          (
            q.status = 'published'
            AND q.rejected = false
            AND EXISTS (
              SELECT 1
              FROM public.daily_challenge_schedule s
              WHERE s.question_id = q.id
                AND s.challenge_date <= (now() AT TIME ZONE 'UTC')::date
            )
          )
          OR public.is_platform_staff()
        )
    )
  );

ALTER POLICY dc_q_events_select_editorial ON public.daily_challenge_question_events
  USING (public.is_platform_staff());
