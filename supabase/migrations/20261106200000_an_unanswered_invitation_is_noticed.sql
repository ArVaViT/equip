-- An invitation nobody answers is noticed before it expires.
--
-- An invitation lives seven days and used to end in silence: the person who
-- sent it learned nothing until they happened to open the list, and every
-- teacher invited in October 2026 expired that way. A sweep now tells the
-- sender, in the bell, before the link stops working, while there is
-- still time to reach the person another way. This is when it did, so it
-- does once; a resend, which gives the link a fresh week, clears it.
-- Written only by the server (`invitation_watch.notice_unanswered`).
--
-- Must be applied before the backend that reads it is deployed.

ALTER TABLE public.invitations ADD COLUMN IF NOT EXISTS unanswered_noticed_at timestamptz;

COMMENT ON COLUMN public.invitations.unanswered_noticed_at IS
  'When the sender was told this invitation was still unanswered close to '
  'its expiry. Cleared by a resend. See migration 20261106200000.';
