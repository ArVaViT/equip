-- An invitation is closed as `fulfilled` when its person arrives by any door.
--
-- Run by the schema-replay job against supabase/schema.sql on a clean
-- Postgres. Every write below goes straight to a table -- no backend, no
-- service function -- because that is the point: the rule lives in
-- public.fulfil_pending_invitations and its triggers, and a caller that
-- forgets to ask for it must not be able to leave an invitation pending.
-- The backend's own tests run on SQLite and cannot see a trigger.
--
-- Every check RAISEs on failure, so ON_ERROR_STOP aborts the job.

\set ON_ERROR_STOP on

BEGIN;

INSERT INTO public.organizations (id, slug, public_name) VALUES
  ('a0000000-0000-0000-0000-00000000000a', 'org-a', 'Org A'),
  ('b0000000-0000-0000-0000-00000000000b', 'org-b', 'Org B');

INSERT INTO public.courses (id, organization_id) VALUES
  ('course-a', 'a0000000-0000-0000-0000-00000000000a'),
  ('course-b', 'a0000000-0000-0000-0000-00000000000a');

INSERT INTO auth.users (id)
SELECT ('10000000-0000-0000-0000-00000000000' || n)::uuid FROM generate_series(1, 7) AS n;

INSERT INTO public.profiles (id, email, role) VALUES
  ('10000000-0000-0000-0000-000000000001', 'enrols@test.local', 'student'),
  ('10000000-0000-0000-0000-000000000002', 'wants-teaching@test.local', 'student'),
  -- Stored with capitals; invitations are written lower-case.
  ('10000000-0000-0000-0000-000000000003', 'Joins.Org@Test.Local', 'student'),
  ('10000000-0000-0000-0000-000000000004', 'late@test.local', 'student'),
  ('10000000-0000-0000-0000-000000000005', 'wrong-course@test.local', 'student'),
  ('10000000-0000-0000-0000-000000000006', 'backfill@test.local', 'student');

-- A helper that reads one invitation's status by email + scope.
CREATE FUNCTION pg_temp.status_of(p_email text, p_scope text, p_course text DEFAULT NULL) RETURNS text
LANGUAGE sql AS $$
  SELECT status FROM public.invitations
  WHERE email = p_email AND scope = p_scope AND course_id IS NOT DISTINCT FROM p_course
  ORDER BY created_at DESC LIMIT 1
$$;

CREATE FUNCTION pg_temp.expect(p_actual text, p_expected text, p_what text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
  IF p_actual IS DISTINCT FROM p_expected THEN
    RAISE EXCEPTION 'INVITATION FULFILMENT BROKEN: % -- expected %, got %', p_what, p_expected, p_actual;
  END IF;
  RAISE NOTICE 'OK: %', p_what;
END $$;

-- 1) Enrolling on the course closes a course invitation. Written straight
--    into `enrollments`, as a cohort add does.
INSERT INTO public.invitations (email, role, token, organization_id, scope, course_id)
VALUES ('enrols@test.local', 'student', 't1', 'a0000000-0000-0000-0000-00000000000a', 'course', 'course-a');
SELECT pg_temp.expect(pg_temp.status_of('enrols@test.local', 'course', 'course-a'), 'pending',
  'a course invitation starts pending');
INSERT INTO public.enrollments (id, user_id, course_id)
VALUES ('e1', '10000000-0000-0000-0000-000000000001', 'course-a');
SELECT pg_temp.expect(pg_temp.status_of('enrols@test.local', 'course', 'course-a'), 'fulfilled',
  'enrolling on the course fulfils its invitation');
SELECT pg_temp.expect(
  (SELECT (fulfilled_at IS NOT NULL AND accepted_at IS NULL)::text FROM public.invitations WHERE token = 't1'),
  'true', 'a fulfilled invitation records when, and does not claim its link was used');

-- 2) A teacher invitation is not fulfilled by enrolling as a student, and is
--    by becoming a teacher.
INSERT INTO public.invitations (email, role, token, organization_id, scope, course_id)
VALUES ('wants-teaching@test.local', 'teacher', 't2', 'a0000000-0000-0000-0000-00000000000a', 'course', 'course-a');
INSERT INTO public.enrollments (id, user_id, course_id)
VALUES ('e2', '10000000-0000-0000-0000-000000000002', 'course-a');
SELECT pg_temp.expect(pg_temp.status_of('wants-teaching@test.local', 'course', 'course-a'), 'pending',
  'a student enrolment does not fulfil a teacher invitation');
UPDATE public.profiles SET role = 'teacher' WHERE id = '10000000-0000-0000-0000-000000000002';
SELECT pg_temp.expect(pg_temp.status_of('wants-teaching@test.local', 'course', 'course-a'), 'fulfilled',
  'gaining the role completes it');

-- 3) Organization invitations: the right organization, matched without case.
INSERT INTO public.invitations (email, role, token, organization_id, scope)
VALUES ('joins.org@test.local', 'student', 't3', 'a0000000-0000-0000-0000-00000000000a', 'organization');
UPDATE public.profiles SET organization_id = 'b0000000-0000-0000-0000-00000000000b'
WHERE id = '10000000-0000-0000-0000-000000000003';
SELECT pg_temp.expect(pg_temp.status_of('joins.org@test.local', 'organization'), 'pending',
  'joining a different organization does not fulfil it');
UPDATE public.profiles SET organization_id = 'a0000000-0000-0000-0000-00000000000a'
WHERE id = '10000000-0000-0000-0000-000000000003';
SELECT pg_temp.expect(pg_temp.status_of('joins.org@test.local', 'organization'), 'fulfilled',
  'joining the inviting organization fulfils it, whatever the case of the stored email');

-- 4) A platform invitation is an account, so creating the account fulfils it
--    (handle_new_user inserts the profile; the backend never sees that).
INSERT INTO public.invitations (email, role, token, organization_id, scope)
VALUES ('newcomer@test.local', 'student', 't4', 'a0000000-0000-0000-0000-00000000000a', 'platform');
INSERT INTO public.profiles (id, email, role)
VALUES ('10000000-0000-0000-0000-000000000007', 'newcomer@test.local', 'student');
SELECT pg_temp.expect(pg_temp.status_of('newcomer@test.local', 'platform'), 'fulfilled',
  'signing up fulfils a platform invitation');

-- 5) An expired invitation is closed too: it still reads pending, and the list
--    would offer to resend it to somebody who is already there.
INSERT INTO public.invitations (email, role, token, organization_id, scope, course_id, created_at, expires_at)
VALUES ('late@test.local', 'student', 't5', 'a0000000-0000-0000-0000-00000000000a', 'course', 'course-a',
        now() - interval '30 days', now() - interval '23 days');
INSERT INTO public.enrollments (id, user_id, course_id)
VALUES ('e5', '10000000-0000-0000-0000-000000000004', 'course-a');
SELECT pg_temp.expect(pg_temp.status_of('late@test.local', 'course', 'course-a'), 'fulfilled',
  'an expired invitation is fulfilled as well');

-- 6) Another course of the same organization is not this course.
INSERT INTO public.invitations (email, role, token, organization_id, scope, course_id)
VALUES ('wrong-course@test.local', 'student', 't6', 'a0000000-0000-0000-0000-00000000000a', 'course', 'course-a');
INSERT INTO public.enrollments (id, user_id, course_id)
VALUES ('e6', '10000000-0000-0000-0000-000000000005', 'course-b');
SELECT pg_temp.expect(pg_temp.status_of('wrong-course@test.local', 'course', 'course-a'), 'pending',
  'an enrolment on a different course fulfils nothing');

-- 7) Revoked and accepted invitations are the sender's and the link's
--    decisions; arriving does not rewrite them.
INSERT INTO public.invitations (email, role, token, organization_id, scope, course_id, status)
VALUES ('wrong-course@test.local', 'student', 't7', 'a0000000-0000-0000-0000-00000000000a', 'course', 'course-b', 'revoked');
INSERT INTO public.invitations (email, role, token, organization_id, scope, course_id, status, accepted_at)
VALUES ('wrong-course@test.local', 'student', 't7b', 'a0000000-0000-0000-0000-00000000000a', 'course', 'course-b', 'accepted', now());
UPDATE public.profiles SET organization_id = 'a0000000-0000-0000-0000-00000000000a'
WHERE id = '10000000-0000-0000-0000-000000000005';
SELECT pg_temp.expect((SELECT status FROM public.invitations WHERE token = 't7'), 'revoked',
  'a revoked invitation stays revoked');
SELECT pg_temp.expect((SELECT status FROM public.invitations WHERE token = 't7b'), 'accepted',
  'an accepted invitation stays accepted');

-- 8) An invitation written for somebody who is already on the course is
--    closed as it is written.
INSERT INTO public.invitations (email, role, token, organization_id, scope, course_id)
VALUES ('enrols@test.local', 'student', 't8', 'a0000000-0000-0000-0000-00000000000a', 'course', 'course-a');
SELECT pg_temp.expect((SELECT status FROM public.invitations WHERE token = 't8'), 'fulfilled',
  'an invitation for somebody already there is fulfilled on insert');

-- 9) The backfill: state left behind before the rule existed (triggers off),
--    closed by one run of the function, and a second run closes nothing.
ALTER TABLE public.invitations DISABLE TRIGGER trg_invitations_created_fulfil;
ALTER TABLE public.enrollments DISABLE TRIGGER trg_enrollments_fulfil_invitations;
INSERT INTO public.invitations (email, role, token, organization_id, scope, course_id)
VALUES ('backfill@test.local', 'student', 't9', 'a0000000-0000-0000-0000-00000000000a', 'course', 'course-b');
INSERT INTO public.enrollments (id, user_id, course_id)
VALUES ('e9', '10000000-0000-0000-0000-000000000006', 'course-b');
ALTER TABLE public.invitations ENABLE TRIGGER trg_invitations_created_fulfil;
ALTER TABLE public.enrollments ENABLE TRIGGER trg_enrollments_fulfil_invitations;
SELECT pg_temp.expect(pg_temp.status_of('backfill@test.local', 'course', 'course-b'), 'pending',
  'precondition: a pre-existing arrival left its invitation pending');
SELECT pg_temp.expect(public.fulfil_pending_invitations(NULL)::text, '1',
  'the backfill closes exactly the one it should');
SELECT pg_temp.expect(pg_temp.status_of('backfill@test.local', 'course', 'course-b'), 'fulfilled',
  'and it is fulfilled');
SELECT pg_temp.expect(public.fulfil_pending_invitations(NULL)::text, '0',
  'a second backfill run closes nothing');
SELECT pg_temp.expect(pg_temp.status_of('wrong-course@test.local', 'course', 'course-a'), 'pending',
  'the backfill leaves an unfulfilled invitation alone');

-- 10) The status and its timestamp agree.
DO $$
BEGIN
  UPDATE public.invitations SET status = 'fulfilled', fulfilled_at = NULL WHERE token = 't6';
  RAISE EXCEPTION 'INVITATION FULFILMENT BROKEN: fulfilled without fulfilled_at was accepted';
EXCEPTION
  WHEN check_violation THEN RAISE NOTICE 'OK: fulfilled requires fulfilled_at';
END $$;

ROLLBACK;

SELECT 'Invitation fulfilment assertions passed' AS result;
