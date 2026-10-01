-- A sweep looking at a course is not an edit of the course.
--
-- The translation sweep stamps `courses.translations_checked_at` on every
-- course it examines, and `trg_courses_updated_at` set `updated_at = now()`
-- on every UPDATE, so each look moved the course's "last changed" time.
-- In production that was 57 819 such updates in 13 days — about three a
-- minute for six courses — and `updated_at` said every course had been
-- touched a minute ago (`completeness.py` already had to route around it).
--
-- Skipping the bump in the ORM is not enough: the trigger writes `now()`
-- whatever the statement says. So courses get their own trigger function:
-- when nothing but `translations_checked_at` (and `updated_at` itself)
-- changed, `updated_at` keeps its old value; any other change bumps it as
-- before.

CREATE OR REPLACE FUNCTION public.courses_touch_updated_at() RETURNS trigger
    LANGUAGE plpgsql
    SET search_path TO 'pg_catalog', 'public'
    AS $$
BEGIN
  IF (to_jsonb(NEW) - 'translations_checked_at' - 'updated_at')
     IS NOT DISTINCT FROM (to_jsonb(OLD) - 'translations_checked_at' - 'updated_at') THEN
    NEW.updated_at = OLD.updated_at;
  ELSE
    NEW.updated_at = now();
  END IF;
  RETURN NEW;
END;
$$;

-- A trigger function is not an API (20260923011620).
REVOKE ALL ON FUNCTION public.courses_touch_updated_at() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.courses_touch_updated_at() FROM anon, authenticated;

DROP TRIGGER IF EXISTS trg_courses_updated_at ON public.courses;
CREATE TRIGGER trg_courses_updated_at BEFORE UPDATE ON public.courses
  FOR EACH ROW EXECUTE FUNCTION public.courses_touch_updated_at();
