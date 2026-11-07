-- A submitted image is never SVG, however the type is spelled.
--
-- 20261107030001 refused `image/svg+xml` by exact comparison. A client can
-- send `image/svg+xml; charset=utf-8` or `IMAGE/SVG+XML`: the bucket's
-- `image/*` compares only the type and subtype, and the exact `<>` let it
-- through. A signed URL serves the file inline, so the script would run on
-- the storage domain (no app session there, but a page anyone can be sent).
--
-- The policy now reads the type the way the bucket does: lower case, the
-- part before the first `;`, trimmed. Same list otherwise. Idempotent.

DROP POLICY IF EXISTS "submissions_student_insert" ON storage.objects;
CREATE POLICY "submissions_student_insert"
  ON storage.objects FOR INSERT
  TO authenticated
  WITH CHECK (
    bucket_id = 'submissions'
    AND (SELECT public.is_open_account())
    AND array_length(storage.foldername(name), 1) = 3
    AND (storage.foldername(name))[3] = (SELECT auth.uid())::text
    AND (storage.foldername(name))[1] IN (SELECT e.course_id FROM public.enrollments e WHERE e.user_id = (SELECT auth.uid()))
    AND (
      btrim(split_part(lower(metadata->>'mimetype'), ';', 1)) LIKE 'image/%'
      OR btrim(split_part(lower(metadata->>'mimetype'), ';', 1)) LIKE 'audio/%'
      OR btrim(split_part(lower(metadata->>'mimetype'), ';', 1)) = ANY (ARRAY[
        'video/mp4',
        'video/quicktime',
        'video/webm',
        'application/pdf',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.oasis.opendocument.text',
        'text/plain'
      ])
    )
    AND btrim(split_part(lower(metadata->>'mimetype'), ';', 1)) <> 'image/svg+xml'
  );
