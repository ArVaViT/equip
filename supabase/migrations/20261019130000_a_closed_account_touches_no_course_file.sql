-- A closed account touches no course file.
--
-- 20261019120000 closed the definer helpers to a deactivated account, and
-- with them `course_assets_teacher_insert`, which asks `can_teach()`. The
-- UPDATE and DELETE policies on the same bucket stopped asking it on
-- 20261016011000: a file is theirs to change when they uploaded it
-- (`owner_id`) or when it sits in the folder of a course they own
-- (`courses.created_by`, through the caller's own policy on `courses`,
-- which shows every owner their courses -- open or closed). So a teacher who
-- deleted their account, or a director switched off for cause, still
-- overwrote or removed the covers and lesson images of the courses they
-- left behind, through Storage, with the session they still held (security
-- review of 20261019120000).
--
-- Both policies now ask `can_teach()` first, as INSERT does: a closed
-- account is not a teacher, and a teacher demoted to student has nothing
-- to change in the bucket either -- which is what the policies said before
-- 20261016011000 narrowed them. Platform staff are inside `can_teach()`.
--
-- SELECT stays as it is: a file they uploaded is their own row, and listing
-- it changes nothing. Storage reads the row before UPDATE and DELETE, and
-- the write policy answers for the write.
--
-- Idempotent; DROP/CREATE as every storage migration here.

DROP POLICY IF EXISTS "course_assets_teacher_update" ON storage.objects;
CREATE POLICY "course_assets_teacher_update"
  ON storage.objects FOR UPDATE
  TO authenticated
  USING (
    bucket_id = 'course-assets'
    AND public.can_teach()
    AND (
      owner_id = (SELECT auth.uid())::text
      OR (storage.foldername(name))[1] IN (SELECT c.id FROM public.courses c WHERE c.created_by = (SELECT auth.uid()))
      OR public.is_platform_staff()
    )
  )
  WITH CHECK (
    bucket_id = 'course-assets'
    AND public.can_teach()
    AND (
      owner_id = (SELECT auth.uid())::text
      OR (storage.foldername(name))[1] IN (SELECT c.id FROM public.courses c WHERE c.created_by = (SELECT auth.uid()))
      OR public.is_platform_staff()
    )
  );

DROP POLICY IF EXISTS "course_assets_teacher_delete" ON storage.objects;
CREATE POLICY "course_assets_teacher_delete"
  ON storage.objects FOR DELETE
  TO authenticated
  USING (
    bucket_id = 'course-assets'
    AND public.can_teach()
    AND (
      owner_id = (SELECT auth.uid())::text
      OR (storage.foldername(name))[1] IN (SELECT c.id FROM public.courses c WHERE c.created_by = (SELECT auth.uid()))
      OR public.is_platform_staff()
    )
  );
