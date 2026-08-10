-- RLS / privilege assertions, run AS the authenticated role against the
-- recreated prod schema + grants. Any "SECURITY HOLE" RAISE (a forbidden
-- write that unexpectedly succeeds) aborts the job. A positive control proves
-- the harness isn't simply failing every statement.
--
-- Seeding runs as the superuser/owner (RLS does not apply to the table owner),
-- then we SET ROLE authenticated and set the JWT-sub GUC to become "student X".

\set ON_ERROR_STOP on
\set student '11111111-1111-1111-1111-111111111111'

INSERT INTO auth.users (id, email) VALUES (:'student', 'student@test.local');
INSERT INTO public.profiles (id, email, role) VALUES (:'student', 'student@test.local', 'student');
-- A second, unrelated user to prove cross-tenant reads are blocked.
INSERT INTO auth.users (id, email) VALUES ('22222222-2222-2222-2222-222222222222', 'other@test.local');
INSERT INTO public.profiles (id, email, role) VALUES ('22222222-2222-2222-2222-222222222222', 'other@test.local', 'student');

-- Become the logged-in student. The GUC is set at session level (as superuser)
-- so it survives SET ROLE; auth.uid() reads it.
SET request.jwt.claim.sub = '11111111-1111-1111-1111-111111111111';
SET ROLE authenticated;

-- 1) certificates: authenticated has no UPDATE privilege -> a student cannot
--    self-approve a certificate.
DO $$
BEGIN
  UPDATE public.certificates SET status = 'approved';
  RAISE EXCEPTION 'SECURITY HOLE: authenticated UPDATE on certificates succeeded';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: certificates UPDATE denied (privilege)';
END $$;

-- 2) quiz_attempts: no UPDATE privilege -> a student cannot tamper with a score.
DO $$
BEGIN
  UPDATE public.quiz_attempts SET score = 100;
  RAISE EXCEPTION 'SECURITY HOLE: authenticated UPDATE on quiz_attempts succeeded';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: quiz_attempts UPDATE denied (privilege)';
END $$;

-- 3) student_grades: SELECT-only -> a student cannot write their own grade.
DO $$
BEGIN
  INSERT INTO public.student_grades (course_id, student_id)
  VALUES ('any-course', '11111111-1111-1111-1111-111111111111');
  RAISE EXCEPTION 'SECURITY HOLE: authenticated INSERT on student_grades succeeded';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: student_grades INSERT denied (privilege)';
END $$;

-- 4) profiles role escalation: the own row passes RLS, but the
--    immutable-fields trigger must block a role change.
DO $$
BEGIN
  UPDATE public.profiles SET role = 'admin'
  WHERE id = '11111111-1111-1111-1111-111111111111';
  RAISE EXCEPTION 'SECURITY HOLE: authenticated escalated profiles.role to admin';
EXCEPTION
  WHEN check_violation THEN RAISE NOTICE 'OK: profiles.role escalation blocked (trigger)';
END $$;

-- 5) positive control: a legitimate own-row safe-field write MUST succeed.
DO $$
DECLARE n int;
BEGIN
  UPDATE public.profiles SET full_name = 'Renamed'
  WHERE id = '11111111-1111-1111-1111-111111111111';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN
    RAISE EXCEPTION 'HARNESS BROKEN: own-row full_name update affected % row(s), expected 1', n;
  END IF;
  RAISE NOTICE 'OK: own-row safe-field update succeeded (positive control)';
END $$;

-- 6) answer-key tables: a client (authenticated) must have NO direct read
--    access. The answer key (is_correct) is served stripped via the backend;
--    a direct client read would leak it before submission.
DO $$
BEGIN
  PERFORM 1 FROM public.quiz_options LIMIT 1;
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can SELECT quiz_options (answer key leak)';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: quiz_options direct read denied';
END $$;

DO $$
BEGIN
  PERFORM 1 FROM public.daily_challenge_options LIMIT 1;
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can SELECT daily_challenge_options (answer key leak)';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: daily_challenge_options direct read denied';
END $$;

-- content_versions is the sole store of ALL course text (entity text columns
-- were dropped in Phase 5); a direct client read would expose unpublished and
-- cohort-gated content. Served exclusively through the backend.
DO $$
BEGIN
  PERFORM 1 FROM public.content_versions LIMIT 1;
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can SELECT content_versions (full content scrape)';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: content_versions direct read denied';
END $$;

-- 7) tamper-proof tables: a client must not be able to write them directly
--    (backend-managed via the service role).
DO $$
BEGIN
  INSERT INTO public.audit_logs (action, resource_id, resource_type)
  VALUES ('forge', 'x', 'user');
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can INSERT audit_logs (forge audit trail)';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: audit_logs INSERT denied';
END $$;

DO $$
BEGIN
  INSERT INTO public.quiz_extra_attempts (quiz_id, user_id, granted_by)
  VALUES (gen_random_uuid(), '11111111-1111-1111-1111-111111111111', '11111111-1111-1111-1111-111111111111');
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can self-grant quiz_extra_attempts';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: quiz_extra_attempts INSERT denied';
END $$;

DO $$
BEGIN
  UPDATE public.quiz_answers SET is_correct = true;
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can UPDATE quiz_answers (tamper a submitted answer)';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: quiz_answers UPDATE denied';
END $$;

-- 8) server-only writes lockdown (migration 20260611200000): the entire
--    client write surface is revoked except profiles safe-field UPDATE.
--    Each probe is the concrete forgery the 2026-06-11 audit flagged.
DO $$
BEGIN
  INSERT INTO public.certificates (user_id, status, certificate_number)
  VALUES ('11111111-1111-1111-1111-111111111111', 'approved', 'CERT-FORGED00001');
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can INSERT an approved certificate (forge a credential)';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: certificates INSERT denied';
END $$;

DO $$
BEGIN
  INSERT INTO public.quiz_attempts (quiz_id, user_id, score, max_score, passed)
  VALUES (gen_random_uuid(), '11111111-1111-1111-1111-111111111111', 100, 100, true);
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can INSERT quiz_attempts (fabricate a passed attempt)';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: quiz_attempts INSERT denied';
END $$;

DO $$
BEGIN
  INSERT INTO public.quiz_answers (attempt_id, question_id, is_correct, points_earned)
  VALUES (gen_random_uuid(), gen_random_uuid(), true, 100);
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can INSERT quiz_answers (fabricate correct answers)';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: quiz_answers INSERT denied';
END $$;

DO $$
BEGIN
  INSERT INTO public.chapter_progress (user_id, chapter_id, completed)
  VALUES ('11111111-1111-1111-1111-111111111111', gen_random_uuid(), true);
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can INSERT chapter_progress (fake course progress)';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: chapter_progress INSERT denied';
END $$;

DO $$
BEGIN
  UPDATE public.chapter_progress SET completed = true;
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can UPDATE chapter_progress';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: chapter_progress UPDATE denied';
END $$;

DO $$
BEGIN
  INSERT INTO public.assignment_submissions (assignment_id, student_id)
  VALUES (gen_random_uuid(), '11111111-1111-1111-1111-111111111111');
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can INSERT assignment_submissions';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: assignment_submissions INSERT denied';
END $$;

DO $$
BEGIN
  DELETE FROM public.enrollments;
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can DELETE enrollments';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: enrollments DELETE denied';
END $$;

DO $$
BEGIN
  INSERT INTO public.course_reviews (course_id, user_id, rating)
  VALUES (gen_random_uuid(), '11111111-1111-1111-1111-111111111111', 5);
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can INSERT course_reviews (bypass API validation)';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: course_reviews INSERT denied';
END $$;

DO $$
BEGIN
  UPDATE public.notifications SET is_read = true;
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can UPDATE notifications directly';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: notifications UPDATE denied';
END $$;

DO $$
BEGIN
  INSERT INTO public.courses (created_by, status)
  VALUES ('11111111-1111-1111-1111-111111111111', 'draft');
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can INSERT courses directly';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: courses INSERT denied';
END $$;

-- 9) cross-tenant SELECT: the profiles_select_self policy must hide another
--    user's row entirely (RLS filters rather than errors, so assert 0 rows).
DO $$
DECLARE visible int;
BEGIN
  SELECT count(*) INTO visible
  FROM public.profiles
  WHERE id = '22222222-2222-2222-2222-222222222222';
  IF visible <> 0 THEN
    RAISE EXCEPTION 'SECURITY HOLE: authenticated can read another user''s profile row (% visible)', visible;
  END IF;
  -- And the own row IS visible (proves the policy isn't just hiding everything).
  SELECT count(*) INTO visible
  FROM public.profiles
  WHERE id = '11111111-1111-1111-1111-111111111111';
  IF visible <> 1 THEN
    RAISE EXCEPTION 'HARNESS BROKEN: own profile row not visible (% rows)', visible;
  END IF;
  RAISE NOTICE 'OK: profiles SELECT is self-only (cross-tenant read blocked)';
END $$;

-- 10) org_settings: institutional configuration — the school's default scheme,
--     pass threshold and grade bands — is backend-only. The SPA reads it
--     through the grading-config endpoint, never straight from the table, so
--     `authenticated` must have no privilege on it at all. A leak here would
--     also expose the school's identity fields to any signed-in user.
DO $$
BEGIN
  PERFORM * FROM public.org_settings;
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can SELECT org_settings';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: org_settings SELECT denied (privilege)';
END $$;

DO $$
BEGIN
  UPDATE public.org_settings SET default_pass_threshold = 0;
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can UPDATE org_settings';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: org_settings UPDATE denied (privilege)';
END $$;

-- 11) invitations: a token is a bearer capability and the email column is PII.
--     Neither belongs in a PostgREST-reachable table — a signed-in student who
--     could SELECT here would be able to redeem someone else's teacher invite.
DO $$
BEGIN
  PERFORM * FROM public.invitations;
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can SELECT invitations (tokens are bearer secrets)';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: invitations SELECT denied (privilege)';
END $$;

DO $$
BEGIN
  INSERT INTO public.invitations (email, role, token)
  VALUES ('self@test.local', 'teacher', 'forged-token');
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can INSERT invitations (self-promotion to teacher)';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: invitations INSERT denied (privilege)';
END $$;

-- 12) grade_exemptions: an exemption removes a piece of work from a student's
--     grade *and* from their progress, which is the shortest path anyone has to
--     a certificate they did not earn — insert two rows and the requirement
--     disappears without a single score being touched. Backend-only, like every
--     other table that decides an official result.
DO $$
BEGIN
  PERFORM * FROM public.grade_exemptions;
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can SELECT grade_exemptions';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: grade_exemptions SELECT denied (privilege)';
END $$;

DO $$
BEGIN
  INSERT INTO public.grade_exemptions (student_id, course_id, item_type, item_id)
  VALUES (
    '11111111-1111-1111-1111-111111111111',
    (SELECT id FROM public.courses LIMIT 1),
    'assignment',
    '22222222-2222-2222-2222-222222222222'
  );
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can INSERT grade_exemptions (self-excuse from coursework)';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: grade_exemptions INSERT denied (privilege)';
END $$;

-- 13) grade_sheets / grade_sheet_rows: a signed ведомость is the document a
--     director puts their name on. A student able to write here would be
--     writing their own line into it; one able to read it would see every
--     classmate's result, which no student surface has ever exposed.
DO $$
BEGIN
  PERFORM * FROM public.grade_sheet_rows;
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can SELECT grade_sheet_rows (every classmate result)';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: grade_sheet_rows SELECT denied (privilege)';
END $$;

DO $$
BEGIN
  INSERT INTO public.grade_sheets (course_id, grading_scheme)
  VALUES ((SELECT id FROM public.courses LIMIT 1), 'letter');
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can INSERT grade_sheets (forge a signed document)';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: grade_sheets INSERT denied (privilege)';
END $$;

RESET ROLE;
SELECT 'RLS policy assertions passed' AS result;
