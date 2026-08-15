-- German and Ukrainian become languages this platform serves.
--
-- Everything below is the database half of the five-step checklist in
-- `backend/app/schemas/locale.py`. The application half — LOCALE_CODES, the
-- display names the translation prompt speaks to the model in, the backend
-- notification catalog — ships in the same PR.
--
-- What each constraint was holding back
-- =====================================
-- `profiles.preferred_locale` decides what a person is shown. Until now it
-- refused any value but 'ru' or 'en', so a German-speaking student could not
-- have German as their language even if every word of the course existed in it.
--
-- `courses.source_locale` records the language a course was written in. A
-- German teacher writing in German would have had their course recorded as
-- Russian or English — and the pipeline would then have "translated" German
-- into German and left the actual target languages empty.
--
-- `content_versions.locale` was deliberately left without a CHECK when that
-- table was designed, precisely so that adding a language would be an INSERT
-- rather than DDL. That decision holds; nothing to do there.
--
-- handle_new_user, rewritten whole
-- ================================
-- The signup trigger hardcodes the locale allowlist. It cannot be ALTERed —
-- plpgsql function bodies are replaced entire — so this is the fourth full
-- rewrite of it. The body is otherwise byte-identical to what is in production
-- today (verified against `pg_get_functiondef` before writing this); the only
-- change is the four-locale list, and this comment.
--
-- A signup that names an unsupported locale still falls to 'ru' rather than
-- failing. A person's first request must not 500 because their browser asked
-- for a language we do not have yet.

ALTER TABLE public.profiles
    DROP CONSTRAINT IF EXISTS profiles_preferred_locale_check;

ALTER TABLE public.profiles
    ADD CONSTRAINT profiles_preferred_locale_check
    CHECK (preferred_locale::text = ANY (ARRAY['ru', 'en', 'de', 'uk']));

ALTER TABLE public.courses
    DROP CONSTRAINT IF EXISTS courses_source_locale_check;

ALTER TABLE public.courses
    ADD CONSTRAINT courses_source_locale_check
    CHECK (source_locale::text = ANY (ARRAY['ru', 'en', 'de', 'uk']));

CREATE OR REPLACE FUNCTION public.handle_new_user()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
AS $function$
DECLARE
  claimed_role text := NEW.raw_user_meta_data->>'role';
  safe_role text;
BEGIN
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
      WHEN NEW.raw_user_meta_data->>'preferred_locale' IN ('ru', 'en', 'de', 'uk')
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
$function$;

COMMENT ON COLUMN public.profiles.preferred_locale IS
    'The language this person is served. ru | en | de | uk.';

COMMENT ON COLUMN public.courses.source_locale IS
    'The language the course was authored in, derived from the teacher at creation. ru | en | de | uk.';
