-- A profile knows where and when you are.
--
-- The profile page gains optional personal details and a time zone.
-- Everything here is optional to the person; nothing is required to use
-- the platform.
--
--   time_zone         IANA name ("America/Indiana/Indianapolis"). The
--                     database and the API keep every instant in UTC;
--                     this is only the zone a person reads them in. A
--                     live lesson a teacher sets for 8:00 in Indiana is
--                     one instant, shown at 5:00 in California and 14:00
--                     in Berlin.
--   time_zone_source  how it got its value, the same three states as
--                     locale_source: 'default' (nobody said), 'detected'
--                     (the browser's zone), 'chosen' (the person picked
--                     it, and nothing automatic may overwrite it).
--   phone             reserved. Until a number can be verified, a client
--                     may not write one: the column is guarded below like
--                     role and email, and the profile shows it disabled.
--   birth_date, country_code, region, city, church
--                     optional, written by the person themselves.
--
-- No street address: a Bible school has no use for one, and storing it
-- would be a liability without a purpose.

ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS time_zone text,
  ADD COLUMN IF NOT EXISTS time_zone_source text NOT NULL DEFAULT 'default',
  ADD COLUMN IF NOT EXISTS phone text,
  ADD COLUMN IF NOT EXISTS birth_date date,
  ADD COLUMN IF NOT EXISTS country_code text,
  ADD COLUMN IF NOT EXISTS region text,
  ADD COLUMN IF NOT EXISTS city text,
  ADD COLUMN IF NOT EXISTS church text;

ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_time_zone_source_check;
ALTER TABLE public.profiles ADD CONSTRAINT profiles_time_zone_source_check
  CHECK (time_zone_source IN ('default', 'detected', 'chosen'));
ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_country_code_check;
ALTER TABLE public.profiles ADD CONSTRAINT profiles_country_code_check
  CHECK (country_code IS NULL OR country_code ~ '^[A-Z]{2}$');
ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_personal_text_lengths_check;
ALTER TABLE public.profiles ADD CONSTRAINT profiles_personal_text_lengths_check
  CHECK (
    (time_zone IS NULL OR char_length(time_zone) BETWEEN 1 AND 64)
    AND (phone IS NULL OR char_length(phone) BETWEEN 4 AND 32)
    AND (region IS NULL OR char_length(region) BETWEEN 1 AND 100)
    AND (city IS NULL OR char_length(city) BETWEEN 1 AND 100)
    AND (church IS NULL OR char_length(church) BETWEEN 1 AND 200)
  );
ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_birth_date_floor_check;
ALTER TABLE public.profiles ADD CONSTRAINT profiles_birth_date_floor_check
  CHECK (birth_date IS NULL OR birth_date >= DATE '1900-01-01');

-- What a CHECK cannot say: that the zone is a real one, and that a birth
-- date is not in the future (current_date is not immutable). Checked on
-- every write, from any role — a wrong zone would shift every time the
-- person reads.
CREATE OR REPLACE FUNCTION public.profiles_validate_personal_fields()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
  IF NEW.time_zone IS NOT NULL
     AND (TG_OP = 'INSERT' OR NEW.time_zone IS DISTINCT FROM OLD.time_zone)
     AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_timezone_names WHERE name = NEW.time_zone) THEN
    RAISE EXCEPTION 'profiles.time_zone must be an IANA time zone name'
      USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.birth_date IS NOT NULL AND NEW.birth_date > current_date THEN
    RAISE EXCEPTION 'profiles.birth_date cannot be in the future'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_profiles_validate_personal_fields ON public.profiles;
CREATE TRIGGER trg_profiles_validate_personal_fields
  BEFORE INSERT OR UPDATE ON public.profiles
  FOR EACH ROW EXECUTE FUNCTION public.profiles_validate_personal_fields();

REVOKE EXECUTE ON FUNCTION public.profiles_validate_personal_fields() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.profiles_validate_personal_fields() FROM anon;
REVOKE EXECUTE ON FUNCTION public.profiles_validate_personal_fields() FROM authenticated;

-- The phone joins the columns a client may not write.
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
  'onboarding_completed_at / phone) is enforced by '
  'trg_profiles_protect_immutable_fields, which only fires for the '
  'authenticated role so service-mediated writes (FastAPI postgres '
  'connection, service_role JWT) can still legitimately change those '
  'columns. The safe fields that remain are full_name, avatar_url, '
  'preferred_locale, locale_source, time_zone, time_zone_source, '
  'birth_date, country_code, region, city and church.';
