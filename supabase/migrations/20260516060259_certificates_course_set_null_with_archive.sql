-- ============================================================================
-- Certificate FK to courses: CASCADE → SET NULL, with archived_course_title.
-- ----------------------------------------------------------------------------
-- The certificate-verify URL (``/verify/{number}``) is a public credential
-- recipients share with employers / committees. Previously, ``ON DELETE
-- CASCADE`` on ``certificates.course_id`` meant that when an admin
-- permanently deletes a course, every issued certificate for that course
-- silently disappears from the DB — the verify URL would then resolve to
-- ``valid=false`` and the recipient's credential would look fraudulent.
--
-- We switch to ``ON DELETE SET NULL`` so the certificate row survives the
-- course deletion, *and* we materialise the historical course title into a
-- new ``archived_course_title`` column so the verify endpoint can still
-- render a meaningful "Course X — verified" page even after the source
-- course is gone. The verify endpoint already does an OUTER JOIN against
-- courses (``cert.outerjoin(Course, …)``) and renders ``course_title`` as a
-- nullable string, so the surviving cert lands in a clean "course archived"
-- state instead of breaking the response.
--
-- The ``(user_id, course_id)`` unique constraint is preserved: with course_id
-- nullable, Postgres treats NULL as distinct under that constraint, which
-- is the behaviour we want — a future, separately-keyed course re-using the
-- same slug doesn't collide with an archived certificate.
-- ============================================================================

-- 1. Allow course_id to be NULL so SET NULL can fire.
ALTER TABLE public.certificates
  ALTER COLUMN course_id DROP NOT NULL;

-- 2. Replace the cascade FK with SET NULL.
ALTER TABLE public.certificates
  DROP CONSTRAINT IF EXISTS certificates_course_id_fkey;

ALTER TABLE public.certificates
  ADD CONSTRAINT certificates_course_id_fkey
    FOREIGN KEY (course_id) REFERENCES public.courses(id) ON DELETE SET NULL;

-- 3. Capture the historical course title so the verify URL keeps working
--    after the underlying course is deleted. Nullable on purpose: existing
--    rows stay NULL until the course is deleted, at which point a trigger
--    snapshots ``courses.title`` into this column (see step 4).
ALTER TABLE public.certificates
  ADD COLUMN IF NOT EXISTS archived_course_title TEXT;

-- 4. BEFORE-DELETE trigger on courses: stamp the title into every certificate
--    that points at the row being deleted, before SET NULL nulls course_id.
--    Runs as ``SECURITY DEFINER`` with an empty ``search_path`` so it can't
--    be hijacked by a malicious schema in the caller's search path (matches
--    the lock_function_search_paths migration's pattern).
CREATE OR REPLACE FUNCTION public.snapshot_certificate_course_title()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
  UPDATE public.certificates
    SET archived_course_title = OLD.title
  WHERE course_id = OLD.id
    AND archived_course_title IS NULL;
  RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_snapshot_certificate_course_title ON public.courses;

CREATE TRIGGER trg_snapshot_certificate_course_title
  BEFORE DELETE ON public.courses
  FOR EACH ROW
  EXECUTE FUNCTION public.snapshot_certificate_course_title();

-- 5. Lock down the helper function: only the table owner (postgres) executes
--    it via the trigger machinery. No direct call surface needed.
REVOKE ALL ON FUNCTION public.snapshot_certificate_course_title() FROM PUBLIC;
REVOKE ALL ON FUNCTION public.snapshot_certificate_course_title() FROM anon;
REVOKE ALL ON FUNCTION public.snapshot_certificate_course_title() FROM authenticated;
