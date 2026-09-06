-- A director uploads course assets.
--
-- The application admits three roles to the course-authoring surface —
-- teacher, director, platform admin (``TEACHING_ROLES`` in
-- backend/app/models/user.py, ``canTeach`` in frontend/src/lib/roles.ts).
-- The storage bucket that holds course covers and the pictures pasted
-- into a lesson still admitted two. A director could create the course,
-- write the chapter, and then watch the cover upload fail with a 403
-- from Storage — the one write that does not go through the API,
-- because the browser uploads to Supabase Storage directly under the
-- signed-in account's own JWT, so RLS is the whole gate here.
--
-- The list of teaching roles now lives in one SQL function, the way
-- ``is_platform_staff()`` already does for the platform role, so the
-- next bucket policy names the predicate rather than spelling the roles
-- out a fourth time.
--
-- Scope of this change: who may write to `course-assets`. The
-- `course-materials` bucket is untouched — its policies key off
-- ``courses.created_by = auth.uid()`` and never mentioned a role, so a
-- director who owns the course already passes and one who does not is
-- refused exactly as a teacher would be.

CREATE OR REPLACE FUNCTION public.can_teach()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.profiles
        WHERE id = (SELECT auth.uid()) AND role IN ('teacher', 'director', 'admin')
    );
$$;

COMMENT ON FUNCTION public.can_teach() IS
    'The signed-in account may author courses: teacher, director, or platform '
    'admin. Mirrors TEACHING_ROLES in the backend and canTeach on the frontend; '
    'says nothing about which course — ownership is courses.created_by.';

DROP POLICY IF EXISTS "course_assets_teacher_insert" ON storage.objects;
CREATE POLICY "course_assets_teacher_insert"
  ON storage.objects FOR INSERT
  WITH CHECK (bucket_id = 'course-assets' AND public.can_teach());

DROP POLICY IF EXISTS "course_assets_teacher_update" ON storage.objects;
CREATE POLICY "course_assets_teacher_update"
  ON storage.objects FOR UPDATE
  USING (bucket_id = 'course-assets' AND public.can_teach());

DROP POLICY IF EXISTS "course_assets_teacher_delete" ON storage.objects;
CREATE POLICY "course_assets_teacher_delete"
  ON storage.objects FOR DELETE
  USING (bucket_id = 'course-assets' AND public.can_teach());
