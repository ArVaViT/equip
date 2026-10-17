-- An account can be deleted by its owner.
--
-- The privacy policy promised it ("delete your account at any time from your
-- profile") and the product had no such button: deletion was a letter to
-- support and a row changed by hand. `DELETE /api/v1/users/me` is that button.
--
-- It is a soft deletion, the same one the admin route has made since
-- 20260608190000: `deactivated_at` is set, every existing guard applies
-- (`get_current_user` answers 403, course mail and reminders skip the
-- account, rosters filter it), and nothing the school keeps -- marks,
-- submissions, certificates, enrolments -- is touched.
--
-- What this column adds is *who* closed it and *that it was closed by its
-- owner*:
--
--   * other people see «Deleted user» instead of the name, and no email or
--     photo, wherever the API shows one person to another
--     (`app.services.deleted_person`). An account switched off by an
--     administrator keeps its name -- that is a suspension, not a departure;
--   * the owner can come back: signing in shows a restore screen, and a link
--     emailed to the account's address is the proof that may clear both columns
--     (`POST /api/v1/users/me/restore`). An administrator's deactivation has
--     no such door.
--
-- A deleted account is always a deactivated one: the CHECK makes it
-- impossible to have the marker without the lock, so no code path can
-- forget the second write and leave a "deleted" account that still signs in.

ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conname = 'profiles_deleted_is_deactivated_check'
       AND conrelid = 'public.profiles'::regclass
  ) THEN
    ALTER TABLE public.profiles
      ADD CONSTRAINT profiles_deleted_is_deactivated_check
      CHECK (deleted_at IS NULL OR deactivated_at IS NOT NULL);
  END IF;
END
$$;

COMMENT ON COLUMN public.profiles.deleted_at IS
  'Set when the owner deleted the account themselves (DELETE /users/me); always '
  'together with deactivated_at. Others are shown «Deleted user» with no email or '
  'photo; the owner may restore it through a link emailed to the account''s '
  'address. See 20261016130000.';

-- ---------------------------------------------------------------------
-- A client may not write it, and a closed account may not be edited
-- ---------------------------------------------------------------------
--
-- `authenticated` holds UPDATE on its own row (profiles_update_own_safe_fields),
-- so a column the trigger does not name is writable from the browser -- the
-- lesson of 20260912120000. Clearing `deleted_at` from the browser would
-- un-hide the name without restoring the account; setting it would hide a name
-- without closing anything. Both are the server's to do.
--
-- And one more rule the earlier versions did not need: a deactivated account
-- edits nothing at all through PostgREST. Supabase still issues a session to
-- whoever proves the address -- that is the door back for a deleted account --
-- and with it the browser could rename a profile the API refuses to serve.

CREATE OR REPLACE FUNCTION public.profiles_protect_immutable_fields()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
  -- Only enforce for client-side writes. FastAPI connects as
  -- ``postgres`` and the service_role JWT becomes ``service_role`` --
  -- both bypass this guard so legitimate server mutations keep working.
  IF current_user <> 'authenticated' THEN
    RETURN NEW;
  END IF;
  IF OLD.deactivated_at IS NOT NULL THEN
    RAISE EXCEPTION 'a deactivated account cannot be edited'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.id IS DISTINCT FROM OLD.id THEN
    RAISE EXCEPTION 'profiles.id is immutable from client writes'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.role IS DISTINCT FROM OLD.role THEN
    RAISE EXCEPTION 'profiles.role can only be changed by an administrator'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.email IS DISTINCT FROM OLD.email THEN
    RAISE EXCEPTION 'profiles.email is mirrored from auth.users and cannot be changed directly'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.created_at IS DISTINCT FROM OLD.created_at THEN
    RAISE EXCEPTION 'profiles.created_at is immutable'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.organization_id IS DISTINCT FROM OLD.organization_id THEN
    RAISE EXCEPTION 'profiles.organization_id is granted by an invitation or a director, not by the client'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.deactivated_at IS DISTINCT FROM OLD.deactivated_at THEN
    RAISE EXCEPTION 'profiles.deactivated_at can only be changed by an administrator'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.deleted_at IS DISTINCT FROM OLD.deleted_at THEN
    RAISE EXCEPTION 'profiles.deleted_at is recorded by the server'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.onboarding_completed_at IS DISTINCT FROM OLD.onboarding_completed_at THEN
    RAISE EXCEPTION 'profiles.onboarding_completed_at is recorded by the server'
      USING ERRCODE = 'check_violation';
  END IF;
  -- Reserved until a number can be verified: an unverified phone written
  -- from the browser would later look like a confirmed one.
  IF NEW.phone IS DISTINCT FROM OLD.phone THEN
    RAISE EXCEPTION 'profiles.phone cannot be set until phone verification exists'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$;

COMMENT ON POLICY profiles_update_own_safe_fields ON public.profiles IS
  'Self-update is gated on row ownership. Column-level immutability '
  '(id / role / email / created_at / organization_id / deactivated_at / '
  'deleted_at / onboarding_completed_at / phone), and the rule that a '
  'deactivated account edits nothing, are enforced by '
  'trg_profiles_protect_immutable_fields, which only fires for the '
  'authenticated role so service-mediated writes (FastAPI postgres '
  'connection, service_role JWT) can still legitimately change those '
  'columns. The safe fields that remain are full_name, avatar_url, '
  'preferred_locale, locale_source, time_zone, time_zone_source, '
  'birth_date, country_code, region, city, church and email_off.';
