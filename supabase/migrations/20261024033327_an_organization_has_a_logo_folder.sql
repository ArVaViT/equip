-- An organization has a logo folder.
--
-- `organizations.logo_url` has existed since 20261003165050 ("arrives with
-- the page, phase 4") and the page and the showcase already render it; no
-- bucket, no policy and no route ever let anyone fill it. This is the
-- infrastructure, and it stays empty: nobody uploads a logo today (decided
-- 2026-10-23 -- "like the profile photo", which also starts blank).
--
-- The bucket is the avatars bucket with the organization in the person's
-- place: public, 2 MB, the same four image types (no SVG -- a public bucket
-- served from equipbible.com through `/img/` is not where a script-bearing
-- document belongs), one folder per organization named by its id, every
-- file written under a fresh key and the previous one removed by the app
-- (frontend/src/services/storage.ts), so the public URL is immutable and
-- cacheable like a cover or an avatar.
--
-- Who writes the folder: the organization's director or platform staff --
-- the same two the API asks for the page itself (`directs()` in
-- `PATCH /organizations/{id}/profile`). In SQL that is
-- `public.is_director_of(<folder>)` and `public.is_platform_staff()`, both
-- of which already answer false for a deactivated account
-- (20261019120000), so a closed account touches no logo without a separate
-- `is_open_account()` clause.
--
-- The folder is text and the helper takes a uuid. The cast is guarded by a
-- CASE, on purpose: a policy on `storage.objects` is evaluated against the
-- rows of every bucket, and `course-materials` keys begin with a course id,
-- which is text, not uuid (`course-m-materials/...` in the CI stand-in). A
-- bare `::uuid` is an error on such a key: in a WITH CHECK a 500 where a
-- refusal is expected (section 21 plants `not-a-uuid/logo.png` to prove the
-- difference), and in a USING an error on somebody else's SELECT whenever
-- the planner evaluates the cast before the bucket test, which AND lets it
-- do. CASE evaluates its THEN only when the WHEN holds (the SQL standard
-- and Postgres both promise it). No
-- subquery on `public.organizations`: it has RLS on and no SELECT policy
-- for `authenticated`, so a policy that read it would admit nobody.
--
-- Rules of 20261023230000, kept: `TO authenticated` on every policy; helpers
-- that take nothing from the row in `(SELECT ...)`; no UPDATE policy on a
-- public bucket (a move is an UPDATE, and an UPDATE policy here would admit
-- the new row of a private file leaving `course-materials`); neither
-- `profiles` nor `organization_members` named by hand -- the helpers are
-- where a closed account is closed. SELECT is what `remove` needs to find
-- the row; the public URL is served by the public bucket without RLS.
--
-- Storage policies are not in supabase/schema.sql (it dumps `public` only;
-- nothing in `public` changes here). supabase/ci/rls_assertions.sql
-- section 21 replays this file onto the stand-in of storage.objects and
-- probes it as a director of one school, a teacher who directs nothing,
-- platform staff, a student, a deactivated director, and anon. Also add it
-- to the list of storage migrations .github/workflows/frontend-e2e.yml
-- replays, and the bucket to the `/img/` proxy (frontend/vercel.json,
-- frontend/vite.config.ts -- the proxy names its buckets one by one).
--
-- Idempotent; ON CONFLICT and DROP/CREATE as every storage migration here.

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES
  ('organization-logos', 'organization-logos', true, 2097152, ARRAY['image/jpeg','image/png','image/webp','image/gif'])
ON CONFLICT (id) DO NOTHING;

DROP POLICY IF EXISTS "organization_logos_director_read" ON storage.objects;
CREATE POLICY "organization_logos_director_read"
  ON storage.objects FOR SELECT
  TO authenticated
  USING (
    bucket_id = 'organization-logos'
    AND (
      (SELECT public.is_platform_staff())
      OR CASE
           WHEN (storage.foldername(name))[1] ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
           THEN public.is_director_of(((storage.foldername(name))[1])::uuid)
           ELSE false
         END
    )
  );

DROP POLICY IF EXISTS "organization_logos_director_insert" ON storage.objects;
CREATE POLICY "organization_logos_director_insert"
  ON storage.objects FOR INSERT
  TO authenticated
  WITH CHECK (
    bucket_id = 'organization-logos'
    AND (
      (SELECT public.is_platform_staff())
      OR CASE
           WHEN (storage.foldername(name))[1] ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
           THEN public.is_director_of(((storage.foldername(name))[1])::uuid)
           ELSE false
         END
    )
  );

DROP POLICY IF EXISTS "organization_logos_director_delete" ON storage.objects;
CREATE POLICY "organization_logos_director_delete"
  ON storage.objects FOR DELETE
  TO authenticated
  USING (
    bucket_id = 'organization-logos'
    AND (
      (SELECT public.is_platform_staff())
      OR CASE
           WHEN (storage.foldername(name))[1] ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
           THEN public.is_director_of(((storage.foldername(name))[1])::uuid)
           ELSE false
         END
    )
  );
