-- An invitation remembers when its letter last actually left.
--
-- "Send again" mails the same link (the token is derived from the row id),
-- and a teacher pressing it twice, or a page retrying, put two identical
-- letters in one inbox — the pattern of a bulk sender. The backend now skips
-- a resend within ten minutes of the last letter the provider took. It must
-- know that the letter left, not merely that it was attempted: after a failed
-- send the next press has to mail. Written only by the server after a
-- successful hand-off (`invitation_service._mail_the_invitation`).
--
-- Must be applied before the backend that reads it is deployed.

ALTER TABLE public.invitations ADD COLUMN IF NOT EXISTS mailed_at timestamptz;
