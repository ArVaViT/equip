-- An invitation is fulfilled when the person arrives, by whatever door.
--
-- A pending invitation used to stay pending until its link was clicked, even
-- after the person it was sent to had joined the course on their own, been
-- added to a cohort by a director, or been placed in the organization. The
-- list of invitations then showed "pending" for somebody who was already
-- studying, and "Resend" was the button next to it.
--
-- `fulfilled` is its own status rather than `accepted`, because the two
-- answer different questions for the person who sent the invitation:
-- `accepted` means the link was used; `fulfilled` means the person got what
-- the invitation offered some other way. `fulfilled_at` says when.
--
-- What "got what it offered" means, per scope. The person is the profile
-- whose email matches the invitation's, ignoring case:
--
--   platform      -- the person has an account.
--   organization  -- the person is a member of the inviting organization.
--   course        -- the person is enrolled on the course, solo or in any
--                    cohort. Membership is NOT required: somebody who
--                    joined a public course by themselves is on the
--                    course, which is what the invitation was for. Using
--                    the link afterwards still grants the membership --
--                    see accept_invitation, which accepts a fulfilled
--                    invitation for its own invitee.
--
-- and in every scope, the person's role is at least the one offered, in the
-- order student < teacher < director < admin (the same order accepting
-- uses, app.models.user.higher_role). A teacher invitation is therefore not
-- fulfilled by somebody enrolling as a student.
--
-- Expiry is not a condition. It is computed, not stored: an expired
-- invitation still reads `pending`, and in the list it reads "expired" --
-- next to a "Resend" button, for a person who is already there. Closing it
-- says what is true.
--
-- WHERE the rule runs: in the database, on the writes that can make it true.
-- Enrolment happens in at least four places in the backend (self-enrolment,
-- a cohort gaining a student, a cohort gaining a course, accepting an
-- invitation), organization membership and roles in three more, and a new
-- account is created by `handle_new_user` on auth.users, which the backend
-- never sees. A service function called from each of those is a rule that
-- the next caller forgets. A trigger is not. The function below is the only
-- statement of the rule; the triggers only decide whom to run it for, and
-- the backfill (the next migration) runs it for everybody.

ALTER TABLE public.invitations
  ADD COLUMN fulfilled_at timestamp with time zone;

-- Prod's constraint carries the name Postgres generated for it; the models
-- have called it chk_invitations_status. Drop either, add one.
ALTER TABLE public.invitations DROP CONSTRAINT IF EXISTS invitations_status_check;
ALTER TABLE public.invitations DROP CONSTRAINT IF EXISTS chk_invitations_status;
ALTER TABLE public.invitations
  ADD CONSTRAINT invitations_status_check
    CHECK (status IN ('pending', 'accepted', 'revoked', 'fulfilled'));

-- The timestamp and the status agree in both directions.
ALTER TABLE public.invitations
  ADD CONSTRAINT chk_invitations_fulfilled_at_matches_status
    CHECK ((status = 'fulfilled') = (fulfilled_at IS NOT NULL));

COMMENT ON COLUMN public.invitations.fulfilled_at IS
  'When the invited person got what this invitation offered without using '
  'its link (status = fulfilled). Set by public.fulfil_pending_invitations.';


CREATE OR REPLACE FUNCTION public.fulfil_pending_invitations(p_profile_id uuid)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO ''
AS $$
DECLARE
  closed integer;
BEGIN
  -- p_profile_id NULL means every profile: the backfill.
  UPDATE public.invitations AS i
  SET status = 'fulfilled',
      fulfilled_at = now()
  FROM public.profiles AS p
  WHERE i.status = 'pending'
    AND (p_profile_id IS NULL OR p.id = p_profile_id)
    AND lower(p.email) = lower(i.email)
    AND (CASE p.role WHEN 'student' THEN 0 WHEN 'teacher' THEN 1 WHEN 'director' THEN 2 WHEN 'admin' THEN 3 ELSE -1 END)
        >= (CASE i.role WHEN 'student' THEN 0 WHEN 'teacher' THEN 1 WHEN 'director' THEN 2 WHEN 'admin' THEN 3 ELSE 4 END)
    AND CASE i.scope
          WHEN 'platform' THEN true
          WHEN 'organization' THEN p.organization_id IS NOT DISTINCT FROM i.organization_id
          WHEN 'course' THEN EXISTS (
            SELECT 1 FROM public.enrollments AS e
            WHERE e.user_id = p.id AND e.course_id = i.course_id
          )
          ELSE false
        END;
  GET DIAGNOSTICS closed = ROW_COUNT;
  RETURN closed;
END;
$$;

COMMENT ON FUNCTION public.fulfil_pending_invitations(uuid) IS
  'Closes, as fulfilled, every pending invitation whose person already has '
  'what it offers (see migration 20260917023526). NULL = every profile.';


CREATE OR REPLACE FUNCTION public.fulfil_invitations_after_change() RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO ''
AS $$
DECLARE
  person uuid;
BEGIN
  IF TG_TABLE_NAME = 'enrollments' THEN
    PERFORM public.fulfil_pending_invitations(NEW.user_id);
  ELSIF TG_TABLE_NAME = 'profiles' THEN
    PERFORM public.fulfil_pending_invitations(NEW.id);
  ELSIF TG_TABLE_NAME = 'invitations' THEN
    -- An invitation written for somebody who is already there.
    FOR person IN
      SELECT p.id FROM public.profiles AS p WHERE lower(p.email) = lower(NEW.email)
    LOOP
      PERFORM public.fulfil_pending_invitations(person);
    END LOOP;
  END IF;
  RETURN NULL;
END;
$$;

-- SECURITY DEFINER so the close happens whoever made the change: a write by
-- `authenticated` through PostgREST would otherwise meet the invitations
-- RLS and close nothing, silently. Nobody calls either function directly.
REVOKE EXECUTE ON FUNCTION public.fulfil_pending_invitations(uuid) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.fulfil_invitations_after_change() FROM PUBLIC, anon, authenticated;

CREATE TRIGGER trg_enrollments_fulfil_invitations
  AFTER INSERT OR UPDATE OF user_id, course_id ON public.enrollments
  FOR EACH ROW EXECUTE FUNCTION public.fulfil_invitations_after_change();

CREATE TRIGGER trg_profiles_created_fulfil_invitations
  AFTER INSERT ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION public.fulfil_invitations_after_change();

CREATE TRIGGER trg_profiles_changed_fulfil_invitations
  AFTER UPDATE OF role, organization_id, email ON public.profiles
  FOR EACH ROW
  WHEN (OLD.role IS DISTINCT FROM NEW.role
        OR OLD.organization_id IS DISTINCT FROM NEW.organization_id
        OR OLD.email IS DISTINCT FROM NEW.email)
  EXECUTE FUNCTION public.fulfil_invitations_after_change();

CREATE TRIGGER trg_invitations_created_fulfil
  AFTER INSERT ON public.invitations
  FOR EACH ROW
  WHEN (NEW.status = 'pending')
  EXECUTE FUNCTION public.fulfil_invitations_after_change();
