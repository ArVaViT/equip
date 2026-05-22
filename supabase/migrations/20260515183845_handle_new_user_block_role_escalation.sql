-- Supabase migration: handle_new_user_block_role_escalation
-- Version: 20260515183810
--
-- CRITICAL SECURITY FIX: privilege escalation via user_metadata.
--
-- The previous ``handle_new_user`` trigger read
-- ``NEW.raw_user_meta_data->>'role'`` and dropped that value verbatim
-- into ``profiles.role``. Because ``raw_user_meta_data`` is fully
-- user-controlled (any client can pass arbitrary keys to
-- ``supabase.auth.signUp({ options: { data: { ... } } })``), an
-- attacker could sign up with ``role: 'admin'`` and immediately have
-- an ``admin`` row in ``profiles`` — full administrative access to
-- the platform on first sign-in.
--
-- This is exactly the Supabase trap documented in the security skill:
-- "Never use user_metadata claims in JWT-based authorization
-- decisions. raw_user_meta_data is user-editable."
--
-- Fix: whitelist the value against the supported self-service roles
-- (``student``, ``pending_teacher``). A user claim of ``teacher`` is
-- downgraded to ``pending_teacher`` so the admin-approval flow
-- (``PendingTeachersCard``) actually gates teacher creation.
-- Anything else falls back to ``student``. ``admin`` is never
-- self-assignable.
--
-- Existing rows are not modified; admin promotion remains an
-- explicit operation via ``PUT /users/admin/users/{id}/role``.

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
  claimed_role text := NEW.raw_user_meta_data->>'role';
  safe_role text;
BEGIN
  -- Whitelist roles that a user is allowed to self-assign at signup.
  -- ``teacher`` claims drop to ``pending_teacher`` so an admin still
  -- has to approve before the user gets teacher privileges. ``admin``
  -- and anything else fall through to ``student``.
  safe_role := CASE
    WHEN claimed_role = 'student' THEN 'student'
    WHEN claimed_role IN ('teacher', 'pending_teacher') THEN 'pending_teacher'
    ELSE 'student'
  END;

  INSERT INTO public.profiles (id, email, full_name, role, preferred_locale)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', ''),
    safe_role,
    -- Whitelist preferred_locale the same way; matches the column CHECK.
    CASE
      WHEN NEW.raw_user_meta_data->>'preferred_locale' IN ('ru', 'en')
        THEN NEW.raw_user_meta_data->>'preferred_locale'
      ELSE 'ru'
    END
  )
  ON CONFLICT (id) DO UPDATE
  SET
    email = EXCLUDED.email,
    full_name = CASE
      WHEN EXCLUDED.full_name <> ''
        THEN EXCLUDED.full_name
      ELSE public.profiles.full_name
    END;
    -- Intentionally NOT updating ``role`` on conflict: that would let
    -- a re-signup attempt overwrite a downgraded role with whatever
    -- the metadata claims. Role changes go through the admin path.
  RETURN NEW;
END;
$$;
