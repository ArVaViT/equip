# Authenticated e2e: a local stack per run

`.github/workflows/frontend-e2e.yml` boots a **complete local stack inside
the CI job** — Postgres + GoTrue (Auth) + Storage + Kong via the Supabase
CLI's `supabase start`, a real FastAPI backend, and the built frontend —
and runs the full Playwright suite, authenticated (student/teacher/admin)
specs included, against it. It costs nothing (all containers on the
runner, torn down when the job ends), needs no repository secrets (nothing
to leak, so fork and Dependabot PRs get the same coverage as everyone
else), and is provably fresh on every run: it is rebuilt from committed
artifacts (`schema.sql`, the migrations, the seed scripts), so it either
reflects `main` or the job fails.

There is no shared staging environment. A long-lived one was tried and
dropped because nothing forced it to stay current with `main`, so a green
run against it said nothing about the code being shipped.

## How the CI stack comes up

Read `.github/workflows/frontend-e2e.yml` for the authoritative sequence;
this is the shape of it:

1. **`supabase start`** (`supabase/config.toml`, `[db.migrations] enabled
   = false` — see that file's header for why) gives a fresh Postgres +
   GoTrue + Storage + Kong on localhost with the CLI's fixed local dev
   keys. Containers this job never touches (Studio, Realtime, imgproxy,
   postgres-meta, Edge Runtime, Logflare, Vector, Supavisor) are
   excluded with `-x` to keep the boot fast. Mailpit is kept:
   `e2e/sign-in-links.spec.ts` follows a real sign-in-link email.
2. **Schema** — `supabase/schema.sql` (minus its `CREATE SCHEMA public;`
   line; `supabase start` already made an empty one) loads onto that
   Postgres, then `supabase/ci/rls_grants.sql` (the dump was taken with
   `--no-privileges`, see `supabase/ci/README.md`) restores the GRANTs,
   then `supabase/ci/local_stack_lockdown.sql` re-asserts the write-surface
   REVOKEs and recreates the `on_auth_user_created` trigger (it lives on
   `auth.users`, outside the `public`-schema dump, so `schema.sql` never
   carries it). Storage buckets + policies aren't in `schema.sql` either
   (also outside `public`) — those come from replaying the specific
   `supabase/migrations/*.sql` files that created them, in the order they
   landed in prod.
3. **Role users** — real signups via GoTrue's admin API
   (`POST /auth/v1/admin/users`, pre-confirmed so no mail is needed),
   promoted to `teacher` / `admin` with a direct `UPDATE public.profiles`
   afterwards — `handle_new_user()` force-sets every signup to
   `role='student'` as an anti-escalation guard, so there is no signup-time
   shortcut around that UPDATE. Passwords are generated in the job and
   never leave it.
4. **Data** — `backend/scripts/seed_fat_test_course.py` with small
   numbers (`--modules 1 --chapters-per-module 1 --students 0`; the
   authenticated specs only need the teacher dashboard + analytics
   endpoint to see *a* course, not a realistic one — run it with its own
   pilot-scale defaults by hand against a local database when that's
   what's needed) plus `backend/scripts/seed_e2e_daily_challenge.py` (one
   published Daily Challenge question — the student dashboard's schedule
   autofill picks up any published question for "today" with no explicit
   schedule row needed).
5. **Backend** — `uvicorn app.main:app` against the local Postgres, with
   `JWT_SECRET_KEY` set to the local stack's GoTrue signing secret so the
   backend's own JWT verification (`app/core/security.py`) accepts tokens
   GoTrue just issued. `CORS_ORIGINS` is set explicitly because the
   backend's default allow-list matches any `localhost` port but not
   `127.0.0.1`, which is what the preview server binds.
6. **Frontend** — built with `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY`
   pointed at the local stack and `VITE_API_URL` at the local backend,
   served with `vite preview`, then the full Playwright suite runs against
   it — public smoke/a11y specs and the authenticated
   `student-flow.spec.ts` / `teacher-flow.spec.ts` specs together, in one
   job.

## What this does and doesn't cover

- The RLS/privilege boundary itself already has a dedicated, stricter
  probe: `rls-policy-postgres` in `backend-ci.yml` runs the actual denial
  assertions (`supabase/ci/rls_assertions.sql`) as the `authenticated`
  role. This job trusts that boundary and exercises the application on
  top of it — a real signed-in browser session hitting real API routes —
  which is a different (complementary) kind of coverage.
- Storage bucket/policy replay follows the documented recipe faithfully,
  but as of this writing none of the authenticated specs' API routes
  (`/health`, courses, the daily-challenge card, teacher courses,
  analytics) touch Supabase Storage at all — so today it's provably
  correct DDL that nothing in the suite currently exercises. Worth
  knowing if a future spec starts asserting on file upload/download.
- Only Chromium runs here (see `playwright.config.ts`'s comment on why) —
  this local stack doesn't change that.
