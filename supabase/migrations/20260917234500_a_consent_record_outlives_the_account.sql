-- A consent record outlives the account, without the person in it.
--
-- What was wrong
-- ==============
-- `legal_acceptances.user_id` carried `ON DELETE CASCADE` (20260813100000).
-- `public.profiles.id` in turn references `auth.users(id) ON DELETE CASCADE`,
-- so deleting a Supabase auth user removed the profile and, behind it, every
-- row proving that person had ever accepted anything.
--
-- That is the one question the table exists to answer, and it went unanswerable
-- for precisely the people most likely to raise it: somebody who left, and then
-- disputes what they had agreed to. A consent record that a deletion erases is
-- not a record.
--
-- What replaces it
-- ================
-- The row stays and the person comes out of it. At the moment the profile is
-- deleted:
--
--   * `user_id`       -> NULL          (no account identifier)
--   * `subject_hash`  -> sha256 of the account id, hex
--   * `ip`            -> NULL          (deleted, not blanked later)
--
-- and `document_slug`, `version`, `locale`, `accepted_at` and `content_sha256`
-- stay exactly as they were. None of those five is about the person: they say
-- which text, in which language, at what moment. `content_sha256` is kept
-- deliberately — it is the fingerprint of the document as served, and without
-- it "somebody accepted privacy 2.0" no longer names a text.
--
-- `subject_hash` is a fingerprint, not a promise of anonymity against an
-- adversary who already holds the deleted account's UUID and wants to confirm
-- a guess. It is honest about what it is: enough to see that the same person
-- accepted the privacy policy and the terms in one sitting, not enough to get
-- back to a name, an email address or an account. Nothing in the product reads
-- it; it exists so the surviving rows are not an undifferentiated heap.
--
-- Why a BEFORE DELETE trigger rather than the backend
-- ==================================================
-- The backend never hard-deletes a profile. `DELETE /api/v1/users/admin/users/
-- {id}` is a soft delete — it sets `deactivated_at` and preserves every owned
-- row, deliberately and reversibly. A real deletion happens through Supabase:
-- the auth user goes, and the cascade takes the profile with it. There is no
-- application code on that path to put this in.
--
-- BEFORE DELETE, so it runs ahead of the referential action and the FK finds
-- nothing left to act on. The FK moves to ON DELETE SET NULL anyway, as the
-- second line of defence: if this trigger is ever dropped, the rows are
-- orphaned rather than destroyed, which is the survivable direction.
--
-- Declared in the Privacy Policy (version 2.0, "What outlives your account"):
-- the record is kept indefinitely, with the account identifier replaced by a
-- one-way fingerprint and the IP address erased.

ALTER TABLE public.legal_acceptances
  ALTER COLUMN user_id DROP NOT NULL;

ALTER TABLE public.legal_acceptances
  ADD COLUMN IF NOT EXISTS subject_hash text;

ALTER TABLE public.legal_acceptances
  DROP CONSTRAINT IF EXISTS legal_acceptances_user_id_fkey;

ALTER TABLE public.legal_acceptances
  ADD CONSTRAINT legal_acceptances_user_id_fkey
  FOREIGN KEY (user_id) REFERENCES public.profiles(id) ON DELETE SET NULL;


CREATE OR REPLACE FUNCTION public.anonymise_legal_acceptances()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
  UPDATE public.legal_acceptances
     SET subject_hash = COALESCE(
           subject_hash,
           encode(sha256(convert_to(OLD.id::text, 'UTF8')), 'hex')
         ),
         user_id = NULL,
         ip = NULL
   WHERE user_id = OLD.id;
  RETURN OLD;
END;
$$;

COMMENT ON FUNCTION public.anonymise_legal_acceptances() IS
  'Keeps the proof that somebody consented while removing who they were. See 20260917234500.';

DROP TRIGGER IF EXISTS trg_profiles_deleted_anonymise_consent ON public.profiles;

CREATE TRIGGER trg_profiles_deleted_anonymise_consent
  BEFORE DELETE ON public.profiles
  FOR EACH ROW
  EXECUTE FUNCTION public.anonymise_legal_acceptances();

COMMENT ON COLUMN public.legal_acceptances.user_id IS
  'Who accepted. NULL once the account is gone — the row survives the person.';
COMMENT ON COLUMN public.legal_acceptances.subject_hash IS
  'Set only when the account is deleted: sha256 of the account id, hex. Links a deleted person''s rows to each other and to nothing else.';
