-- A consent record outlives the account, and the person does not.
--
-- Run by the schema-replay job against supabase/schema.sql on a clean
-- Postgres. Every write below goes straight to a table -- no backend, no
-- service function -- because that is the point: the rule lives in
-- public.anonymise_legal_acceptances and its BEFORE DELETE trigger, and
-- nothing in the application is on the path that fires it. The backend's own
-- delete route is a soft delete; a real deletion comes through Supabase
-- removing the auth user, and the cascade takes the profile with it.
--
-- The backend's tests run on SQLite and cannot see a trigger.
--
-- Every check RAISEs on failure, so ON_ERROR_STOP aborts the job.

\set ON_ERROR_STOP on

BEGIN;

CREATE FUNCTION pg_temp.expect(p_actual text, p_expected text, p_what text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
  IF p_actual IS DISTINCT FROM p_expected THEN
    RAISE EXCEPTION 'CONSENT SURVIVAL BROKEN: % -- expected %, got %', p_what, p_expected, p_actual;
  END IF;
  RAISE NOTICE 'OK: %', p_what;
END;
$$;

INSERT INTO auth.users (id) VALUES
  ('20000000-0000-0000-0000-000000000001'),
  ('20000000-0000-0000-0000-000000000002');

INSERT INTO public.profiles (id, email, role) VALUES
  ('20000000-0000-0000-0000-000000000001', 'leaves@test.local', 'student'),
  ('20000000-0000-0000-0000-000000000002', 'stays@test.local', 'student');

-- Two documents each, so the surviving rows can be checked for the thing
-- subject_hash is actually for: seeing that one person accepted both.
INSERT INTO public.legal_acceptances
  (user_id, document_slug, version, locale, content_sha256, accepted_at, ip)
VALUES
  ('20000000-0000-0000-0000-000000000001', 'privacy', '2.0', 'ru', 'aa', '2026-09-17T10:00:00Z', '203.0.113.7'),
  ('20000000-0000-0000-0000-000000000001', 'terms',   '2.0', 'ru', 'bb', '2026-09-17T10:00:01Z', '203.0.113.7'),
  ('20000000-0000-0000-0000-000000000002', 'privacy', '2.0', 'en', 'aa', '2026-09-17T11:00:00Z', '203.0.113.9');

-- The deletion the product will actually perform: the auth user goes, and
-- profiles cascades from it.
DELETE FROM auth.users WHERE id = '20000000-0000-0000-0000-000000000001';

SELECT pg_temp.expect(
  (SELECT count(*)::text FROM public.profiles WHERE id = '20000000-0000-0000-0000-000000000001'),
  '0',
  'the profile is gone');

SELECT pg_temp.expect(
  (SELECT count(*)::text FROM public.legal_acceptances WHERE user_id IS NULL),
  '2',
  'both acceptances survived the deletion');

SELECT pg_temp.expect(
  (SELECT count(*)::text FROM public.legal_acceptances WHERE user_id IS NULL AND ip IS NOT NULL),
  '0',
  'no IP address survived on an anonymised row');

SELECT pg_temp.expect(
  (SELECT count(DISTINCT subject_hash)::text FROM public.legal_acceptances WHERE user_id IS NULL),
  '1',
  'the two surviving rows share one fingerprint -- one person, two documents');

-- The fingerprint is of the account id and of nothing else. Written out here
-- rather than recomputed with the same expression the trigger uses, so a
-- change to that expression fails rather than agrees with itself.
SELECT pg_temp.expect(
  (SELECT DISTINCT subject_hash FROM public.legal_acceptances WHERE user_id IS NULL),
  encode(sha256(convert_to('20000000-0000-0000-0000-000000000001', 'UTF8')), 'hex'),
  'the fingerprint is sha256 of the account id');

-- What the record is kept for: which text, in which language, when.
SELECT pg_temp.expect(
  (SELECT string_agg(document_slug || ' ' || version || ' ' || locale || ' ' || content_sha256, ', ' ORDER BY document_slug)
     FROM public.legal_acceptances WHERE user_id IS NULL),
  'privacy 2.0 ru aa, terms 2.0 ru bb',
  'document, version, language and fingerprint of the text all survived');

SELECT pg_temp.expect(
  (SELECT count(*)::text FROM public.legal_acceptances WHERE user_id IS NULL AND accepted_at IS NULL),
  '0',
  'the moment of acceptance survived');

-- The account that stayed is untouched: still attributed, still carrying its
-- IP, and not fingerprinted. subject_hash is set at deletion, not at insert.
SELECT pg_temp.expect(
  (SELECT count(*)::text FROM public.legal_acceptances
    WHERE user_id = '20000000-0000-0000-0000-000000000002'
      AND ip IS NOT NULL AND subject_hash IS NULL),
  '1',
  'a living account keeps its own row exactly as it was');

-- Two different people who leave do not collapse into one fingerprint.
DELETE FROM auth.users WHERE id = '20000000-0000-0000-0000-000000000002';

SELECT pg_temp.expect(
  (SELECT count(DISTINCT subject_hash)::text FROM public.legal_acceptances WHERE user_id IS NULL),
  '2',
  'a second deleted account gets a fingerprint of its own');

-- The unique constraint is (user_id, document_slug, version), and Postgres
-- treats NULLs as distinct — so two people who both accepted privacy 2.0 and
-- then left do not collide.
SELECT pg_temp.expect(
  (SELECT count(*)::text FROM public.legal_acceptances WHERE user_id IS NULL AND document_slug = 'privacy'),
  '2',
  'two anonymised acceptances of the same version coexist');

ROLLBACK;
