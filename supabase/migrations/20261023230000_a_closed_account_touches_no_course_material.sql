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
-- to private.
--
-- The policies now say what the sibling bucket's say:
--
--   * the administrator is `(SELECT public.is_platform_staff())`, which is
--     false for a closed account;
--   * the three write policies ask `(SELECT public.can_teach())` first, as
--     `course_assets_teacher_insert/update/delete` do: a closed account is
--     not a teacher, and neither is one demoted to student -- the editor
--     and the API already refuse that person (`TEACHING_ROLES`,
--     `canTeach`), so the bucket now refuses them too;
--   * SELECT keeps the owner and the enrolled student, and asks that the
--     account be open -- `profiles.deactivated_at IS NULL`, read through
--     the caller's own `profiles_select_self` policy. No helper says just
--     that today, and an enrolled student is not inside `can_teach()`; a
--     deleted account is always a deactivated one
--     (`profiles_deleted_is_deactivated_check`), so this one column covers
--     both. A demoted owner still reads the files of the course they made,
--     as the sibling bucket's SELECT still shows them its files.
--
-- For an open account nothing changes: an administrator, the owner of the
-- course and an enrolled student read what they read, the first two write
-- what they wrote. `TO authenticated` is written out (20260915142924 did it
-- for the other eight storage policies and missed these four): `anon` never
-- passed -- `auth.uid()` is null for it -- and now the helpers, on which
-- `anon` holds no EXECUTE (20260915030000), are not evaluated for it at all.
-- `(SELECT ...)` around a helper that takes nothing from the row keeps it an
-- InitPlan, evaluated once per statement.
--
-- Storage policies are not in supabase/schema.sql (it dumps `public` only);
-- supabase/ci/rls_assertions.sql section 19 replays this file onto a
-- stand-in of storage.objects and probes it as a closed and as an open
-- administrator, owner and student.
--
-- Idempotent; DROP/CREATE as every storage migration here.

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
        EXISTS (
          SELECT 1 FROM public.profiles
          WHERE id = (SELECT auth.uid()) AND deactivated_at IS NULL
        )
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
