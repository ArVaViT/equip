-- An invitation keeps only the hash of its token — step 1 of 2 (expand).
--
-- The token in an invitation link is a bearer secret: whoever holds it can
-- join a school, some of them as a teacher. Until now it was stored here in
-- plain text, so anything that could read this table -- a backup, a support
-- query, a leaked connection string -- could open every pending invitation.
--
-- From PR #1389 the backend looks links up by `token_hash`, SHA-256 of the
-- token (hex), and never reads or writes `token`. It derives each new token
-- from the row's id with a server-held key (invitation_service.
-- invitation_token), so a resend mails the same link without the table ever
-- holding it.
--
-- Safe BEFORE that backend and with both backends running at once, so it is
-- applied first and nothing answers 500 in between:
--
--   * the backfill hashes every token already mailed, with the same function
--     the backend uses (sha256 of the UTF-8 bytes, hex) -- every link in an
--     inbox keeps opening under the new backend;
--   * `token` becomes nullable, because the new backend does not write it;
--   * a trigger fills `token_hash` whenever a row arrives with a `token`, so
--     an invitation the previous backend writes during the rollout is found
--     by the new one too;
--   * `token_hash` stays nullable until step 2, which the previous backend's
--     inserts would otherwise break on if the trigger were ever missing.
--
-- Step 2 (contract) drops the trigger and `token` and makes `token_hash`
-- NOT NULL — 20261015230000_an_invitation_forgets_its_token.sql, applied
-- only once this backend is live.

ALTER TABLE public.invitations ADD COLUMN IF NOT EXISTS token_hash text;

UPDATE public.invitations
   SET token_hash = encode(sha256(convert_to(token, 'UTF8')), 'hex')
 WHERE token_hash IS NULL
   AND token IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS invitations_token_hash_key
  ON public.invitations (token_hash);

ALTER TABLE public.invitations ALTER COLUMN token DROP NOT NULL;

CREATE OR REPLACE FUNCTION public.invitation_token_hash_from_token() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO ''
    AS $$
BEGIN
  -- Rollout only: the previous backend writes `token`; the new one writes
  -- `token_hash` and leaves `token` NULL, which this leaves alone.
  IF NEW.token IS NOT NULL THEN
    NEW.token_hash := encode(sha256(convert_to(NEW.token, 'UTF8')), 'hex');
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_invitations_token_hash_from_token ON public.invitations;
CREATE TRIGGER trg_invitations_token_hash_from_token
  BEFORE INSERT OR UPDATE OF token ON public.invitations
  FOR EACH ROW EXECUTE FUNCTION public.invitation_token_hash_from_token();
