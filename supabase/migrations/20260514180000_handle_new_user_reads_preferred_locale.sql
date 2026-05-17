-- Supabase migration: handle_new_user_reads_preferred_locale
-- Version: 20260514180000
--
-- Extends the auth.users → profiles trigger to carry ``preferred_locale``
-- across from ``raw_user_meta_data`` (set by the frontend's signup form
-- from the user's browser language) instead of always falling through
-- to the column default 'ru'.
--
-- Why this matters: an English-speaking visitor who sees the
-- registration form in English would, on signup, immediately get
-- snapped back to Russian on first login (profile.preferred_locale
-- wins in `useLocaleSync`). Sourcing the value from the browser keeps
-- the language they registered in as the default.
--
-- Email signup populates `raw_user_meta_data.preferred_locale` from
-- the frontend (`services/auth.ts`). Google-OAuth signup does not pass
-- options upfront, so its first profile still defaults to 'ru' — that
-- path is handled separately by post-OAuth reconciliation in the
-- frontend.

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  INSERT INTO public.profiles (id, email, full_name, role, preferred_locale)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', ''),
    COALESCE(NEW.raw_user_meta_data->>'role', 'student'),
    -- Whitelist against the same supported set as
    -- ``profiles_preferred_locale_check``. Anything unknown falls back
    -- to the column default ('ru') so a malformed metadata blob can
    -- never violate the CHECK constraint and abort the trigger.
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
