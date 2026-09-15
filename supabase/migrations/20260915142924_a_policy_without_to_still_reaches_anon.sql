-- A policy without TO still reaches anon.
--
-- Eight policies on storage.objects were written without a TO clause:
--
--   avatars_owner_insert / _update / _delete / _read
--   course_assets_teacher_insert / _update / _delete / _read
--
-- Omitting TO does not narrow a policy — Postgres applies it to every role
-- of PERMISSIVE policies for the command, `anon` included. Each of these
-- eight happens to evaluate to false for `anon` today, because every USING /
-- WITH CHECK expression bottoms out in `auth.uid()` (null for an anonymous
-- request) or `can_teach()` (false without a matching profiles row). So the
-- refusal was already correct — only the role list was implicit, left for
-- the next reader to work out from the expression rather than stated. This
-- makes it explicit: TO authenticated, expressions unchanged.
--
-- Two policies do intentionally serve anon and are NOT touched here:
--   avatars_public_read and course_assets_public_read granted anonymous
--   SELECT on these same two public buckets, but migration
--   20260421010827_remove_public_bucket_listing_policies.sql already
--   dropped both — a public bucket serves objects over public URLs without
--   consulting RLS at all (see 20260910120214's comment), so there is no
--   surviving policy here that anon actually needs.

DROP POLICY IF EXISTS "avatars_owner_insert" ON storage.objects;
CREATE POLICY "avatars_owner_insert"
  ON storage.objects FOR INSERT
  TO authenticated
  WITH CHECK (
    bucket_id = 'avatars'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

DROP POLICY IF EXISTS "avatars_owner_update" ON storage.objects;
CREATE POLICY "avatars_owner_update"
  ON storage.objects FOR UPDATE
  TO authenticated
  USING (
    bucket_id = 'avatars'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

DROP POLICY IF EXISTS "avatars_owner_delete" ON storage.objects;
CREATE POLICY "avatars_owner_delete"
  ON storage.objects FOR DELETE
  TO authenticated
  USING (
    bucket_id = 'avatars'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

DROP POLICY IF EXISTS "avatars_owner_read" ON storage.objects;
CREATE POLICY avatars_owner_read
    ON storage.objects
    FOR SELECT
    TO authenticated
    USING (
        bucket_id = 'avatars'
        AND (storage.foldername(name))[1] = (auth.uid())::text
    );

DROP POLICY IF EXISTS "course_assets_teacher_insert" ON storage.objects;
CREATE POLICY "course_assets_teacher_insert"
  ON storage.objects FOR INSERT
  TO authenticated
  WITH CHECK (bucket_id = 'course-assets' AND public.can_teach());

DROP POLICY IF EXISTS "course_assets_teacher_update" ON storage.objects;
CREATE POLICY "course_assets_teacher_update"
  ON storage.objects FOR UPDATE
  TO authenticated
  USING (bucket_id = 'course-assets' AND public.can_teach());

DROP POLICY IF EXISTS "course_assets_teacher_delete" ON storage.objects;
CREATE POLICY "course_assets_teacher_delete"
  ON storage.objects FOR DELETE
  TO authenticated
  USING (bucket_id = 'course-assets' AND public.can_teach());

DROP POLICY IF EXISTS "course_assets_teacher_read" ON storage.objects;
CREATE POLICY course_assets_teacher_read
    ON storage.objects
    FOR SELECT
    TO authenticated
    USING (bucket_id = 'course-assets' AND can_teach());
