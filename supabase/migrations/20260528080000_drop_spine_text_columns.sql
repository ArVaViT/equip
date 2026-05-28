-- =====================================================================
-- Phase 5g — drop the spine text columns and their dependent triggers.
--
-- Columns dropped:
--   * courses.title
--   * courses.description
--   * courses.search_vector  (FTS tsvector — derived from title+description)
--   * modules.title
--   * modules.description
--
-- After Phase 3 backfill, both ``courses`` and ``modules`` have their
-- title + description mirrored in ``content_versions``. With those columns
-- gone, two trigger-driven side effects need new homes:
--
--   1. ``courses_search_vector_update()`` rebuilt courses.search_vector
--      from title + description on every INSERT/UPDATE. The column is
--      gone; the trigger + function + GIN index are dropped here.
--      Catalog search now runs in Python via ILIKE against
--      content_versions text rows (see app/services/course_service/_queries.py).
--
--   2. ``snapshot_certificate_course_title()`` was a BEFORE-DELETE trigger
--      on courses that stamped OLD.title into certificates.archived_course_title
--      before the FK SET NULL fired. With OLD.title gone the trigger is
--      invalid. We move the snapshot to the FastAPI delete-course handler
--      where we can fetch the title from cv first.
--
-- Irreversibility: data + indexes + triggers are gone. Rollback artefact
-- = pre-merge pg_dump.
-- =====================================================================

-- 1. Drop the search-vector trigger + function + index.
DROP TRIGGER IF EXISTS trg_courses_search_vector_update ON public.courses;
DROP TRIGGER IF EXISTS courses_search_vector_update ON public.courses;
DROP FUNCTION IF EXISTS public.courses_search_vector_update();
DROP INDEX IF EXISTS public.ix_courses_search_vector;

-- 2. Drop the certificate-snapshot trigger + function (snapshot now in app).
DROP TRIGGER IF EXISTS trg_snapshot_certificate_course_title ON public.courses;
DROP FUNCTION IF EXISTS public.snapshot_certificate_course_title();

-- 3. Drop the columns themselves.
ALTER TABLE public.courses DROP COLUMN IF EXISTS title;
ALTER TABLE public.courses DROP COLUMN IF EXISTS description;
ALTER TABLE public.courses DROP COLUMN IF EXISTS search_vector;
ALTER TABLE public.modules DROP COLUMN IF EXISTS title;
ALTER TABLE public.modules DROP COLUMN IF EXISTS description;
