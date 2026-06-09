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

RESET ROLE;
SELECT 'RLS policy assertions passed' AS result;
