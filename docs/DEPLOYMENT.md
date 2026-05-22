# Deployment runbook

How a change goes from a green PR to live on `equipbible.com` /
`api.equipbible.com`. Companion to [`OBSERVABILITY.md`](OBSERVABILITY.md)
(post-deploy verification) and [`SECURITY.md`](SECURITY.md).

> **Note:** Section headings use Title Case and are stable -- other docs
> may link by anchor.

## What deploys when

The repo has **two Vercel projects** and **one Supabase project**:

| Surface | Project | Triggers | Output |
|---|---|---|---|
| Frontend (Vite SPA) | `equip-frontend` | Push to `main` matching `frontend/**` | `equipbible.com` + `www.equipbible.com` (apex) |
| Backend (FastAPI on Python serverless) | `equip-backend` | Push to `main` matching `backend/**` | `api.equipbible.com` |
| Database schema | Supabase project `Equip` | **Manual** (see below) | Postgres schema |

Both Vercel projects auto-deploy from `main`. Every PR also gets a
deploy preview. Build settings, env vars, and custom domains live in
the Vercel project pages -- not in this repo.

## Pre-deploy checks (CI must be green)

`.github/workflows/backend-ci.yml`:

- `ruff check .` (zero warnings)
- `ruff format --check .`
- `python -m py_compile` (smoke import of every module)
- `mypy --config-file mypy.ini`
- `pytest tests/` against in-memory SQLite (~600 tests)
- `pip-audit` (allow-list-of-known-issues only)
- A second job `schema-smoke-postgres` materializes the SQLAlchemy
  models against a real Postgres service container -- catches
  SQLite-only behaviour before it lands on the linked Supabase project.

`.github/workflows/frontend-ci.yml`:

- `npm ci` then `npm audit --omit=dev`
- `eslint --max-warnings 0`
- `tsc --noEmit` (strict)
- `vite build`
- `vitest run` (jsdom)

CI is configured with `concurrency: cancel-in-progress` so re-pushes
to a PR don't pile up runs.

## Normal release flow

Most changes need **no extra steps** -- merge to `main`, Vercel picks
it up, both services are live in 60-120 s.

1. PR opened. CI runs. Vercel posts a preview link on the PR for both
   frontend and backend.
2. Reviewer (or you, on a solo change) checks the preview.
3. Merge to `main`. Vercel kicks off the production build automatically.
4. Vercel finishes; the new commit SHA shows up at
   `https://api.equipbible.com/` (root JSON) and in the frontend's
   "Inspect Element → version" footer.

That's it. No manual deploy step, no SSH, no `vercel --prod`.

### Post-merge verification (90 seconds)

After the production build finishes:

1. `curl -sI https://api.equipbible.com/health` -- expect `HTTP/2 200`
   and an `X-Request-Id` header (PR #326 onward).
2. `curl -s https://equipbible.com/ | grep -c "<title>"` -- expect `1`.
3. Run the [`OBSERVABILITY.md` "Check Datadog"](OBSERVABILITY.md#check-datadog----one-shot-status-snapshot)
   PowerShell snippet. Synthetics should still be `live`; no monitors
   firing.

If any of those fail, see "Rolling back" below.

## Database migrations -- the one manual step

Migrations are **not auto-applied on deploy**. This is deliberate.
The migration file is the source of truth and gets committed alongside
the app code, but the actual `ALTER TABLE` runs against the linked
Supabase project as a separate, human-initiated action.

### Why manual

- The app code never reads `supabase/migrations/*.sql` at runtime. The
  runtime schema is whatever Supabase says it is. If the SQL file in
  the PR is wrong, applying it on deploy could corrupt prod before
  anyone notices.
- A migration that does heavy work (rebuilds an index, rewrites a
  column with a default) is best done at a chosen quiet moment, not
  whenever the next merge-to-`main` happens.
- Vadym wants to read the migration before it touches prod. The
  agent-driven workflow can write the migration and queue it in a PR,
  but applying is human-only.

### How to apply

After the PR is merged and CI is green:

1. **Verify the migration file landed on `main`**: `git log --oneline -- supabase/migrations/`
   should show the newest timestamp at the top.
2. **Apply via Supabase MCP** (preferred, no CLI install needed):
   ```
   apply_migration(
     name="<short_snake_case_name>",
     query=<contents of the .sql file>
   )
   ```
   The Supabase MCP server reports success / failure and writes a row
   to `supabase_migrations.schema_migrations`.
3. **Or apply via the Supabase CLI** (if you're at a terminal with
   `supabase` linked to the project):
   ```bash
   cd supabase
   supabase db push --linked
   ```
4. **Verify**: `select version from supabase_migrations.schema_migrations
   order by version desc limit 5;` -- the new timestamp should appear.
5. **Smoke-test the affected route** from production -- e.g. if the
   migration added a column, hit the endpoint that reads it.

### What if the migration breaks prod

Migrations are append-only; do **not** edit a file that has been
applied. To revert:

1. Write a **new** migration with a fresh timestamp that undoes the
   bad change (drop the column, restore the policy, etc.).
2. Commit, merge, apply.
3. Update the SQLAlchemy model so the local test suite catches the
   revert.

## Environment variables

Vercel project env vars are the source of truth for production
secrets. Local `.env` files are gitignored and never committed.

### Backend (`equip-backend`)

Required at boot (`Settings.load_alternative_env_vars` raises on absence):

- `SUPABASE_URL` -- project URL
- `SUPABASE_SERVICE_ROLE_KEY` (or legacy `SUPABASE_KEY`) -- server-side
  admin client
- `DATABASE_URL` (or `POSTGRES_URL` / `POSTGRES_PRISMA_URL`) -- pooled
  Postgres connection
- `JWT_SECRET_KEY` (or `SUPABASE_JWT_SECRET`) -- Supabase JWT verification

Optional but production-set:

- `GEMINI_API_KEY` -- enables the translation pipeline (missing → no-op)
- `YOUVERSION_API_KEY` -- enables `/api/v1/verse-of-the-day` (missing → 404,
  frontend hides the card)
- `DD_API_KEY` + `DD_SITE=us5.datadoghq.com` + `DD_SERVICE=equip-backend`
  + `DD_ENV=production` -- enables the `DatadogHTTPHandler` log shipping
- `CORS_ORIGINS`, `CORS_ORIGIN_REGEX` -- override the defaults (rarely needed)

Missing-but-required vars cause a `ValueError` at first Settings
instantiation, which surfaces in Vercel as a 500 on the first request
and a stack trace in the function logs. CI catches the same shape via
the `lint-and-test` job's env defaults.

### Frontend (`equip-frontend`)

Build-time only (Vite inlines `VITE_*` into the bundle):

- `VITE_API_URL` -- absolute URL of the backend (`https://api.equipbible.com`)
- `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` -- Supabase client
- `VITE_DATADOG_APPLICATION_ID`, `VITE_DATADOG_CLIENT_TOKEN`,
  `VITE_DATADOG_ENV`, `VITE_DATADOG_SITE`, `VITE_DATADOG_SERVICE`,
  `VITE_APP_VERSION` -- enables RUM. Missing applicationId/clientToken
  → `initDatadogRum()` is a no-op.

Build-time only on Vercel (not in the bundle):

- `DATADOG_API_KEY`, `DATADOG_SITE` -- used by `scripts/upload-sourcemaps.mjs`
  to push `.map` files to Datadog after `vite build`. Missing → build
  still succeeds but RUM stack traces will be minified.

## Vercel project settings (current)

| Setting | `equip-frontend` | `equip-backend` |
|---|---|---|
| Framework preset | Vite | Other (custom `vercel.json`) |
| Node version | 22.x | n/a (Python 3.12) |
| Max function duration | n/a (static) | default (10 s on Pro plan) |
| Function memory | n/a | default (1024 MB) |
| Region | All edge / IAD1 | IAD1 (default Python serverless) |
| Custom domains | `equipbible.com`, `www.equipbible.com` | `api.equipbible.com` |
| Auto-deploy branch | `main` | `main` |
| Log Drain | Same drain | `drn_JWO7AolUh4PEEUXB` → Datadog us5 |

`backend/vercel.json` sets `maxLambdaSize: 50mb` and a single catch-all
route to `index.py`. There are no other custom Vercel settings on the
backend -- the FastAPI handler is the default `@vercel/python` build.

`frontend/vercel.json` adds SPA fallback rewrites, the
Supabase-storage image rewrite (`/img/<bucket>/<path>`), and the strict
CSP header set. No custom build command -- Vercel's Vite preset runs
`npm run build`.

## Rolling back

Three options, in order of preference:

1. **Vercel instant rollback** (Dashboard → project → Deployments →
   pick a known-good build → "Promote to production"). Effective
   immediately, no rebuild. Use this for almost every "we just shipped
   a bad change" scenario.
2. **Revert the merge commit** on `main` (`git revert <sha>`), push, and
   let Vercel rebuild. Slower (build time) but leaves a clean git
   history. Use when you also need the revert recorded in source.
3. **Roll forward with a hotfix PR.** Use when the bad code is mixed
   with good code in the same release and only one piece needs undoing.

For DB migration breakage, see "What if the migration breaks prod"
above -- migrations roll forward, not back.

## Vercel build limits we're inside today

These are the Pro-plan limits (the team plan; account `arvavitcorp`,
team `vadyms-projects-dfb6f76f`). Current usage is well below all of
them.

| Limit | Value | Where we sit |
|---|---|---|
| Function bundle size | 50 MB unzipped (backend `vercel.json` cap) | ~12-15 MB |
| Function max duration | 60 s (Pro) | ≤ 30 s on Gemini translation, ≤ 1 s on normal requests |
| Function memory | 3008 MB (Pro) | default 1024 MB |
| Edge requests / month | 1 M (Pro) | ~hundreds |
| Build execution / month | 6 000 min (Pro) | < 100 min |
| Bandwidth | 1 TB (Pro) | < 1 GB |

The only constraint we've actually had to plan around is the bundle
size cap: psycopg2 + bleach + SQLAlchemy push the wheel toward 15 MB,
so we keep `requirements.txt` lean (10 entries) and resist adding new
deps casually.

## CI / deploy environment variables to know about

Set in GitHub Actions repo secrets / vars (read by `backend-ci.yml`):

- `CI_SUPABASE_URL`, `CI_SUPABASE_ANON_KEY` -- placeholder by default
- `CI_DATABASE_URL` -- placeholder by default
- `CI_JWT_SECRET_KEY` -- placeholder by default (`ci-only-...`)

These are only used by the lint-and-test job to satisfy
`Settings.load_alternative_env_vars`. Tests then bootstrap their own
SQLite in-memory DB via `conftest.py`. The placeholder values are safe
to keep in source.

## Known gaps / follow-ups

- **No staging environment.** Vercel deploy previews substitute for one
  -- every PR gets a `<branch>-equip-frontend-vadyms-projects-dfb6f76f.vercel.app`
  URL that hits the same backend. For DB-affecting changes, this means
  preview backends share the production DB. If we ever need a true
  staging tier, the cleanest path is a separate Supabase project +
  separate Vercel project bound to a `staging` branch.
- **No automatic migration apply.** Documented above. Worth revisiting
  once we have point-in-time recovery (Supabase Pro) -- the auto-apply
  story is much less scary when a 5-minute rollback is one click.
- **No deploy notification.** Vercel can ping a Slack channel on
  production deploy success/failure. Equip has no shared Slack today,
  so this is deferred until the team grows past one developer.
