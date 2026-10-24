-- A bucket admits only its own types, however the file arrives.
--
-- Storage checks a bucket's `allowed_mime_types` and `file_size_limit` on an
-- ordinary upload and nowhere else (storage-api v1.68.1, the version the
-- linked project reports):
--
--   * a copy (`POST /object/copy`, `destinationBucket`) is authorized by two
--     queries under the caller's role -- a SELECT of the source row, then a
--     rolled-back INSERT of the destination row -- and never looks at the
--     destination bucket's limits. The row carries the source's `metadata`,
--     or, with `copyMetadata: false`, whatever `metadata.mimetype` the
--     caller names;
--   * an upload whose key ends in `.emptyFolderPlaceholder` skips the MIME
--     check (`limits.ts`, `isEmptyFolder`). Its INSERT is tested with the
--     declared Content-Type as `metadata.mimetype`.
--
-- So a student enrolled in a course could copy its PDF out of the private
-- `course-materials` into their own `avatars` folder, and anyone who may
-- insert into a public bucket could store `image/svg+xml`,
-- `application/xhtml+xml` or `text/javascript` there -- served from
-- equipbible.com through `/img/<bucket>/...`, a stored document on our own
-- origin. 20261023230000 closed the move (an UPDATE); a copy is an INSERT,
-- and the INSERT policies asked only who and where.
--
-- The one question every path still asks is the INSERT policy, on a row
-- whose `metadata->>'mimetype'` is the type the object will be served with.
-- So each INSERT policy now asks it too, against exactly the list its bucket
-- holds in production (verified 2026-10-24: `storage.buckets` shows the
-- lists of 20260227031449, less SVG on `course-assets` since
-- 20261016011000). An ordinary upload changes nothing: Storage has already
-- refused any type outside the list, by the same exact comparison, before
-- the policy runs (`validateMimeType`; no bucket here uses a `type/*`
-- wildcard). `frontend/src/lib/uploadLimits.ts` keeps the same lists for
-- the client. If a bucket's list changes, its policy changes in the same
-- migration.
--
-- `course-assets` INSERT also asks where, as its SELECT and DELETE already
-- do. The app writes two shapes of key there and no other
-- (frontend/src/services/storage.ts): `<course_id>/cover-<hex>.<ext>`,
-- which only the course's owner or an administrator may then save on the
-- course (`assert_course_owner`, PATCH /courses/{id}), and
-- `content-images/<ms>-<hex>.<ext>`, an image pasted into any rich-text
-- field, filed under no course. So a teacher adds into the folder of a
-- course they own or into `content-images/`; platform staff anywhere. Until
-- now any teacher could file an object under another school's course.
--
-- Not covered, on purpose: the size limit. A copy keeps the source's
-- `metadata.size`, an upload declares `contentLength`, and neither is
-- always present; the type is what made the copy dangerous. A 50 MB PDF
-- copied into `course-assets` now has to call itself an image and is
-- served as one.
--
-- Storage policies are not in supabase/schema.sql (it dumps `public` only).
-- supabase/ci/rls_assertions.sql replays this file onto the stand-in of
-- `storage.objects` in section 19, whose probes now carry a type, and
-- section 20 probes copies and uploads of every kind.
--
-- Idempotent; DROP/CREATE as every storage migration here. Each policy is
-- the one 20261023230000 / 20260915142924 left, plus the new conditions
-- (`can_teach()` on course-assets wrapped in `(SELECT ...)`, as on its
-- siblings -- same answer, evaluated once per statement).

DROP POLICY IF EXISTS "avatars_owner_insert" ON storage.objects;
CREATE POLICY "avatars_owner_insert"
  ON storage.objects FOR INSERT
  TO authenticated
  WITH CHECK (
    bucket_id = 'avatars'
    AND (SELECT public.is_open_account())
    AND (storage.foldername(name))[1] = auth.uid()::text
    AND (metadata->>'mimetype') = ANY (ARRAY['image/jpeg', 'image/png', 'image/webp', 'image/gif'])
  );

DROP POLICY IF EXISTS "course_assets_teacher_insert" ON storage.objects;
CREATE POLICY "course_assets_teacher_insert"
  ON storage.objects FOR INSERT
  TO authenticated
  WITH CHECK (
    bucket_id = 'course-assets'
    AND (SELECT public.can_teach())
    AND (metadata->>'mimetype') = ANY (ARRAY['image/jpeg', 'image/png', 'image/webp', 'image/gif'])
    AND (
      (storage.foldername(name))[1] = 'content-images'
      OR (storage.foldername(name))[1] IN (SELECT c.id FROM public.courses c WHERE c.created_by = (SELECT auth.uid()))
      OR (SELECT public.is_platform_staff())
    )
  );

DROP POLICY IF EXISTS "course_materials_teacher_insert" ON storage.objects;
CREATE POLICY "course_materials_teacher_insert"
  ON storage.objects FOR INSERT
  TO authenticated
  WITH CHECK (
    bucket_id = 'course-materials'
    AND (SELECT public.can_teach())
    AND (metadata->>'mimetype') = ANY (ARRAY[
      'application/pdf',
      'audio/mpeg',
      'audio/mp4',
      'audio/ogg',
      'audio/wav',
      'application/msword',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/vnd.ms-powerpoint',
      'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      'text/plain'
    ])
    AND (
      (storage.foldername(name))[1] IN (SELECT c.id FROM public.courses c WHERE c.created_by = (SELECT auth.uid()))
      OR (SELECT public.is_platform_staff())
    )
  );
