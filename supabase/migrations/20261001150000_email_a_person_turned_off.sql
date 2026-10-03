-- Course mail a person has turned off.
--
-- The privacy policy promises it in so many words: course mail "can be
-- turned off in your profile, and every such message carries an
-- unsubscribe link". Until now there was no course mail to turn off; the
-- first kind ("your work has been marked or returned") arrives with this.
--
-- A list of kinds rather than a column per kind: a new kind of mail is a
-- new allowed value, not a migration of every row, and an empty list —
-- the default — means "send me everything the platform sends".
--
-- The kinds are the ones the policy names. Account mail (confirming an
-- address, resetting a password, an invitation) is not here: it cannot
-- be turned off, because without it an account cannot be used.
--
-- Written by the person through PostgREST (their own row, under
-- profiles_update_own_safe_fields) and by the unsubscribe link through
-- the API. Read by the API before any course mail goes out.

ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS email_off jsonb DEFAULT '[]'::jsonb NOT NULL;

ALTER TABLE public.profiles
  DROP CONSTRAINT IF EXISTS profiles_email_off_check;
ALTER TABLE public.profiles
  ADD CONSTRAINT profiles_email_off_check CHECK (
    jsonb_typeof(email_off) = 'array'
    AND email_off <@ '["work_returned", "certificate_decided", "session_starting", "deadline_moved", "announcement"]'::jsonb
  );
