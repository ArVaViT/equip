-- A submission can carry a file.
--
-- In the whole life of the platform no written work has been handed in
-- (assignment_submissions: 0 rows on 2026-11-06). The one assignment that
-- ran -- «prepare a topical sermon», ten students enrolled -- got nothing,
-- and the form explains why: a text box, or an https:// link to put the
-- file somewhere else first. A sermon outline is a photo of a notebook
-- page, a PDF, or a voice memo from the phone, and most of these students
-- are on a phone and on 3G.
--
-- So a submission may now carry one file, uploaded by the student into a
-- private bucket of its own, `submissions`:
--
--   * 50 MB, like `course-materials`; images and audio of any subtype (a
--     phone's recorder says `audio/x-m4a`, `audio/aac`, `audio/amr`,
--     `audio/3gpp` depending on the make, and every one is the sermon),
--     the three video containers phones produce, PDF, Word / OpenDocument
--     text, and plain text. The list is mirrored in
--     frontend/src/lib/uploadLimits.ts (`SUBMISSIONS`) and asked again by
--     the INSERT policy, as 20261024142623 does for every bucket, so a copy
--     into the bucket is held to the same list;
--   * one key shape and no other: `<course_id>/<assignment_id>/<student_id>/
--     <ms>-<safe_name>`. The student's own folder is the third segment and
--     the course is the first; the API refuses a `file.path` outside the
--     caller's own folder for the assignment being handed in.
--
-- Who may do what, in the bucket (the table's `submissions_select_own_or_
-- teacher` and the API's `verify_chapter_owner` say the same about the row):
--
--   * a student, with an open account, adds into their own folder of a
--     course they are enrolled in, and reads their own folder. Enrollment is
--     asked on the way in: a file is handed in to a course one attends. It
--     is not asked on the way back: the file is the student's own record of
--     their own work, as the row is, whatever happens to the enrollment;
--   * the same student removes a file of theirs that no submission names
--     yet -- the «remove» cross between choosing the file and handing it
--     in. Once a row points at it, it is part of the record; the student's
--     own SELECT policy on `assignment_submissions` is what the subquery
--     reads through, so a student cannot see past it;
--   * the owner of the course reads every submission of their course, and
--     platform staff read everything. The API lets exactly these two mark
--     the work (`verify_chapter_owner`: owner or administrator). Nobody
--     but the student writes;
--   * no UPDATE policy at all: a move is an UPDATE (20261023230000), and
--     nothing renames or moves a submission;
--   * a closed account touches nothing. The two helpers that answer by role
--     (`is_platform_staff`, `can_teach`) are closed to a deactivated account
--     since 20261019120000; the student and owner branches, which admit a
--     person by a row they hold, sit behind `is_open_account()` as the
--     course-materials policies do since 20261023230000.
--
-- No student reads another student's work: the student branch compares the
-- third segment with `auth.uid()`, and nothing else admits a student.
--
-- The row: three nullable columns, all set or none (`file_bucket`,
-- `file_path`, `file_name`). The bucket is stored, as a chapter file block
-- stores its own, so the client signs a URL on every click and nothing
-- secret-dependent is ever written down. `file_url` stays for the link a
-- student pastes when the file is too large for the bucket (YouTube,
-- Google Drive).
--
-- Only additions: the backend that runs today never reads the new columns
-- and writes NULL into them. Idempotent; ON CONFLICT, IF NOT EXISTS and
-- DROP/CREATE as every migration here. Storage policies are not in
-- supabase/schema.sql (it dumps `public` only; the columns are added there
-- by hand). supabase/ci/rls_assertions.sql section 22 replays this file
-- onto the stand-in of storage.objects and probes it as a student, another
-- student, the course owner, a teacher who owns nothing here, platform
-- staff, a closed student and anon.

-- ---------------------------------------------------------------------------
-- The bucket.
-- ---------------------------------------------------------------------------

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES
  ('submissions', 'submissions', false, 52428800, ARRAY[
    'image/*',
    'audio/*',
    'video/mp4',
    'video/quicktime',
    'video/webm',
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.oasis.opendocument.text',
    'text/plain'
  ])
ON CONFLICT (id) DO NOTHING;

-- ---------------------------------------------------------------------------
-- The row.
-- ---------------------------------------------------------------------------

ALTER TABLE public.assignment_submissions
  ADD COLUMN IF NOT EXISTS file_bucket text,
  ADD COLUMN IF NOT EXISTS file_path text,
  ADD COLUMN IF NOT EXISTS file_name text;

ALTER TABLE public.assignment_submissions
  DROP CONSTRAINT IF EXISTS assignment_submissions_file_all_or_none;
ALTER TABLE public.assignment_submissions
  ADD CONSTRAINT assignment_submissions_file_all_or_none CHECK (
    (file_bucket IS NULL AND file_path IS NULL AND file_name IS NULL)
    OR (file_bucket IS NOT NULL AND file_path IS NOT NULL AND file_name IS NOT NULL)
  );

COMMENT ON COLUMN public.assignment_submissions.file_path IS
  'Object key in file_bucket: <course_id>/<assignment_id>/<student_id>/<ms>-<safe_name>. Signed on every click by the client; never a URL. See 20261107030001.';

-- ---------------------------------------------------------------------------
-- The policies. `(SELECT ...)` around a helper that takes nothing from the
-- row keeps it an InitPlan, evaluated once per statement (20261023230000).
-- ---------------------------------------------------------------------------

DROP POLICY IF EXISTS "submissions_student_insert" ON storage.objects;
CREATE POLICY "submissions_student_insert"
  ON storage.objects FOR INSERT
  TO authenticated
  WITH CHECK (
    bucket_id = 'submissions'
    AND (SELECT public.is_open_account())
    -- Exactly <course>/<assignment>/<student>/<file>: the folder is the
    -- caller's own and the course is one they attend.
    AND array_length(storage.foldername(name), 1) = 3
    AND (storage.foldername(name))[3] = (SELECT auth.uid())::text
    AND (storage.foldername(name))[1] IN (SELECT e.course_id FROM public.enrollments e WHERE e.user_id = (SELECT auth.uid()))
    AND (
      (metadata->>'mimetype') LIKE 'image/%'
      OR (metadata->>'mimetype') LIKE 'audio/%'
      OR (metadata->>'mimetype') = ANY (ARRAY[
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
    -- A script-bearing image is not a photo of a notebook.
    AND (metadata->>'mimetype') <> 'image/svg+xml'
  );

DROP POLICY IF EXISTS "submissions_student_read" ON storage.objects;
CREATE POLICY "submissions_student_read"
  ON storage.objects FOR SELECT
  TO authenticated
  USING (
    bucket_id = 'submissions'
    AND (SELECT public.is_open_account())
    AND (storage.foldername(name))[3] = (SELECT auth.uid())::text
  );

DROP POLICY IF EXISTS "submissions_student_delete" ON storage.objects;
CREATE POLICY "submissions_student_delete"
  ON storage.objects FOR DELETE
  TO authenticated
  USING (
    bucket_id = 'submissions'
    AND (SELECT public.is_open_account())
    AND (storage.foldername(name))[3] = (SELECT auth.uid())::text
    -- Not yet handed in. The subquery runs under the caller's own policy on
    -- assignment_submissions, which shows a student their own rows.
    AND NOT EXISTS (
      SELECT 1 FROM public.assignment_submissions s
      WHERE s.file_bucket = 'submissions' AND s.file_path = storage.objects.name
    )
  );

DROP POLICY IF EXISTS "submissions_teacher_read" ON storage.objects;
CREATE POLICY "submissions_teacher_read"
  ON storage.objects FOR SELECT
  TO authenticated
  USING (
    bucket_id = 'submissions'
    AND (
      (SELECT public.is_platform_staff())
      OR (
        (SELECT public.is_open_account())
        AND (storage.foldername(name))[1] IN (SELECT c.id FROM public.courses c WHERE c.created_by = (SELECT auth.uid()))
      )
    )
  );
