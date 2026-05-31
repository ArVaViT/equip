-- Remove the pending_teacher role.
--
-- Decision 2026-05-31: admin manually decides who's a teacher. No
-- self-service teacher application path. Existing pending_teacher
-- rows downgrade to student; admin will promote individuals as
-- needed via the standard role-change admin endpoint.

-- 1. Rewrite the signup trigger so a 'teacher' claim no longer flips
--    the new profile to pending_teacher. The new whitelist is just
--    {student}: anything else (including 'teacher', 'admin', 'pending_teacher')
--    falls back to student.

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
  -- Self-service signups always land as student. Teacher and admin
  -- roles are admin-assignment only; the old 'wants to be a teacher'
  -- → pending_teacher path is gone.
  safe_role := CASE
    WHEN claimed_role = 'student' THEN 'student'
    ELSE 'student'
  END;

  INSERT INTO public.profiles (id, email, full_name, role, preferred_locale)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', ''),
    safe_role,
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
  RETURN NEW;
END;
$$;

-- 2. Downgrade any existing pending_teacher rows to student so we're
--    not leaving accounts in a dead state. Admin can promote them
--    back to teacher manually if the original intent stood.

UPDATE public.profiles
SET role = 'student'
WHERE role = 'pending_teacher';
