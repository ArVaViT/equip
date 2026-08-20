-- English is the last resort.
--
-- The decision
-- ============
-- A visitor's language comes from their browser or their system. When we do
-- not serve that language, the answer must be English — not Russian.
--
-- `profiles.preferred_locale` has defaulted to 'ru' since the column was
-- added (20260425010000), when the platform was Russian-only and "the
-- language we fall back to" and "the language the content is written in"
-- were the same fact. They stopped being the same fact the day a second
-- language shipped. The default never moved, so an account created without
-- a language — a Google sign-up carries none, see 20260817131500 — was
-- written down as Russian. The application half of this change moves
-- `DEFAULT_LOCALE` in `backend/app/schemas/locale.py` and the ORM default in
-- `backend/app/models/user.py`; this file is the database half.
--
-- What this does NOT touch
-- ========================
-- * Existing rows. Nobody's stored language changes. Accounts marked
--   `locale_source = 'chosen'` were chosen; accounts marked 'detected' were
--   read off a real browser; and the 'default' rows are already handled the
--   right way by the client, which replaces them with what the reader is
--   actually reading (20260817131500). Rewriting Russian to English under
--   people who have been using the product in Russian would be the original
--   defect pointed the other way.
-- * `courses.source_locale`. Courses are AUTHORED in Russian. That is the
--   language the pipeline translates *from*, and it has nothing to do with
--   what an unknown visitor is shown. Its default stays 'ru'.
--
-- handle_new_user, rewritten whole
-- ================================
-- Sixth full rewrite (fifth was 20260817131500): plpgsql bodies are replaced
-- entire, never ALTERed. The body below is byte-identical to the fifth apart
-- from one token — the ELSE branch of the locale CASE, 'ru' -> 'en' — and
-- this comment. A signup that names an unsupported locale still falls
-- through rather than failing: a person's first request must not 500 because
-- their browser asked for a language we do not have.
--
-- Note that the fallback list itself needed no widening here. It was
-- ('ru','en') in 20260514212219 and was widened to all four locales by
-- 20260815014042; only the ELSE value is behind.

ALTER TABLE public.profiles
    ALTER COLUMN preferred_locale SET DEFAULT 'en';

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
    -- The signup said nothing about language, so neither do we: 'en' here
    -- means "we had to write something down", and the 'default' below is
    -- what says so out loud. The client replaces both the moment it sees
    -- the reader's actual browser language.
    CASE WHEN has_locale THEN claimed_locale ELSE 'en' END,
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

COMMENT ON COLUMN public.profiles.preferred_locale IS
    'The language this person is served. ru | en | de | uk. Defaults to en — the answer for a reader we know nothing about; read locale_source to tell that apart from a language somebody chose.';
