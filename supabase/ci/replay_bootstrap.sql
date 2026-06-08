-- ---------------------------------------------------------------------------
-- Supabase primitives that a plain Postgres instance does NOT have, but which
-- the production schema dump (../schema.sql) references. Loading this first
-- lets a vanilla `postgres:17` container replay the full prod schema in CI,
-- which proves the committed schema is reproducible from scratch (DR / drift
-- guard). This file is NOT a migration and never runs against prod — it only
-- stubs the Supabase-managed objects that live outside the `public` schema.
--
-- What the dump needs from us:
--   * roles anon / authenticated / service_role  -> RLS policies' TO clauses
--   * schema auth + auth.users(id)               -> 12 FK constraints
--   * auth.uid() / auth.role()                    -> 67 RLS policy predicates
-- ---------------------------------------------------------------------------

-- The prod dump emits `CREATE SCHEMA public;`, but a fresh database already
-- has one. Drop it so the dump can recreate it cleanly.
DROP SCHEMA IF EXISTS public CASCADE;

-- Supabase's built-in roles. NOLOGIN: we never authenticate as them in CI,
-- they only need to exist so `... TO authenticated` etc. resolves.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    CREATE ROLE anon NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    CREATE ROLE authenticated NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    CREATE ROLE service_role NOLOGIN;
  END IF;
END
$$;

-- The auth schema + a minimal auth.users so foreign keys can resolve.
CREATE SCHEMA IF NOT EXISTS auth;

CREATE TABLE IF NOT EXISTS auth.users (
    id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text
);

-- Stub the two GoTrue helpers referenced by RLS policies. In CI there is no
-- JWT, so they return NULL (every row-level check evaluates to "no current
-- user", which is fine — the replay only validates that the DDL is loadable).
CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
    LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;

CREATE OR REPLACE FUNCTION auth.role() RETURNS text
    LANGUAGE sql STABLE AS $$ SELECT NULL::text $$;
