-- A sweep looking at a course is not an edit of the course.
--
-- Run by the schema-replay job against supabase/schema.sql on a clean
-- Postgres. The rule lives in public.courses_touch_updated_at and the
-- BEFORE UPDATE trigger on courses (migration 20260930150000): stamping
-- translations_checked_at leaves updated_at alone, even when the ORM's own
-- onupdate sends updated_at = now() in the same statement; any other change
-- still bumps it.
--
-- The backend's tests run on SQLite and cannot see a trigger.
--
-- Every check RAISEs on failure, so ON_ERROR_STOP aborts the job.

\set ON_ERROR_STOP on

BEGIN;

CREATE FUNCTION pg_temp.expect(p_actual text, p_expected text, p_what text) RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
  IF p_actual IS DISTINCT FROM p_expected THEN
    RAISE EXCEPTION 'COURSE UPDATED_AT BROKEN: % -- expected %, got %', p_what, p_expected, p_actual;
  END IF;
  RAISE NOTICE 'OK: %', p_what;
END;
$$;

INSERT INTO public.organizations (id, slug, public_name) VALUES
  ('30000000-0000-0000-0000-0000000000a1', 'updated-at-check', 'Updated-at check');

INSERT INTO public.courses (id, status, organization_id, updated_at) VALUES
  ('30000000-0000-0000-0000-00000000c001', 'published', '30000000-0000-0000-0000-0000000000a1', '2026-01-01T00:00:00Z');

UPDATE public.courses SET translations_checked_at = now()
 WHERE id = '30000000-0000-0000-0000-00000000c001';

SELECT pg_temp.expect(
  (SELECT updated_at::text FROM public.courses WHERE id = '30000000-0000-0000-0000-00000000c001'),
  ('2026-01-01T00:00:00Z'::timestamptz)::text,
  'the sweep stamping a course leaves updated_at alone');

-- What SQLAlchemy actually sends: onupdate=func.now() rides along.
UPDATE public.courses SET translations_checked_at = now(), updated_at = now()
 WHERE id = '30000000-0000-0000-0000-00000000c001';

SELECT pg_temp.expect(
  (SELECT updated_at::text FROM public.courses WHERE id = '30000000-0000-0000-0000-00000000c001'),
  ('2026-01-01T00:00:00Z'::timestamptz)::text,
  'the ORM''s own updated_at does not turn a look into an edit');

UPDATE public.courses SET status = 'publishing'
 WHERE id = '30000000-0000-0000-0000-00000000c001';

SELECT pg_temp.expect(
  (SELECT (updated_at > '2026-06-01T00:00:00Z')::text FROM public.courses WHERE id = '30000000-0000-0000-0000-00000000c001'),
  'true',
  'a real change still moves updated_at');

ROLLBACK;
