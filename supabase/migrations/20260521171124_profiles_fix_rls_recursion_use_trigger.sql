-- Supabase migration: profiles_fix_rls_recursion_use_trigger
--
-- SEV-1 PRODUCTION OUTAGE FIX. Migration
-- ``20260515185101_profiles_lock_email_self_update.sql`` introduced an
-- RLS WITH CHECK clause that issues subqueries against the SAME
-- ``public.profiles`` table the policy is attached to:
--
--   WITH CHECK (
--     auth.uid() = id
--     AND role = (SELECT p.role FROM public.profiles p WHERE p.id = auth.uid())
--     AND email = (SELECT p.email FROM public.profiles p WHERE p.id = auth.uid())
--     AND created_at IS NOT DISTINCT FROM
--           (SELECT p.created_at FROM public.profiles p WHERE p.id = auth.uid())
--   )
--
-- Postgres evaluates the subqueries with RLS applied to the same
-- relation under the same role and raises:
--
--   ERROR 42P17: infinite recursion detected in policy for relation
--                "profiles"
--
-- Every PostgREST ``PATCH /rest/v1/profiles`` call from an
-- ``authenticated`` JWT has been returning 500 since the migration
-- shipped. This breaks every client-side profile write the SPA does:
--
--   * SetupStep first-run save (name + avatar)
--   * ProfilePage inline name edit (the user-reported "не удалось")
--   * Avatar upload (storage write succeeds, then the ``avatar_url``
--     PATCH fails so the new image silently never attaches)
--   * Any other ``usersService.updateProfile`` caller
--
-- The original intent of the WITH CHECK was correct -- pin
-- ``role`` / ``email`` / ``id`` / ``created_at`` so PostgREST clients
-- cannot spoof identity columns. The implementation just picked the
-- wrong tool: WITH CHECK can only see NEW row values, so verifying
-- "this column didn't change" forces a self-select.
--
-- Fix: enforce immutability with a BEFORE UPDATE trigger that has
-- direct access to both OLD and NEW. The trigger only fires for the
-- ``authenticated`` role -- service_role and the FastAPI ``postgres``
-- connection legitimately need to mutate ``role`` (admin promotion in
-- ``/users/admin/users/{id}/role``) and ``email`` (future auth.users
-- email-change sync). The RLS policy is simplified back to a clean
-- ownership check.
--
-- Security equivalence with the broken policy:
--   * role     immutable -> trigger raises (was: subquery match)
--   * email    immutable -> trigger raises (was: subquery match)
--   * id       immutable -> trigger raises (was: implicit via id = id)
--   * created_at immutable -> trigger raises (was: subquery match)
-- All four exploit paths the prior migration closed remain closed.

-- 1. Replace the broken policy with a simple ownership-only check.
DROP POLICY IF EXISTS profiles_update_own_safe_fields ON public.profiles;

CREATE POLICY profiles_update_own_safe_fields ON public.profiles
  FOR UPDATE
  TO authenticated
  USING ((SELECT auth.uid()) = id)
  WITH CHECK ((SELECT auth.uid()) = id);

COMMENT ON POLICY profiles_update_own_safe_fields ON public.profiles IS
  'Self-update is gated on row ownership. Column-level immutability '
  '(role / email / id / created_at) is enforced by '
  'trg_profiles_protect_immutable_fields, which only fires for the '
  'authenticated role so service-mediated writes (FastAPI postgres '
  'connection, service_role JWT) can still legitimately change those '
  'columns.';

-- 2. Trigger that blocks attempts to change protected columns from
--    the ``authenticated`` role.
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
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_profiles_protect_immutable_fields ON public.profiles;
CREATE TRIGGER trg_profiles_protect_immutable_fields
  BEFORE UPDATE ON public.profiles
  FOR EACH ROW
  EXECUTE FUNCTION public.profiles_protect_immutable_fields();

COMMENT ON FUNCTION public.profiles_protect_immutable_fields() IS
  'Enforces column-level immutability of identity fields '
  '(id / role / email / created_at) for the authenticated role. '
  'Replaces the self-referencing WITH CHECK clauses that caused '
  '42P17 infinite-recursion errors on every client profile update.';
