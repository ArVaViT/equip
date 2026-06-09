-- Bootstrap for the RLS policy test (rls-policy-postgres CI job).
--
-- Loads BEFORE supabase/schema.sql + supabase/ci/rls_grants.sql so a vanilla
-- Postgres can recreate the prod RLS + privilege surface and then be probed
-- AS the `authenticated` role. Unlike replay_bootstrap.sql, here auth.uid()
-- is configurable (reads the JWT-sub GUC) so we can simulate a specific
-- logged-in user and prove RLS / privilege boundaries actually hold.

DROP SCHEMA IF EXISTS public CASCADE;

-- Supabase-managed roles referenced by the prod GRANTs. NOLOGIN: we reach
-- them via SET ROLE, never a real login.
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['anon', 'authenticated', 'service_role', 'authenticator', 'supabase_auth_admin']
  LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN', r);
    END IF;
  END LOOP;
END
$$;

CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE IF NOT EXISTS auth.users (
    id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text
);

-- Configurable GoTrue helpers: auth.uid() / auth.role() read the request GUCs
-- the test sets per-scenario, mirroring how Supabase injects the JWT claims.
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
    LANGUAGE sql STABLE
    AS $$ SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;

CREATE OR REPLACE FUNCTION auth.role() RETURNS text
    LANGUAGE sql STABLE
    AS $$ SELECT coalesce(nullif(current_setting('request.jwt.claim.role', true), ''), 'authenticated') $$;
