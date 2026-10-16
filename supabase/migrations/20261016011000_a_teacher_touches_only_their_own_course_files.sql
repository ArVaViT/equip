-- A teacher touches only their own course files.
--
-- `course-assets` holds every course's cover and every image pasted into a
-- lesson. Its UPDATE, DELETE and SELECT policies asked one question —
-- `can_teach()` — so any teacher or director of any school could list the
-- bucket, delete another school's cover, or overwrite it in place, through
-- Storage directly with their own session (security review, 2026-10-15).
--
-- A file is now theirs to change when either is true:
--
--   * they uploaded it — Storage stamps `owner_id` with the uploader's
--     `auth.uid()`. This is the only answer for a lesson image
--     (`content-images/…`), which is not filed under any course;
--   * it sits in the folder of a course they own — a cover is
--     `<course_id>/cover-…`. Needed beside the first: every object in the
--     bucket today was put there by a script on the secret key and has no
--     `owner_id` (production, 2026-10-15), so without it the owner of a
--     course could no longer remove the cover they replace. The subquery
--     runs under the caller's own policy on `courses`, which shows every
--     owner their courses.
--
-- Platform staff keep every file, as they keep every course.
--
-- INSERT stays as it was: a teacher may add a new object, and a new key
-- cannot replace anyone's — the app never uploads with `upsert`, and an
-- existing key is a conflict, which is decided by UPDATE below.
--
-- New SVG uploads are refused. An SVG can carry script; the bucket is
-- public and the app serves it from its own origin (`/img/course-assets/*`),
-- so a teacher could publish a document on equipbible.com. The CSP blocks
-- the script today, but a cover or a photo in a lesson has no reason to be
-- a vector document. The six diagrams already in `diagrams/` are ours,
-- uploaded 2026-08-12 and shown in lessons; they stay — the bucket's list
-- governs uploads, not what is stored.

DROP POLICY IF EXISTS "course_assets_teacher_update" ON storage.objects;
CREATE POLICY "course_assets_teacher_update"
  ON storage.objects FOR UPDATE
  TO authenticated
  USING (
    bucket_id = 'course-assets'
    AND (
      owner_id = (SELECT auth.uid())::text
      OR (storage.foldername(name))[1] IN (SELECT c.id FROM public.courses c WHERE c.created_by = (SELECT auth.uid()))
      OR public.is_platform_staff()
    )
  )
  WITH CHECK (
    bucket_id = 'course-assets'
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
    AND (
      owner_id = (SELECT auth.uid())::text
      OR (storage.foldername(name))[1] IN (SELECT c.id FROM public.courses c WHERE c.created_by = (SELECT auth.uid()))
      OR public.is_platform_staff()
    )
  );

-- Storage reads the row before it removes it, so DELETE needs a SELECT
-- policy that sees the same rows — and no more: the old one listed every
-- file of every school to any teacher.
DROP POLICY IF EXISTS "course_assets_teacher_read" ON storage.objects;
CREATE POLICY "course_assets_teacher_read"
  ON storage.objects FOR SELECT
  TO authenticated
  USING (
    bucket_id = 'course-assets'
    AND (
      owner_id = (SELECT auth.uid())::text
      OR (storage.foldername(name))[1] IN (SELECT c.id FROM public.courses c WHERE c.created_by = (SELECT auth.uid()))
      OR public.is_platform_staff()
    )
  );

UPDATE storage.buckets
   SET allowed_mime_types = ARRAY['image/jpeg', 'image/png', 'image/webp', 'image/gif']
 WHERE id = 'course-assets';
