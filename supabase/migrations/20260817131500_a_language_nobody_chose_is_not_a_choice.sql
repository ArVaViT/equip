-- A language nobody chose is not a preference.
--
-- The defect
-- ==========
-- `profiles.preferred_locale` is NOT NULL and defaults to 'ru', so every
-- account has an answer to "what language do you read in?" from the moment it
-- exists — including the accounts that were never asked.
--
-- Signing up with email carries the answer: the frontend passes the locale the
-- registration form was rendered in through `raw_user_meta_data`, and
-- handle_new_user reads it. Signing in with Google carries nothing. Supabase
-- fills `raw_user_meta_data` from the provider (name, avatar, email) and there
-- is no hook where our value could join it, so the CASE in handle_new_user
-- falls to its ELSE branch and the profile is created as Russian.
--
-- What that does to a German visitor: the landing page and the sign-up screen
-- are correctly in German (the browser said so). They click "Continue with
-- Google". They come back, the app loads their profile, and `useLocaleSync`
-- does exactly what it was built to do — the profile is the source of truth
-- for language, so it switches the interface to Russian. The first thing the
-- product does after they join is take away the language they were reading in.
--
-- Why a flag rather than making the column nullable
-- ================================================
-- Nullable would say "unknown" honestly, but `preferred_locale` is read in
-- forty places that would each have to decide what to do with NULL, and the
-- interesting distinction is not two-valued anyway. Three states are worth
-- telling apart:
--
--   'default'  — nobody has said anything. We put a value there so the column
--                could be NOT NULL, and it means nothing. The client replaces
--                it with the reader's actual browser language on first sight
--                and marks it 'detected'.
--   'detected' — inferred from the browser, and good enough to serve. Still
--                yields to an explicit choice, and to a later, better signal.
--   'chosen'   — a person picked this language: the switcher, the first-run
--                setup screen, or a sign-up form they filled in in it. Nothing
--                automatic may ever overwrite it. This is the state the whole
--                column was pretending to be in.
--
-- Existing accounts are marked 'chosen'. They have been using the product with
-- whatever locale they have; changing it under them on the strength of a
-- browser header would be the same defect pointed the other way.

ALTER TABLE public.profiles
    ADD COLUMN locale_source TEXT NOT NULL DEFAULT 'default';

ALTER TABLE public.profiles
    ADD CONSTRAINT profiles_locale_source_check
    CHECK (locale_source = ANY (ARRAY['default', 'detected', 'chosen']));

-- Everyone who already has an account keeps their language, untouched.
UPDATE public.profiles SET locale_source = 'chosen';

-- Fifth full rewrite (see 20260815014042 for the fourth): plpgsql bodies are
-- replaced whole, never altered. The only change is the locale_source column —
-- 'chosen' when the signup actually carried a language, 'default' when it did
-- not and we are about to guess.
CREATE OR REPLACE FUNCTION public.handle_new_user()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
DECLARE
  claimed_role text := NEW.raw_user_meta_data->>'role';
  claimed_locale text := NEW.raw_user_meta_data->>'preferred_locale';
  safe_role text;
  has_locale boolean;
BEGIN
  safe_role := CASE
    WHEN claimed_role = 'student' THEN 'student'
    ELSE 'student'
  END;

  has_locale := claimed_locale IN ('ru', 'en', 'de', 'uk');

  INSERT INTO public.profiles (id, email, full_name, role, preferred_locale, locale_source)
  VALUES (
    NEW.id,
    NEW.email,
    COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name', ''),
    safe_role,
    CASE WHEN has_locale THEN claimed_locale ELSE 'ru' END,
    CASE WHEN has_locale THEN 'chosen' ELSE 'default' END
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
$function$;

COMMENT ON COLUMN public.profiles.locale_source IS
    'How preferred_locale got its value. default = nobody was asked, the column just had to hold something; detected = inferred from the browser; chosen = a person picked it, and nothing automatic may overwrite it.';
