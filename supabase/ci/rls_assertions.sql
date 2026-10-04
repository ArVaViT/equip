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


-- ---------------------------------------------------------------------
-- 14) Organizations: the backstop layer.
--
-- Steps 3 and 3b closed this in the API. These assertions prove the
-- policies hold it too, for anything that reaches Postgres as
-- `authenticated` without going through a route — which is the only
-- reason the layer exists, since the backend's service-role key bypasses
-- RLS entirely.
--
-- Seeded as the owner (RLS does not apply to the table owner), then read
-- back as a director of school A.
-- ---------------------------------------------------------------------

RESET ROLE;

\set school_a 'aaaa1111-0000-0000-0000-000000000001'
\set school_b 'bbbb2222-0000-0000-0000-000000000002'
\set director_a '33333333-3333-3333-3333-333333333333'

INSERT INTO public.organizations (id, slug, public_name)
VALUES (:'school_a', 'school-a', 'School A'), (:'school_b', 'school-b', 'School B');

INSERT INTO auth.users (id, email) VALUES (:'director_a', 'director-a@test.local');
INSERT INTO public.profiles (id, email, role, organization_id)
VALUES (:'director_a', 'director-a@test.local', 'director', :'school_a');
-- Since 20261003203000 the policies read organization_members, not the
-- column; the director holds the director membership of A that the
-- phase-1 backfill gave everyone who sat somewhere.
INSERT INTO public.organization_members (user_id, organization_id, role, joined_via)
VALUES (:'director_a', :'school_a', 'director', 'migration');

INSERT INTO public.cohorts (id, organization_id, start_date, end_date)
VALUES
  ('cccc0001-0000-0000-0000-000000000001', :'school_a', '2026-01-01', '2026-06-01'),
  ('cccc0002-0000-0000-0000-000000000002', :'school_b', '2026-01-01', '2026-06-01');

-- No title column: course text lives in content_versions.
INSERT INTO public.courses (id, status, access_mode, organization_id)
VALUES
  ('course-a-institute', 'published', 'institute', :'school_a'),
  ('course-b-institute', 'published', 'institute', :'school_b'),
  ('course-b-public',    'published', 'public',    :'school_b');

INSERT INTO public.certificates (id, organization_id, user_id, course_id, status)
VALUES
  ('dddd0001-0000-0000-0000-000000000001', :'school_a', :'director_a', 'course-a-institute', 'approved'),
  ('dddd0002-0000-0000-0000-000000000002', :'school_b', '22222222-2222-2222-2222-222222222222', 'course-b-institute', 'approved');

SET request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
SET ROLE authenticated;

DO $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM public.cohorts;
  IF n <> 1 THEN
    RAISE EXCEPTION 'SECURITY HOLE: a director sees % cohorts, expected only their own organization''s 1', n;
  END IF;
  RAISE NOTICE 'OK: cohorts scoped to the reader''s organization';
END $$;

DO $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM public.courses WHERE id = 'course-b-institute';
  IF n <> 0 THEN
    RAISE EXCEPTION 'SECURITY HOLE: another organization''s institute course is readable';
  END IF;
  RAISE NOTICE 'OK: a foreign institute course is invisible';
END $$;

DO $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM public.courses WHERE id = 'course-a-institute';
  IF n <> 1 THEN
    RAISE EXCEPTION 'BROKEN: a director cannot read their own organization''s institute course';
  END IF;
  SELECT count(*) INTO n FROM public.courses WHERE id = 'course-b-public';
  IF n <> 1 THEN
    RAISE EXCEPTION 'BROKEN: a published public course left the catalogue';
  END IF;
  RAISE NOTICE 'OK: own institute course and the public catalogue still read';
END $$;

DO $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM public.certificates
   WHERE id = 'dddd0002-0000-0000-0000-000000000002';
  IF n <> 0 THEN
    RAISE EXCEPTION 'SECURITY HOLE: another organization''s certificate is readable';
  END IF;
  SELECT count(*) INTO n FROM public.certificates
   WHERE id = 'dddd0001-0000-0000-0000-000000000001';
  IF n <> 1 THEN
    RAISE EXCEPTION 'BROKEN: a director cannot read their own organization''s certificate';
  END IF;
  RAISE NOTICE 'OK: certificates scoped to the reader''s organization';
END $$;

-- 15) profiles: the columns a client must not write.
--
-- `authenticated` holds table-level UPDATE on profiles and
-- `profiles_update_own_safe_fields` allows the own row, so every column
-- the immutable-fields trigger does not name is writable from a browser
-- holding nothing but the anon key and a session. Three were added to
-- the table after the trigger was written and are worth more than the
-- ones it already guards: `organization_id` reads another school's
-- institute courses and cohorts, `deactivated_at` un-shuts-off a closed
-- account, `onboarding_completed_at` steps over the legal consent gate.
--
-- Still the director of school A from section 14.

DO $$
BEGIN
  UPDATE public.profiles SET organization_id = 'bbbb2222-0000-0000-0000-000000000002'
  WHERE id = '33333333-3333-3333-3333-333333333333';
  RAISE EXCEPTION 'SECURITY HOLE: authenticated walked into another organization';
EXCEPTION
  WHEN check_violation THEN RAISE NOTICE 'OK: profiles.organization_id is not client-writable (trigger)';
END $$;

-- Shut the account off as the owner first: "NULL -> NULL" is not a change,
-- so an account that was never deactivated cannot prove anything here.
RESET ROLE;
UPDATE public.profiles SET deactivated_at = now()
WHERE id = '33333333-3333-3333-3333-333333333333';
SET ROLE authenticated;

DO $$
BEGIN
  UPDATE public.profiles SET deactivated_at = NULL
  WHERE id = '33333333-3333-3333-3333-333333333333';
  RAISE EXCEPTION 'SECURITY HOLE: authenticated cleared its own deactivation';
EXCEPTION
  WHEN check_violation THEN RAISE NOTICE 'OK: profiles.deactivated_at is not client-writable (trigger)';
END $$;

DO $$
BEGIN
  UPDATE public.profiles SET onboarding_completed_at = now()
  WHERE id = '33333333-3333-3333-3333-333333333333';
  RAISE EXCEPTION 'SECURITY HOLE: authenticated skipped the first-run gate';
EXCEPTION
  WHEN check_violation THEN RAISE NOTICE 'OK: profiles.onboarding_completed_at is not client-writable (trigger)';
END $$;

-- Positive control for this section: the safe fields still move, so the
-- three assertions above are proving a guard rather than a broken write
-- path.
DO $$
DECLARE n int;
BEGIN
  UPDATE public.profiles SET full_name = 'Director A', preferred_locale = 'uk'
  WHERE id = '33333333-3333-3333-3333-333333333333';
  GET DIAGNOSTICS n = ROW_COUNT;
  IF n <> 1 THEN
    RAISE EXCEPTION 'HARNESS BROKEN: own-row safe-field update affected % row(s), expected 1', n;
  END IF;
  RAISE NOTICE 'OK: full_name and preferred_locale remain client-writable (positive control)';
END $$;

RESET ROLE;

-- Structural guard (2026-10-03): a SELECT policy on student work must not let
-- a role in by membership alone. «teacher OR admin» once opened every
-- student's submissions, answers and grades in every school to any teacher
-- through PostgREST; the API scopes those reads to the teacher's own courses.
DO $$
DECLARE offenders text;
BEGIN
  SELECT string_agg(tablename || '.' || policyname, ', ') INTO offenders
  FROM pg_policies
  WHERE schemaname = 'public'
    AND tablename IN ('assignment_submissions', 'quiz_answers', 'quiz_attempts', 'quiz_extra_attempts',
                      'student_grades', 'chapter_progress', 'enrollments')
    AND qual LIKE '%''teacher''%';
  IF offenders IS NOT NULL THEN
    RAISE EXCEPTION 'SECURITY HOLE: student-work policies grant by teacher role alone: %', offenders;
  END IF;
  RAISE NOTICE 'OK: no student-work policy grants by teacher role alone';
END $$;


-- ---------------------------------------------------------------------
-- 16) Memberships (20261003165050): a person reads their own rows, the
--     helpers answer by membership, and the mirror keeps profiles.role.
--
-- The three organization policies rest on these helpers since
-- 20261003203000 (section 17 proves the policies); this section pins the
-- contract underneath them, so a failure there says which of the two broke.
-- ---------------------------------------------------------------------

\set member_x '44444444-4444-4444-4444-444444444444'

INSERT INTO auth.users (id, email) VALUES (:'member_x', 'member-x@test.local');
INSERT INTO public.profiles (id, email, role) VALUES (:'member_x', 'member-x@test.local', 'student');

-- Director A directs A (section 14); X studies in A and used to teach in B
-- (suspended).
INSERT INTO public.organization_members (user_id, organization_id, role, joined_via)
VALUES
  (:'member_x',   :'school_a', 'student',  'invitation');
INSERT INTO public.organization_members (user_id, organization_id, role, status, joined_via)
VALUES
  (:'member_x',   :'school_b', 'teacher', 'suspended', 'invitation');

-- The mirror ran as the owner: a student with a suspended teacher row is a
-- student; the director reads director.
DO $$
DECLARE r text;
BEGIN
  SELECT role INTO r FROM public.profiles WHERE id = '44444444-4444-4444-4444-444444444444';
  IF r <> 'student' THEN
    RAISE EXCEPTION 'BROKEN: a suspended teacher membership mirrored into profiles.role (%)', r;
  END IF;
  UPDATE public.organization_members SET status = 'active'
   WHERE user_id = '44444444-4444-4444-4444-444444444444' AND organization_id = 'bbbb2222-0000-0000-0000-000000000002';
  SELECT role INTO r FROM public.profiles WHERE id = '44444444-4444-4444-4444-444444444444';
  IF r <> 'teacher' THEN
    RAISE EXCEPTION 'BROKEN: reactivating a teacher membership did not reach profiles.role (%)', r;
  END IF;
  UPDATE public.organization_members SET status = 'suspended'
   WHERE user_id = '44444444-4444-4444-4444-444444444444' AND organization_id = 'bbbb2222-0000-0000-0000-000000000002';
  SELECT role INTO r FROM public.profiles WHERE id = '44444444-4444-4444-4444-444444444444';
  IF r <> 'student' THEN
    RAISE EXCEPTION 'BROKEN: suspending the membership did not drop profiles.role back (%)', r;
  END IF;
  RAISE NOTICE 'OK: profiles.role mirrors the highest active membership';
END $$;

SET request.jwt.claim.sub = '44444444-4444-4444-4444-444444444444';
SET ROLE authenticated;

DO $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM public.organization_members;
  IF n <> 2 THEN
    RAISE EXCEPTION 'SECURITY HOLE: a member sees % membership rows, expected only their own 2', n;
  END IF;
  SELECT count(*) INTO n FROM public.organization_members WHERE user_id = '33333333-3333-3333-3333-333333333333';
  IF n <> 0 THEN
    RAISE EXCEPTION 'SECURITY HOLE: another person''s membership row is readable';
  END IF;
  RAISE NOTICE 'OK: organization_members is self-only';
END $$;

DO $$
BEGIN
  INSERT INTO public.organization_members (user_id, organization_id, role, joined_via)
  VALUES ('44444444-4444-4444-4444-444444444444', 'bbbb2222-0000-0000-0000-000000000002', 'director', 'appointment');
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can INSERT organization_members (self-appointment)';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: organization_members INSERT denied (privilege)';
  WHEN unique_violation THEN RAISE EXCEPTION 'SECURITY HOLE: the INSERT reached the table';
END $$;

DO $$
BEGIN
  UPDATE public.organization_members SET role = 'director'
   WHERE user_id = '44444444-4444-4444-4444-444444444444';
  RAISE EXCEPTION 'SECURITY HOLE: authenticated can UPDATE organization_members (self-promotion)';
EXCEPTION
  WHEN insufficient_privilege THEN RAISE NOTICE 'OK: organization_members UPDATE denied (privilege)';
END $$;

-- The helpers, as member X: a member of A in any role, staff of nowhere
-- (the B row is suspended), director of nowhere, and NULL is never a yes.
DO $$
BEGIN
  IF NOT public.is_member_of('aaaa1111-0000-0000-0000-000000000001') THEN
    RAISE EXCEPTION 'BROKEN: is_member_of denies an active member';
  END IF;
  IF public.is_member_of('bbbb2222-0000-0000-0000-000000000002') THEN
    RAISE EXCEPTION 'SECURITY HOLE: a suspended membership still counts as membership';
  END IF;
  IF public.is_staff_of('aaaa1111-0000-0000-0000-000000000001') THEN
    RAISE EXCEPTION 'SECURITY HOLE: a student is staff';
  END IF;
  IF public.is_director_of('aaaa1111-0000-0000-0000-000000000001') THEN
    RAISE EXCEPTION 'SECURITY HOLE: a student is a director';
  END IF;
  IF public.is_member_of(NULL) IS DISTINCT FROM false OR public.is_staff_of(NULL) IS DISTINCT FROM false
     OR public.is_director_of(NULL) IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'SECURITY HOLE: a NULL organization satisfies a membership helper';
  END IF;
  IF (SELECT count(*) FROM public.member_organization_ids()) <> 1 THEN
    RAISE EXCEPTION 'BROKEN: member_organization_ids() should list exactly school A';
  END IF;
  RAISE NOTICE 'OK: membership helpers answer by active membership and refuse NULL';
END $$;

-- And as director A: staff and director of A, neither of B.
RESET ROLE;
SET request.jwt.claim.sub = '33333333-3333-3333-3333-333333333333';
SET ROLE authenticated;

DO $$
BEGIN
  IF NOT (public.is_staff_of('aaaa1111-0000-0000-0000-000000000001')
          AND public.is_director_of('aaaa1111-0000-0000-0000-000000000001')) THEN
    RAISE EXCEPTION 'BROKEN: a director is not staff and director of their own organization';
  END IF;
  IF public.is_member_of('bbbb2222-0000-0000-0000-000000000002')
     OR public.is_director_of('bbbb2222-0000-0000-0000-000000000002') THEN
    RAISE EXCEPTION 'SECURITY HOLE: a director of A is something in B';
  END IF;
  RAISE NOTICE 'OK: a director directs their own organization only';
END $$;

RESET ROLE;


-- ---------------------------------------------------------------------
-- 17) A role held elsewhere opens nothing here (20261003203000).
--
-- Until that migration the three organization policies read
-- profiles.organization_id and the global profiles.role. Once the role
-- became a mirror of the *highest* membership anywhere, a student of A who
-- teaches in B read `teacher` while the column still said A — and A's
-- certificates opened to them. A membership suspended in A kept A open for
-- the same reason: the column did not move. The policies now ask the
-- membership rows, so the shapes that leaked are the ones asserted here.
--
-- S: student of A, teacher of B. The column deliberately says A, as it
-- does for anybody who joined A first.
-- ---------------------------------------------------------------------

\set member_s '55555555-5555-5555-5555-555555555555'

INSERT INTO auth.users (id, email) VALUES (:'member_s', 'member-s@test.local');
INSERT INTO public.profiles (id, email, role, organization_id)
VALUES (:'member_s', 'member-s@test.local', 'student', :'school_a');
INSERT INTO public.organization_members (user_id, organization_id, role, joined_via)
VALUES
  (:'member_s', :'school_a', 'student', 'invitation'),
  (:'member_s', :'school_b', 'teacher', 'invitation');
-- S's own certificate in A, next to the director's from section 14.
INSERT INTO public.certificates (id, organization_id, user_id, course_id, status)
VALUES ('dddd0003-0000-0000-0000-000000000003', :'school_a', :'member_s', 'course-a-institute', 'pending');

-- Precondition: the mirror did what makes this dangerous — S reads teacher.
DO $$
DECLARE r text;
BEGIN
  SELECT role INTO r FROM public.profiles WHERE id = '55555555-5555-5555-5555-555555555555';
  IF r <> 'teacher' THEN
    RAISE EXCEPTION 'HARNESS BROKEN: expected S to mirror teacher, got %', r;
  END IF;
END $$;

SET request.jwt.claim.sub = '55555555-5555-5555-5555-555555555555';
SET ROLE authenticated;

DO $$
DECLARE n int;
BEGIN
  -- certificates: own, yes; another student's in A, no — S is A's student;
  -- B's, yes — S is B's staff.
  SELECT count(*) INTO n FROM public.certificates WHERE id = 'dddd0003-0000-0000-0000-000000000003';
  IF n <> 1 THEN
    RAISE EXCEPTION 'BROKEN: a person cannot read their own certificate';
  END IF;
  SELECT count(*) INTO n FROM public.certificates WHERE id = 'dddd0001-0000-0000-0000-000000000001';
  IF n <> 0 THEN
    RAISE EXCEPTION 'SECURITY HOLE: a teacher of B reads a certificate of A, where they are a student';
  END IF;
  SELECT count(*) INTO n FROM public.certificates WHERE id = 'dddd0002-0000-0000-0000-000000000002';
  IF n <> 1 THEN
    RAISE EXCEPTION 'BROKEN: staff of B cannot read a certificate of B';
  END IF;
  RAISE NOTICE 'OK: certificates open to the staff of *their* organization, not to a role held elsewhere';
END $$;

DO $$
DECLARE n int;
BEGIN
  -- courses: a member of both reads both closed courses, and the catalogue.
  SELECT count(*) INTO n FROM public.courses WHERE id IN ('course-a-institute', 'course-b-institute', 'course-b-public');
  IF n <> 3 THEN
    RAISE EXCEPTION 'BROKEN: a member of A and B reads % of their 3 courses', n;
  END IF;
  -- cohorts: B's as its staff, not A's as its student.
  SELECT count(*) INTO n FROM public.cohorts WHERE id = 'cccc0002-0000-0000-0000-000000000002';
  IF n <> 1 THEN
    RAISE EXCEPTION 'BROKEN: staff of B cannot read a cohort of B';
  END IF;
  SELECT count(*) INTO n FROM public.cohorts WHERE id = 'cccc0001-0000-0000-0000-000000000001';
  IF n <> 0 THEN
    RAISE EXCEPTION 'SECURITY HOLE: a student of A reads a cohort of A (role held in B)';
  END IF;
  RAISE NOTICE 'OK: cohorts open to the staff of their organization only';
END $$;

-- Suspended in A. The column still says A; the policies must not care.
RESET ROLE;
UPDATE public.organization_members SET status = 'suspended'
 WHERE user_id = '55555555-5555-5555-5555-555555555555' AND organization_id = 'aaaa1111-0000-0000-0000-000000000001';
SET ROLE authenticated;

DO $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM public.courses WHERE id = 'course-a-institute';
  IF n <> 0 THEN
    RAISE EXCEPTION 'SECURITY HOLE: a membership suspended in A still reads A''s closed course';
  END IF;
  SELECT count(*) INTO n FROM public.certificates WHERE id = 'dddd0001-0000-0000-0000-000000000001';
  IF n <> 0 THEN
    RAISE EXCEPTION 'SECURITY HOLE: a membership suspended in A still reads A''s certificates';
  END IF;
  SELECT count(*) INTO n FROM public.cohorts WHERE id = 'cccc0001-0000-0000-0000-000000000001';
  IF n <> 0 THEN
    RAISE EXCEPTION 'SECURITY HOLE: a membership suspended in A still reads A''s cohorts';
  END IF;
  -- Their own certificate is theirs whatever the organization decides.
  SELECT count(*) INTO n FROM public.certificates WHERE id = 'dddd0003-0000-0000-0000-000000000003';
  IF n <> 1 THEN
    RAISE EXCEPTION 'BROKEN: a suspended member lost sight of their own certificate';
  END IF;
  -- And B, where nothing changed, still reads.
  SELECT count(*) INTO n FROM public.courses WHERE id = 'course-b-institute';
  IF n <> 1 THEN
    RAISE EXCEPTION 'BROKEN: suspension in A closed B';
  END IF;
  RAISE NOTICE 'OK: a suspended membership opens nothing, and only there';
END $$;

RESET ROLE;

-- Structural guard: the column has no reader left in a policy, and the
-- helper that read it is gone. A policy written by habit against the
-- deprecated column would answer the wrong organization with a real uuid.
DO $$
DECLARE offenders text;
BEGIN
  SELECT string_agg(tablename || '.' || policyname, ', ') INTO offenders
  FROM pg_policies
  WHERE schemaname = 'public'
    AND (coalesce(qual, '') LIKE '%current_organization_id%' OR coalesce(with_check, '') LIKE '%current_organization_id%'
         OR coalesce(qual, '') LIKE '%profiles.organization_id%');
  IF offenders IS NOT NULL THEN
    RAISE EXCEPTION 'SECURITY HOLE: policies still read the deprecated column: %', offenders;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
             WHERE n.nspname = 'public' AND p.proname = 'current_organization_id') THEN
    RAISE EXCEPTION 'SECURITY HOLE: current_organization_id() still exists (20261003203000 dropped it)';
  END IF;
  RAISE NOTICE 'OK: no policy reads profiles.organization_id';
END $$;

SELECT 'RLS policy assertions passed' AS result;
