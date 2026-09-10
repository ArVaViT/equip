-- A teacher can see the file they uploaded.
--
-- `course-assets` and `avatars` have INSERT, UPDATE and DELETE policies
-- and no SELECT policy at all. Migration 20260421010827 removed the two
-- that existed (`avatars_public_read`, `course_assets_public_read`) for a
-- good reason — they granted listing of every file in the bucket to
-- everyone — and nothing looked broken afterwards, because a public
-- bucket serves its objects over public URLs without consulting RLS.
--
-- What broke is everything that has to *find* an object first, and all of
-- it fails quietly:
--
--   * `upload(..., { upsert: true })` looks for the existing object,
--     finds nothing, inserts, and collides — reported as "new row
--     violates row-level security policy", which reads like a problem
--     with the write. This is why replacing a course cover has been
--     impossible since April.
--   * `remove([path])` looks the object up the same way and, finding
--     nothing, deletes nothing and reports no error. Measured on
--     production 2026-09-10: the frontend swept the previous cover of
--     course 7924a1cf after uploading a new one, the call returned
--     cleanly, and `7924a1cf…/cover.png` is still there.
--
-- Measured before writing this file, as `authenticated` carrying an
-- admin/teacher's claims: `SELECT count(*) FROM storage.objects WHERE
-- bucket_id = 'course-assets'` returns 0, with rows plainly present.
--
-- These two policies are deliberately narrower than the ones that were
-- dropped. The April pair were `USING (true)` for anyone at all; these
-- match the bucket's own INSERT policies, so a listing is available to
-- exactly whoever was already allowed to write there:
--
--   course-assets — anyone who can teach. Course covers are public
--     images with public URLs; the only thing this adds is the ability
--     to enumerate them, and every teacher can already upload and delete
--     in this bucket.
--   avatars — the owner's own folder, nobody else's.
--
-- Anonymous callers gain nothing either way: `can_teach()` is false
-- without a profile, and `auth.uid()` is null.

CREATE POLICY course_assets_teacher_read
    ON storage.objects
    FOR SELECT
    USING (bucket_id = 'course-assets' AND can_teach());

CREATE POLICY avatars_owner_read
    ON storage.objects
    FOR SELECT
    USING (
        bucket_id = 'avatars'
        AND (storage.foldername(name))[1] = (auth.uid())::text
    );
