-- A closed account touches no course material.
--
-- 20261019120000 closed the definer helpers to a deactivated account and
-- 20261019130000 put `can_teach()` in front of the `course-assets` write
-- policies. The private bucket next to it, `course-materials` (the PDFs and
-- files of a lesson, served only through a signed URL), was left as
-- 20260227031530 wrote it. Its four policies never asked a helper: the
-- administrator check is spelled out by hand (`profiles.role = 'admin'`,
-- which deletion and deactivation do not touch), the owner branch is
-- `courses.created_by = auth.uid()`, which a closed account keeps, and the
-- student branch is an `enrollments` row, which a closed account keeps too.
-- So, with the session it still holds on purpose (the door back for a
-- restore), a closed account still:
--
--   * read every file of the bucket, as the administrator it used to be;
--   * read, added, overwrote and removed the files of the courses it
--     created, as a teacher or director switched off or deleted;
--   * read the files of every course it was enrolled in, as a student.
--
-- Verified against production on 2026-10-23: `pg_policies` shows the four
-- policies exactly as 20260227031530 wrote them, applied to every role
-- (`{public}` -- no TO clause), and 20260910123047 only flipped the bucket
-- to private. The `avatars` write policies have the same shape: the folder
-- is the account's own, which a closed account keeps.
--
-- One new helper, `is_open_account()`: the account behind the session is
-- not deactivated (a deleted account is always a deactivated one, by
-- `profiles_deleted_is_deactivated_check`). The other helpers answer about
-- a role or a membership; an enrolled student holds neither, and the owner
-- of an avatar folder holds nothing but the folder. Same shape, grants and
-- search_path as the helpers of 20261019120000; no EXECUTE for `anon`
-- (20260915030000).
--
-- The course-materials policies now say what the sibling bucket's say:
--
--   * the administrator is `(SELECT public.is_platform_staff())`, which is
--     false for a closed account;
--   * the three write policies ask `(SELECT public.can_teach())` first, as
--     `course_assets_teacher_insert/update/delete` do: a closed account is
--     not a teacher, and neither is one demoted to student -- the editor
--     and the API already refuse that person (`TEACHING_ROLES`,
--     `canTeach`), so the bucket now refuses them too;
--   * SELECT keeps the owner and the enrolled student, behind
--     `(SELECT public.is_open_account())`. A demoted owner still reads the
--     files of the course they made, as the sibling bucket's SELECT still
--     shows them its files.
--
-- The avatars write policies ask `is_open_account()` too: a closed account
-- does not change the picture others see next to its name.
--
-- The two public buckets lose their UPDATE policies altogether
-- (`avatars_owner_update`, `course_assets_teacher_update`; review of this
-- migration, 2026-10-23). Storage's move and copy (`POST /object/move`,
-- `destinationBucket`) are one UPDATE of `storage.objects` under the
-- caller's role, and permissive policies are OR-ed per command: a row
-- leaving `course-materials` passed the owner's `course_materials_teacher_
-- update` USING, and the new row -- now in `avatars`, in the caller's own
-- folder -- passed `avatars_owner_update`, whose WITH CHECK was its USING.
-- From `avatars` the same step reached `course-assets`. Neither the target
-- bucket's MIME list nor its size limit is checked on a move. So the owner
-- of a course could turn a 50 MB private PDF or audio file into a public
-- object served from equipbible.com (`/img/course-assets/...`), with the
-- course-materials policies never asked about the destination. Nothing
-- uses UPDATE on these buckets: the app uploads every cover and avatar
-- under a fresh key and removes the old one (20261016011000,
-- frontend/src/services/storage.ts -- `upload` with `upsert: false`,
-- `remove`, `createSignedUrl`; no `move`, `copy` or `update`, in the
-- frontend, the backend or the e2e specs), so upsert, rename and move in
-- the public buckets are refused from now on, on purpose. A file in
-- `course-materials` can still be renamed by its course's owner, inside
-- the bucket: its UPDATE policy checks the new row against the same
-- predicate, and no other UPDATE policy remains to admit a row elsewhere.
--
-- For an open account nothing changes: an administrator, the owner of the
-- course and an enrolled student read what they read, the first two write
-- what they wrote, and everyone keeps their own avatar folder.
-- `TO authenticated` is written out on the course-materials policies
-- (20260915142924 did it for the other eight storage policies and missed
-- these four): `anon` never passed -- `auth.uid()` is null for it -- and
-- now the helpers, on which `anon` holds no EXECUTE, are not evaluated for
-- it at all. `(SELECT ...)` around a helper that takes nothing from the row
-- keeps it an InitPlan, evaluated once per statement; the course-assets
-- SELECT and DELETE policies of 20261016011000 / 20261019130000 called
-- theirs bare and are rewritten with the wrapper only -- same text
-- otherwise.
--
-- Storage policies are not in supabase/schema.sql (it dumps `public` only;
-- the helper is added there by hand). supabase/ci/rls_assertions.sql
-- section 19 replays this file onto a stand-in of storage.objects and
-- probes it as a closed and as an open administrator, owner and student.
--
-- A signed URL minted before the account closed keeps working until it
-- expires (SIGNED_URL_TTL_SECONDS, one hour); the signature is checked by
-- Storage, not by these policies. Accepted.
--
-- Idempotent; DROP/CREATE as every storage migration here.

-- ---------------------------------------------------------------------------
-- The helper.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.is_open_account() RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'public', 'pg_temp'
    AS $$
    SELECT EXISTS (
        SELECT 1 FROM public.profiles
        WHERE id = (SELECT auth.uid()) AND deactivated_at IS NULL
    );
$$;

COMMENT ON FUNCTION public.is_open_account() IS
  'The signed-in account is open (profiles.deactivated_at IS NULL); says nothing about a role. For policies that admit a person by a row they hold -- an enrollment, their own folder -- rather than by a role. See 20261023230000.';

REVOKE EXECUTE ON FUNCTION public.is_open_account() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.is_open_account() TO authenticated, service_role;

-- ---------------------------------------------------------------------------
-- course-materials: the private bucket.
-- ---------------------------------------------------------------------------

DROP POLICY IF EXISTS "course_materials_enrolled_read" ON storage.objects;
CREATE POLICY "course_materials_enrolled_read"
  ON storage.objects FOR SELECT
  TO authenticated
  USING (
    bucket_id = 'course-materials'
    AND (
      -- Platform staff read everything.
      (SELECT public.is_platform_staff())
      OR (
        -- An open account --
        (SELECT public.is_open_account())
        AND (
          -- -- that owns the course,
          (storage.foldername(name))[1] IN (SELECT c.id FROM public.courses c WHERE c.created_by = (SELECT auth.uid()))
          -- -- or is enrolled in it.
          OR (storage.foldername(name))[1] IN (SELECT e.course_id FROM public.enrollments e WHERE e.user_id = (SELECT auth.uid()))
        )
      )
    )
  );

DROP POLICY IF EXISTS "course_materials_teacher_insert" ON storage.objects;
CREATE POLICY "course_materials_teacher_insert"
  ON storage.objects FOR INSERT
  TO authenticated
  WITH CHECK (
    bucket_id = 'course-materials'
    AND (SELECT public.can_teach())
    AND (
      (storage.foldername(name))[1] IN (SELECT c.id FROM public.courses c WHERE c.created_by = (SELECT auth.uid()))
      OR (SELECT public.is_platform_staff())
    )
  );

DROP POLICY IF EXISTS "course_materials_teacher_update" ON storage.objects;
CREATE POLICY "course_materials_teacher_update"
  ON storage.objects FOR UPDATE
  TO authenticated
  USING (
    bucket_id = 'course-materials'
    AND (SELECT public.can_teach())
    AND (
      (storage.foldername(name))[1] IN (SELECT c.id FROM public.courses c WHERE c.created_by = (SELECT auth.uid()))
      OR (SELECT public.is_platform_staff())
    )
  )
  WITH CHECK (
    bucket_id = 'course-materials'
    AND (SELECT public.can_teach())
    AND (
      (storage.foldername(name))[1] IN (SELECT c.id FROM public.courses c WHERE c.created_by = (SELECT auth.uid()))
      OR (SELECT public.is_platform_staff())
    )
  );

DROP POLICY IF EXISTS "course_materials_teacher_delete" ON storage.objects;
CREATE POLICY "course_materials_teacher_delete"
  ON storage.objects FOR DELETE
  TO authenticated
  USING (
    bucket_id = 'course-materials'
    AND (SELECT public.can_teach())
    AND (
      (storage.foldername(name))[1] IN (SELECT c.id FROM public.courses c WHERE c.created_by = (SELECT auth.uid()))
      OR (SELECT public.is_platform_staff())
    )
  );

-- ---------------------------------------------------------------------------
-- avatars: the owner's folder, while the account is open. `avatars_owner_read`
-- (SELECT of the own folder, TO authenticated -- what `remove` needs to find
-- the row; the public URL is served by the public bucket without RLS) is not
-- touched. UPDATE is dropped and not recreated: see the header.
-- ---------------------------------------------------------------------------

DROP POLICY IF EXISTS "avatars_owner_insert" ON storage.objects;
CREATE POLICY "avatars_owner_insert"
  ON storage.objects FOR INSERT
  TO authenticated
  WITH CHECK (
    bucket_id = 'avatars'
    AND (SELECT public.is_open_account())
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

DROP POLICY IF EXISTS "avatars_owner_update" ON storage.objects;

DROP POLICY IF EXISTS "avatars_owner_delete" ON storage.objects;
CREATE POLICY "avatars_owner_delete"
  ON storage.objects FOR DELETE
  TO authenticated
  USING (
    bucket_id = 'avatars'
    AND (SELECT public.is_open_account())
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

-- ---------------------------------------------------------------------------
-- course-assets: SELECT and DELETE as 20261019130000 / 20261016011000 wrote
-- them, the helpers wrapped so the planner evaluates each once per
-- statement -- what they answer does not change. UPDATE is dropped and not
-- recreated: see the header.
-- ---------------------------------------------------------------------------

DROP POLICY IF EXISTS "course_assets_teacher_read" ON storage.objects;
CREATE POLICY "course_assets_teacher_read"
  ON storage.objects FOR SELECT
  TO authenticated
  USING (
    bucket_id = 'course-assets'
    AND (
      owner_id = (SELECT auth.uid())::text
      OR (storage.foldername(name))[1] IN (SELECT c.id FROM public.courses c WHERE c.created_by = (SELECT auth.uid()))
      OR (SELECT public.is_platform_staff())
    )
  );

DROP POLICY IF EXISTS "course_assets_teacher_update" ON storage.objects;

DROP POLICY IF EXISTS "course_assets_teacher_delete" ON storage.objects;
CREATE POLICY "course_assets_teacher_delete"
  ON storage.objects FOR DELETE
  TO authenticated
  USING (
    bucket_id = 'course-assets'
    AND (SELECT public.can_teach())
    AND (
      owner_id = (SELECT auth.uid())::text
      OR (storage.foldername(name))[1] IN (SELECT c.id FROM public.courses c WHERE c.created_by = (SELECT auth.uid()))
      OR (SELECT public.is_platform_staff())
    )
  );
