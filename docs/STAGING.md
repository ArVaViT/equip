# Staging environment

Staging is a full, isolated copy of the production stack, designed to be
**ephemeral**: cheap to spin up, safe to tear down, never a hard dependency
of CI (see `STAGING_ACTIVE` below).

| Piece | Production | Staging |
|---|---|---|
| Database | Supabase project `rrisqutxlkamwfhcashl` | Supabase **branch** `staging` (own project ref, own auth/storage) |
| Backend | Vercel `equip-backend` → `api.equipbible.com` (deploys from `main`) | Vercel `equip-backend-staging` → `api-staging.equipbible.com` (deploys from the `staging` git branch) |
| Frontend | Vercel `equip-frontend` → `equipbible.com` (deploys from `main`) | Vercel `equip-frontend-staging` → `staging.equipbible.com` (deploys from `staging`) |
| Data | Real users | Synthetic only (`scripts/seed_fat_test_course.py` + three `e2e-*@staging.equipbible.com` role users) |

## How deploys flow

The long-lived git branch `staging` is the deploy source for both staging
projects (their "production" environment). To put code on staging:

```powershell
git checkout staging
git merge --ff-only origin/main   # or cherry-pick a feature branch
git push origin staging
```

Both staging Vercel projects have an ignored-build-step that skips every
branch except `staging`, so PR pushes never double-build.

## Spin-up (from nothing, ~15 min)

1. **DB branch**: create a Supabase branch named `staging` (MCP
   `create_branch` or dashboard). The branch runner cannot replay our
   migration history (it predates the initial schema), so bootstrap from the
   DR baseline instead:
   - load `supabase/schema.sql` **minus the `CREATE SCHEMA public;` line**;
   - apply `supabase/ci/rls_grants.sql`;
   - replay the write-surface lockdown (branch default-privileges re-grant
     writes): `REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN
     SCHEMA public FROM anon, authenticated; GRANT UPDATE ON public.profiles
     TO authenticated; REVOKE SELECT ON public.quiz_options,
     public.daily_challenge_options, public.content_versions FROM anon,
     authenticated;` + the matching `ALTER DEFAULT PRIVILEGES`;
   - recreate `on_auth_user_created` (lives on `auth.users`, so it is NOT in
     the public-schema dump): `CREATE TRIGGER on_auth_user_created AFTER
     INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION
     public.handle_new_user();`
   - create the three storage buckets + the ten `storage.objects` policies
     (copy from prod `pg_policies`);
   - copy `supabase_migrations.schema_migrations` rows from prod so future
     `db push` stays idempotent.
2. **JWT parity**: new branches sign tokens with ES256; the backend expects
   the legacy HS256 secret (prod parity). Promote the branch's HS256 key:
   `previously_used` → `standby` → `in_use` via the Management API
   (`/config/auth/signing-keys`).
3. **Role users**: create `e2e-student|teacher|admin@staging.equipbible.com`
   via the branch auth admin API, promote roles in `profiles`.
4. **Seed**: `python -m scripts.seed_fat_test_course --course-id staging-fat
   --teacher-email e2e-teacher@staging.equipbible.com --modules 10
   --chapters-per-module 4 --students 30` with `DATABASE_URL` pointing at
   the branch pooler.
5. **Vercel env**: point the staging projects' env at the branch (URL, keys,
   `JWT_SECRET_KEY` = branch secret, `DD_ENV=staging`,
   `TRANSLATION_QUEUE_ENABLED=false`), then push `staging` to deploy.
6. Flip the repo variable `STAGING_ACTIVE` to `true`.

## Teardown

1. `gh variable set STAGING_ACTIVE --body "false"` — the authenticated e2e
   specs go back to skipping instead of failing.
2. Delete the Supabase branch (stops the ~$0.013/hr compute).
3. The Vercel projects, domains, and repo secrets can stay — they cost
   nothing while the branch is gone.

## e2e in CI

`frontend-e2e.yml` builds against staging when `STAGING_ACTIVE == 'true'`,
which unlocks the authenticated student/teacher/admin specs
(`E2E_*` repository secrets). In any other state — flag off, fork PR,
Dependabot PR — the build falls back to placeholder env and only the public
smoke/a11y specs run. CI therefore never turns red because staging is down.

## Guard-rails

- The staging cron workers are neutered: `TRANSLATION_QUEUE_ENABLED=false`;
  the daily-challenge worker runs but against staging data only.
- `DD_ENV=staging` keeps staging logs out of the production monitors.
- Synthetic students live on `@seed.invalid` (RFC 2606 — can never receive
  mail); role users live on `@staging.equipbible.com`.
- Never point staging env at the production database or vice versa; the
  backend's CORS origin (`staging.equipbible.com` + localhost for the e2e
  preview server) would be the first thing to break loudly.
