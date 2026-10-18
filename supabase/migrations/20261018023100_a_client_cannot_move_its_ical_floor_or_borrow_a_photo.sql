-- A client cannot move its iCal floor, or point its photo at somebody else's.
--
-- `authenticated` holds table-level UPDATE on `profiles`, and
-- `profiles_update_own_safe_fields` lets a session write its own row; the
-- columns that must not move are listed in `profiles_protect_immutable_fields`.
-- Two were missing.
--
-- `calendar_ical_min_iat` is the rotation floor of the iCal feed
-- (`backend/app/api/v1/calendar_ical.py`): the feed refuses a token issued
-- before it, and issuing a new link raises it. Written from the browser it
-- could be lowered again -- to 0 -- and every link the person had switched
-- off would answer once more. Only the API writes it, as `postgres`, which
-- this trigger lets through.
--
-- `avatar_url` is shown to strangers (the course's «Автор» tab, the school
-- page). A client could store any string there: another member's photo, or a
-- third-party address. A new value written from the browser must now be an
-- object in the `avatars` bucket under the person's own folder, or NULL: the
-- same-origin proxy path `storageService.uploadAvatar` returns
-- (`/img/avatars/<user id>/<file>`), or the full Storage URL
-- (`<host>/storage/v1/object/public/avatars/<user id>/<file>`) an older client
-- wrote. In the latter the host is not pinned: the database does not know its
-- own public address (a restore, the local e2e stack), and the CSP's `img-src`
-- already refuses foreign hosts in the browser. Only a change is checked, so a value written
-- by the server (a Google sign-up picture) does not lock the row; production
-- had no avatars at all on 2026-10-17.
--
-- CREATE OR REPLACE: idempotent; the function body is the 20261016130000 one
-- with the two checks added before `RETURN NEW`.

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
  -- The iCal rotation floor: lowered, it revives every switched-off link.
  IF NEW.calendar_ical_min_iat IS DISTINCT FROM OLD.calendar_ical_min_iat THEN
    RAISE EXCEPTION 'profiles.calendar_ical_min_iat is recorded by the server'
      USING ERRCODE = 'check_violation';
  END IF;
  -- A photo is the person's own upload, or none. The frontend stores the
  -- same-origin proxy path (`/img/avatars/<id>/<file>`, storage.ts
  -- getPublicUrl); the full Storage URL is the older shape. One file name,
  -- no further slash, no leading dot, no percent-escape or backslash: no
  -- way out of the folder.
  IF NEW.avatar_url IS DISTINCT FROM OLD.avatar_url
     AND NEW.avatar_url IS NOT NULL
     AND NEW.avatar_url !~ ('^/img/avatars/' || NEW.id::text || '/[^/?#%\\.][^/?#%\\]*$')
     AND NEW.avatar_url !~ ('^https?://[^/?#]+/storage/v1/object/public/avatars/'
                            || NEW.id::text || '/[^/?#%\\.][^/?#%\\]*$') THEN
    RAISE EXCEPTION 'profiles.avatar_url must be an upload in the avatars bucket under the account''s own folder'
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$;

COMMENT ON POLICY profiles_update_own_safe_fields ON public.profiles IS
  'Self-update is gated on row ownership. Column-level immutability '
  '(id / role / email / created_at / organization_id / deactivated_at / '
  'deleted_at / onboarding_completed_at / phone / calendar_ical_min_iat), '
  'the shape of a new avatar_url (an upload in the avatars bucket under the '
  'account''s own folder), and the rule that a deactivated account edits '
  'nothing, are enforced by trg_profiles_protect_immutable_fields, which only '
  'fires for the authenticated role so service-mediated writes (FastAPI '
  'postgres connection, service_role JWT) can still legitimately change those '
  'columns. The safe fields that remain are full_name, avatar_url, '
  'preferred_locale, locale_source, time_zone, time_zone_source, '
  'birth_date, country_code, region, city, church and email_off.';
