-- Both backends can write an invitation while 20261015213140 is live.
--
-- The expand step of the token-hash rollout is applied before the backend
-- that reads `token_hash` is deployed, so for a while the previous backend
-- (writes `token`) and the new one (writes `token_hash`, leaves `token`
-- NULL) share the table. Either insert must succeed, and either row must be
-- findable by the hash the new backend looks up. Remove this file together
-- with the trigger in 20261015230000.
--
-- Every check RAISEs on failure, so ON_ERROR_STOP aborts the job.

\set ON_ERROR_STOP on

BEGIN;

INSERT INTO public.organizations (id, slug, public_name) VALUES
  ('c0000000-0000-0000-0000-00000000000c', 'org-rollout', 'Org Rollout');

-- The previous backend: a plain token, no hash.
INSERT INTO public.invitations (email, role, token, organization_id)
VALUES ('old@test.local', 'student', 'plain-token-from-the-old-backend', 'c0000000-0000-0000-0000-00000000000c');

-- The new backend: a hash, no token.
INSERT INTO public.invitations (email, role, token_hash, organization_id)
VALUES ('new@test.local', 'student', encode(sha256(convert_to('derived-token', 'UTF8')), 'hex'),
        'c0000000-0000-0000-0000-00000000000c');

DO $$
DECLARE
  found_old text;
  found_new text;
  plain text;
BEGIN
  SELECT email INTO found_old FROM public.invitations
   WHERE token_hash = encode(sha256(convert_to('plain-token-from-the-old-backend', 'UTF8')), 'hex');
  IF found_old IS DISTINCT FROM 'old@test.local' THEN
    RAISE EXCEPTION 'TOKEN ROLLOUT BROKEN: a row the previous backend wrote is not found by its hash';
  END IF;
  RAISE NOTICE 'OK: the previous backend''s insert is found by its hash';

  SELECT email, token INTO found_new, plain FROM public.invitations
   WHERE token_hash = encode(sha256(convert_to('derived-token', 'UTF8')), 'hex');
  IF found_new IS DISTINCT FROM 'new@test.local' OR plain IS NOT NULL THEN
    RAISE EXCEPTION 'TOKEN ROLLOUT BROKEN: the new backend''s insert is missing or holds a plain token';
  END IF;
  RAISE NOTICE 'OK: the new backend''s insert stores no plain token';
END $$;

-- Two rows can never share a hash.
DO $$
BEGIN
  INSERT INTO public.invitations (email, role, token, organization_id)
  VALUES ('dup@test.local', 'teacher', 'plain-token-from-the-old-backend', 'c0000000-0000-0000-0000-00000000000c');
  RAISE EXCEPTION 'TOKEN ROLLOUT BROKEN: a second row with the same token hash was accepted';
EXCEPTION
  WHEN unique_violation THEN RAISE NOTICE 'OK: token hashes are unique';
END $$;

ROLLBACK;

SELECT 'Invitation token rollout assertions passed' AS result;
