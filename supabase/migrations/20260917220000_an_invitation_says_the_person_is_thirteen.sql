-- An invitation says the person is thirteen.
--
-- The Privacy Policy has always said you can register yourself from 16 and
-- that anyone younger comes in through a school administrator. It set no
-- floor under the second half, so as written an administrator could open an
-- account for a nine-year-old and the platform would have no idea.
--
-- The owner's decision of 2026-09-17 puts the floor at thirteen. Below that
-- the platform does not want the account at all: a known under-13 turns
-- COPPA on, and COPPA is verifiable parental consent, a parental
-- records-access duty, a deletion duty and a direct-notice duty. Those are
-- real obligations with a real process behind them, and there is no process
-- here — there are nine teachers. Refusing the account is the honest answer,
-- and it is also the cheap one.
--
-- No date of birth. Collecting one would mean holding a piece of personal
-- data about a child in order to protect children, and the platform has no
-- second use for it. What it needs is a person who knows the family saying
-- so, and a record of who that was. That is these two columns: the sender's
-- statement, and the sender.
--
-- Both nullable, and moving together. Every invitation written before today
-- has no answer to this question and inventing one would be the opposite of
-- a record; the CHECK is what stops half an answer — an attestation with no
-- attester says nobody made it.
--
-- ON DELETE SET NULL on the attester, matching invited_by on the same table.
-- A deleted profile should not take the invitation with it, and the audit
-- log line written alongside the row keeps the name if the column loses it.
--
-- Apply BEFORE the backend that writes these columns is deployed: the new
-- code names them on every insert, and the previous backend does not read
-- them, so this direction has no window where either half is broken.

ALTER TABLE public.invitations
  ADD COLUMN IF NOT EXISTS age_attested_at timestamp with time zone,
  ADD COLUMN IF NOT EXISTS age_attested_by uuid;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'invitations_age_attested_by_fkey'
  ) THEN
    ALTER TABLE public.invitations
      ADD CONSTRAINT invitations_age_attested_by_fkey
      FOREIGN KEY (age_attested_by) REFERENCES public.profiles(id) ON DELETE SET NULL;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_invitations_age_attested_together'
  ) THEN
    ALTER TABLE public.invitations
      ADD CONSTRAINT chk_invitations_age_attested_together
      CHECK ((age_attested_at IS NULL) = (age_attested_by IS NULL));
  END IF;
END
$$;
