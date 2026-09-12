-- Three columns a client must not write.
--
-- `profiles_protect_immutable_fields` has guarded `id`, `role`, `email`
-- and `created_at` since 2026-05-21. Three columns added since carry the
-- same weight and were never added to it:
--
--   organization_id       -- which school you belong to
--   deactivated_at        -- whether the platform still lets you in
--   onboarding_completed_at
--
-- `authenticated` holds table-level UPDATE on `profiles` and
-- `profiles_update_own_safe_fields` allows the own row, so anything the
-- trigger does not name is writable from the browser with the anon key
-- and a session. Verified against production on 2026-09-12 inside a
-- rolled-back transaction: the write passed both the policy and the
-- trigger and failed only on the foreign key, which a real organization
-- id satisfies.
--
-- What each one is worth to an attacker:
--
--   organization_id -- `courses_select_published` and
--     `cohorts_select_own_organization` both admit a reader whose
--     `current_organization_id()` matches the row. Writing another
--     school's id to your own profile is how you read that school's
--     institute courses and cohorts.
--
--   deactivated_at -- `get_current_user` answers 403
--     ACCOUNT_DEACTIVATED while it is set. An account that can clear it
--     cannot be shut off.
--
--   onboarding_completed_at -- the smallest of the three: it skips the
--     first-run flow, which includes the legal consent step. A consent
--     record that can be stepped over is not a consent record.
--
-- The shape is the existing one: enforced only for the `authenticated`
-- role, so FastAPI (connecting as `postgres`) and service_role writes --
-- which is how a director is appointed and how an invitation grants
-- membership -- keep working.

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
  IF NEW.onboarding_completed_at IS DISTINCT FROM OLD.onboarding_completed_at THEN
    RAISE EXCEPTION 'profiles.onboarding_completed_at is recorded by the server'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$;

COMMENT ON POLICY profiles_update_own_safe_fields ON public.profiles IS
  'Self-update is gated on row ownership. Column-level immutability '
  '(id / role / email / created_at / organization_id / deactivated_at / '
  'onboarding_completed_at) is enforced by '
  'trg_profiles_protect_immutable_fields, which only fires for the '
  'authenticated role so service-mediated writes (FastAPI postgres '
  'connection, service_role JWT) can still legitimately change those '
  'columns. The safe fields that remain are full_name, avatar_url, '
  'preferred_locale and locale_source.';
