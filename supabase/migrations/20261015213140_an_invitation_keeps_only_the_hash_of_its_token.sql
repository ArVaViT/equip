-- An invitation keeps only the hash of its token.
--
-- The token in an invitation link is a bearer secret: whoever holds it can
-- join a school, some of them as a teacher. Until now it was stored here in
-- plain text, so anything that could read this table -- a backup, a support
-- query, a leaked connection string -- could open every pending invitation.
--
-- From this migration the table holds SHA-256 of the token (hex) and looks
-- links up by it. The backend derives each new token from the row's id with
-- a server-held key (invitation_service.invitation_token), so a resend
-- mails the same link again without the table ever holding it.
--
-- The backfill hashes the tokens already mailed, with the same function the
-- backend uses (sha256 of the UTF-8 bytes, hex), so every link already in
-- somebody's inbox keeps opening.
--
-- Not safe before the backend that needs it, and not after it either: the
-- previous release reads `token`, this one reads `token_hash`. Apply it as
-- soon as the production deploy of the same PR is live; until then
-- invitation routes answer 500.

ALTER TABLE public.invitations ADD COLUMN IF NOT EXISTS token_hash text;

UPDATE public.invitations
   SET token_hash = encode(sha256(convert_to(token, 'UTF8')), 'hex')
 WHERE token_hash IS NULL;

ALTER TABLE public.invitations ALTER COLUMN token_hash SET NOT NULL;

ALTER TABLE public.invitations
  ADD CONSTRAINT invitations_token_hash_key UNIQUE (token_hash);

-- Dropping the column drops its UNIQUE constraint (invitations_token_key)
-- with it.
ALTER TABLE public.invitations DROP COLUMN token;
