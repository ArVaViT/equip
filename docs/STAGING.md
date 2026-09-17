# Authenticated e2e: a local stack, not a staging environment

There is no staging environment. There used to be one — a long-lived
Supabase branch plus two Vercel projects, kept up between releases so the
authenticated (student/teacher/admin) Playwright specs had somewhere real
to sign in against. It is gone; see "What happened to the old staging
tier" below for why. The `STAGING_ACTIVE` repo variable it was gated
behind is retired along with it — nothing in the workflows reads it any
more.

What replaced it: `.github/workflows/frontend-e2e.yml` boots a **complete
local stack inside the CI job** — Postgres + GoTrue (Auth) + Storage + Kong
via the Supabase CLI's `supabase start`, a real FastAPI backend, and the
built frontend — and runs the full Playwright suite, authenticated specs
included, against it. It costs nothing (all containers on the runner,
torn down when the job ends), needs no repository secrets (nothing to
leak, so fork and Dependabot PRs get the same coverage as everyone else),
and is provably fresh on every run instead of trusting a long-lived
environment to still reflect `main`.

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
   pilot-scale defaults by hand against a real environment when that's
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

## What happened to the old staging tier

The previous design was a long-lived Supabase branch (`staging`) plus two
Vercel projects, kept up between releases so CI had somewhere real to run
the authenticated specs against continuously rather than booting a fresh
stack per run. It had been `STAGING_ACTIVE=true` since 2026-07-04 while
the environment itself stopped moving that same day: the `staging` branch
sat 417 commits behind `main`, both Vercel projects still served the
03.07 deploy, and the branch was quietly in `MIGRATIONS_FAILED` the whole
time. CI built each day's frontend and ran the authenticated specs against
a 73-day-old backend and schema. They passed — which was the problem: a
green run said nothing about the contract the code actually shipped
against, and that's worse than an honest skip because it's
indistinguishable from real coverage.

The Supabase branch was deleted on 2026-09-15 (stopping its
~$0.013/hr compute) and `STAGING_ACTIVE` was flipped to `false`, which
made the authenticated specs skip on every run — an honest gap, but a
gap: nothing exercised a signed-in student or teacher until this local
stack replaced it. The core problem with the branch design wasn't cost,
it was staleness by construction — a shared environment nobody was
forced to keep current. A stack rebuilt from committed artifacts
(`schema.sql`, the migrations, the seed scripts) on every single run
can't go stale the same way: it either reflects `main` or the job fails.

The two Vercel projects (`equip-backend-staging`, `equip-frontend-staging`)
and their domains still exist and cost nothing while idle; they are
unrelated to this CI job and out of scope for it. Whether to keep them
around for anything else is a separate call.
