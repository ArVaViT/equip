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
| Frontend (Vite SPA) | `equip-frontend` | Push to `main` matching `frontend/**` | `equipbible.com` (`www.equipbible.com` 308-redirects to apex since 2026-06-11) |
| Backend (FastAPI on Python serverless) | `equip-backend` | Push to `main` matching `backend/**` | `api.equipbible.com` |
| Database schema | Supabase project `Equip` | **Manual** (see below) | Postgres schema |

Both Vercel projects auto-deploy from `main`. Every PR also gets a
deploy preview. Build settings, env vars, and custom domains live in
the Vercel project pages -- not in this repo.

## Pre-deploy checks (CI must be green)

`.github/workflows/backend-ci.yml`:

- `ruff check app/ tests/ scripts/` (zero warnings)
- `ruff format app/ tests/ scripts/ --check`
- `python -m py_compile app/main.py` + `python -m compileall app/`
  (every module byte-compiles) and a smoke import of `app.main:app`
- `mypy --config-file mypy.ini`
- `pytest tests/` against in-memory SQLite (3,200+ test functions)
- `pip-audit --requirement requirements.txt --strict` -- no ignores
  today; `--ignore-vuln` would be added in the workflow if one were ever
  needed
- Postgres jobs: `schema-smoke-postgres` materializes the SQLAlchemy
  models against a real Postgres service container (catches
  SQLite-only behaviour before it lands on the linked Supabase project),
  `schema-replay-postgres` replays `supabase/schema.sql` from zero, and
  `rls-policy-postgres` runs the denial probes in
  `supabase/ci/rls_assertions.sql` against the replayed schema.

`.github/workflows/frontend-ci.yml`:

- `npm ci` then `audit-ci --high --skip-dev` with an explicit allowlist
  (one advisory today; the list lives in the workflow, not in
  `package.json`)
- `eslint --max-warnings 0`
- `npm run i18n:check` (locale parity across ru / en / de / uk)
- `tsc --noEmit` (strict)
- `npm run build` (locale boot script, `vite build`, bundle-size budget)
- `vitest run --coverage` (jsdom), coverage uploaded to Codecov

CI is configured with `concurrency: cancel-in-progress` so re-pushes
to a PR don't pile up runs.

### What CI does not check: `frontend/vercel.json`

Nothing above exercises it. The e2e suite serves the built `dist/` with
`npx vite preview` on localhost, so Vercel's rewrites and headers — the
SPA fallback, the `/img/**` Supabase proxies, CSP, cache-control — are
never evaluated. A green pipeline says nothing about that file.

This is how the catch-all rewrite went unnoticed while it answered a
request for a deleted asset chunk with `200 text/html` instead of `404`,
which is what the browser reported as
`'text/html' is not a valid JavaScript MIME type`.

Verify a change to that file on a real preview deployment, not in CI.
Preview URLs sit behind Vercel SSO, so plain `curl` gets a 302 — use a
browser with a logged-in session, or check the aliased deployment after
merging.

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
2. **Apply that one file, and record it under the file's own timestamp**,
   in one transaction, from the directory linked to the project:
   ```bash
   f=supabase/migrations/<timestamp>_<name>.sql
   v=$(basename "$f" | cut -d_ -f1); n=$(basename "$f" .sql | cut -d_ -f2-)
   {
     echo "BEGIN;"
     cat "$f"
     echo "INSERT INTO supabase_migrations.schema_migrations (version, name)"
     echo "  VALUES ('$v', '$n') ON CONFLICT (version) DO NOTHING;"
     echo "COMMIT;"
   } > /tmp/apply-migration.sql
   supabase db query --linked --file /tmp/apply-migration.sql
   ```
   If any statement fails, nothing is applied and nothing is recorded.
3. **Verify**: `select version, name from supabase_migrations.schema_migrations
   order by version desc limit 5;` -- the file's timestamp should appear,
   and the change itself should be visible (`pg_indexes`,
   `information_schema.columns`, `pg_constraint`).
4. **Smoke-test the affected route** from production -- e.g. if the
   migration added a column, hit the endpoint that reads it.

### Never `supabase db push` against production

`db push` decides what to run by comparing the files in
`supabase/migrations/` with the versions in
`supabase_migrations.schema_migrations`. On this project the two do not
line up: 32 migrations were applied (mostly through the Supabase MCP
`apply_migration` tool, which records the moment it ran as the version)
and recorded under timestamps different from their file names. To `db
push`, those 32 files look unapplied, and the 32 recorded versions look
like migrations nobody has. It refuses on the second, and the repair it
suggests -- marking the recorded versions `reverted` -- clears the way
for it to run all 32 files again against the live database: column
drops, policy rewrites and grant revocations, replayed onto a schema
that already has them. The same applies to MCP `apply_migration` for a
new file: it records a version that is not the file's, and adds one more
mismatch.

Applying one named file (above) avoids both. Until the history is
repaired so that every file's timestamp is recorded, that is the only
path.

### What if the migration breaks prod

Migrations are append-only; do **not** edit a file that has been
applied. To revert:

1. Write a **new** migration with a fresh timestamp that undoes the
   bad change (drop the column, restore the policy, etc.).
2. Commit, merge, apply.
3. Update the SQLAlchemy model so the local test suite catches the
   revert.

### Schema baseline & disaster recovery

`supabase/migrations/*.sql` is **incremental history** and cannot replay onto a
blank database (the base tables predate migration tracking — they were made in
the dashboard). The replayable source of truth is **`supabase/schema.sql`**, a
`pg_dump --schema-only` of the prod `public` schema. CI job
`schema-replay-postgres` loads it into a clean Postgres 17 on every
schema-touching PR (bootstrapping the Supabase `auth`/roles primitives first via
`supabase/ci/replay_bootstrap.sql`), proving prod is reproducible from zero.

When you make an intentional prod schema change, **regenerate `schema.sql` in the
same PR** (see [`supabase/ci/README.md`](../supabase/ci/README.md) for the exact
`pg_dump` command). The diff is the audit trail; the replay job is the gate. This
is what would have caught the `cohorts.name` drift before it broke prod.

## Auth settings live in the repository

`supabase/config/auth.production.json` holds the Auth settings this
project keeps deliberately -- OTP lifetime, password floor, refresh-token
rotation, and the email rate limit. `.github/workflows/supabase-guardrails.yml`
checks them nightly and on every PR touching the file; drift fails the run.

Applying is never automatic. Run the workflow by hand with `apply=true`
(Actions -> Supabase Guardrails -> Run workflow) and it writes only the
settings that differ, then reads them back -- a PATCH to this endpoint is
not instant, so the read-back is the proof, not the response.

Settings not named in that file keep Supabase's defaults and are never
touched.

**Why it exists.** `rate_limit_email_sent` sat at 2 for months. Two auth
emails per hour, shared by sign-up and password recovery, was the real
reason recovery mail "went missing" while `/recover` answered 200 -- and
it was written off as a platform limit that needed custom SMTP. It is a
field in the Auth config. Nothing in the repository described it, so
nobody questioned it.

## Edge functions -- deployed by CI since 2026-09-14

`supabase/functions/send-email` is deployed by
`.github/workflows/edge-functions-deploy.yml` on every push to `main` that
touches it. Nothing needs doing by hand.

**What this replaced, and why it is worth remembering.** Until 2026-09-14
no workflow deployed the function: `git push` did nothing to it, and a
green pipeline on a PR that changed it meant only that its Deno tests
passed. The version answering Supabase Auth was whatever was last pushed
by hand. The failure was silent in the worst direction -- the code in
`main` and the code sending your users' email could differ for weeks with
every check green. On 2026-09-01 three merged fixes to the email copy sat
undeployed for exactly that reason.

Two guards now stand there:

* the deploy job runs on push and then **reads the function back**, so a
  deploy step that reports success without deploying fails the run;
* a drift job runs nightly and on every PR touching the function. It
  compares the deploy timestamp against the last commit that changed the
  source, and fails when production is older. That comparison would have
  caught 2026-09-01 the following morning.

The workflow needs `SUPABASE_ACCESS_TOKEN` in repository secrets. That
token carries full access to the Supabase project, which is the price of
CI being able to deploy at all -- keep it in mind when reviewing workflow
changes, and rotate it in 1Password and GitHub together.

Deploying by hand still works and is sometimes right (a hotfix while CI is
down):

```bash
cd ~/Projects/equip
op run -- supabase functions deploy send-email
```

`op run` because the CLI wants `SUPABASE_ACCESS_TOKEN`, which lives in
1Password and must not be pasted into a shell. If the CLI is not
signed in it says so; `supabase login` opens a browser.

The function reads its configuration from Supabase secrets (`supabase
secrets set NAME=value`), not from Vercel. A fresh project needs all of
these before the first auth email goes out:

| Secret | Role | Missing → |
|---|---|---|
| `SEND_EMAIL_HOOK_SECRET` | Verifies the Auth hook signature (standardwebhooks) | every auth email fails closed with `401` |
| `RESEND_API_KEY` | Sends through Resend | Resend rejects the call; logged as `Resend delivery failed (non-blocking)`, the auth action itself still succeeds |
| `SUPABASE_URL` + `EQUIP_PROFILE_READ_KEY` | Reads the recipient's profile to pick the email language | falls back to `preferred_locale` from the sign-up metadata, then to the default locale |
| `EQUIP_SITE_URL` | Where the verified link lands (default `https://equipbible.com`) | default is used |
| `DD_API_KEY` (+ `DD_SITE`, default `us5.datadoghq.com`) | Ships the function's logs to Datadog | logs stay in Supabase only; the `send-email-failures` monitor is blind |

`EQUIP_PROFILE_READ_KEY` carries a project prefix on purpose: the
platform reserves `SUPABASE_*` names and refuses to store custom ones
under that prefix.

**Verify with a real email, not with the CLI's output.** A deploy that
returns success can still ship broken copy — the wording is not type
checked against anything a person will read:

```bash
curl -s -X POST "$SUPABASE_URL/auth/v1/recover" \
  -H "apikey: $PUBLISHABLE_KEY" -H "Content-Type: application/json" \
  -d '{"email":"you+check@gmail.com"}'
```

Then open the inbox. Mind `smtp_max_frequency` (60s between emails to
one address) and the hourly project allowance -- both answer 429, and
`/recover` may answer 200 while sending nothing.

## Environment variables

Vercel project env vars are the source of truth for production
secrets. Local `.env` files are gitignored and never committed.

### Backend (`equip-backend`)

Required for the API to serve (collected by
`Settings.runtime_ready_errors()`; boot itself does not fail -- see below):

- `SUPABASE_URL` -- project URL
- `SUPABASE_SERVICE_ROLE_KEY` -- server-side admin client. The old
  `SUPABASE_KEY` name is **no longer read**: Supabase disabled the legacy
  key format on 2026-06-08, so a value under that name only made the
  settings look configured while every call came back `401`.
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
- `TRANSLATION_WORKER_SECRET` -- shared secret the translation cron presents
  (see *Translation worker cron* below). Unset → the worker endpoint 503s.
- `TRANSLATION_QUEUE_ENABLED=true` -- routes publish-time translation through
  the async queue (drained by the cron) instead of running inline.
- `CRON_SECRET` -- **must equal `TRANSLATION_WORKER_SECRET`** (see below).
- `RESEND_API_KEY` -- lets the backend send invitation emails
  (`app/services/email_service.py`). Missing → the invitation row is
  still created and a WARNING is logged; the director has to share the
  accept link by hand. Auth emails do not use this key -- they go through
  the `send-email` edge function, which has its own copy.
- `FRONTEND_URL` -- base for links inside backend-sent emails (the
  `/invite/accept` link). Defaults to `https://equipbible.com`; a local or
  preview backend should point it at its own frontend.
- `GEMINI_REVIEW_MODEL`, `GEMINI_TIMEOUT_SECONDS`, `GEMINI_MAX_OUTPUT_TOKENS`,
  `GEMINI_MIN_INTERVAL_SECONDS`, `TRANSLATION_WORKER_BUDGET_SECONDS` -- tuning
  knobs with measured defaults in `backend/app/core/config.py`; production runs
  the defaults.
- `MAX_COURSES_PER_TEACHER` -- **unset on production**, which runs the base
  plan's own number. The shipped limits live in
  `backend/app/services/limits.py` (`BASE_PLAN`), not in the environment; this
  var only overrides the course cap for a deployment that genuinely differs.
  See [ADR-0014](adr/0014-a-plan-decides-what-an-account-may-hold.md).

Missing required vars do **not** crash boot. `settings.runtime_ready_errors()`
collects them and logs a single `"booting in degraded mode; missing env
vars: ..."` WARNING at startup; static routes (`/health`, `/`, `/favicon.*`)
keep serving, while any route that needs the DB or auth returns a clean
`503` / `401` through the per-request handlers. This was a deliberate change
from the old crash-on-import behavior so a misconfigured preview can't turn
every favicon scrape into a 500 stack trace. CI exercises the configured
path via the `lint-and-test` job's env defaults.

#### Cron workers

`backend/vercel.json` declares two crons. Both present the same bearer
(`Authorization: Bearer ${CRON_SECRET}`) and both are validated the way
described below for the translation worker:

| Path | Schedule | Purpose |
|---|---|---|
| `GET /api/v1/internal/translation-worker` | `*/1 * * * *` (every minute) | drains the translation queue |
| `GET /api/v1/internal/daily-challenge-worker` | `0 9 * * *` (09:00 UTC daily) | publishes the day's Daily Challenge and tops up the schedule |

##### Translation worker

`backend/vercel.json` schedules `GET /api/v1/internal/translation-worker`
every minute (`*/1 * * * *`). Vercel signs each cron request with
`Authorization: Bearer ${CRON_SECRET}`, and the endpoint validates that
bearer (constant-time) against `TRANSLATION_WORKER_SECRET`. **Therefore
`CRON_SECRET` and `TRANSLATION_WORKER_SECRET` must be set to the SAME value
on `equip-backend`.** If `CRON_SECRET` is missing/mismatched the cron 401s
every tick and, with `TRANSLATION_QUEUE_ENABLED=true`, queued translations
silently never drain (this caused a ~37 min outage on 2026-06-03). The
`translation-worker-401-rate` + `worker-cron-silent` Datadog monitors now
page on a recurrence. **Pre-launch check:** `curl` the prod worker with no
auth → expect `401`; confirm recent drained jobs in `/admin/translations/
queue-status`.

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
| Max function duration | n/a (static) | 300 s (`functions` block in `vercel.json`) |
| Function memory | n/a | default (1024 MB) |
| Region | All edge / IAD1 | **PDX1** (`regions` in `vercel.json`) |
| Custom domains | `equipbible.com` (`www` 308-redirects to apex) | `api.equipbible.com` |
| Auto-deploy branch | `main` | `main` |
| Log Drain | Same drain | `drn_anVGfaiUT6UPtBCo` → Datadog us5 (json) |

### Why the backend runs in PDX1 and not next to its readers

The Supabase project is in **`us-west-2` (Oregon)**. The backend ran in
`iad1` (Virginia), the Vercel default, so every database round-trip
crossed the continent -- and a single API request makes about ten of
them. The school is on Eastern time, which makes `iad1` the intuitive
choice, and that intuition is backwards here: the reader pays the
distance to the function **once** per request, while the function pays
the distance to the database **once per query**.

Measured on 2026-09-20: `GET /api/v1/courses` spent 1141 ms server-side
in `iad1` after its N+1 was fixed, on five courses -- roughly 100 ms per
query, essentially all of it flight time. `/health`, which touches no
database, answered in 2 ms from the same warm function.

`pdx1` is Vercel's Portland region, the same AWS region the database is
in, so those round-trips become intra-region. `vercel.json` carries the
setting rather than the dashboard so it is reviewed, versioned, and
reverted like anything else.

If the database ever moves, this moves with it. The pairing is the
point; neither value means anything alone.

`backend/vercel.json` uses the modern `functions` + `rewrites` format:
the FastAPI entrypoint lives at `api/index.py` (re-exporting
`app.main:app`), a catch-all rewrite sends every path to it (the
function still receives the original request path), and `maxDuration`
is set to 300 s so the cron workers (Gemini generation, translation
batches -- one translation tick is budgeted at
`TRANSLATION_WORKER_BUDGET_SECONDS`, 180 s by default) have headroom over
the platform default.

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
| Function max duration | 300 s configured (`vercel.json`; the Pro cap is higher) | ≤ 180 s on a translation worker tick, ≤ 1 s on normal requests |
| Function memory | 3008 MB (Pro) | default 1024 MB |
| Edge requests / month | 1 M (Pro) | ~hundreds |
| Build execution / month | 6 000 min (Pro) | < 100 min |
| Bandwidth | 1 TB (Pro) | < 1 GB |

The only constraint we've actually had to plan around is the bundle
size cap: psycopg2 + bleach + SQLAlchemy push the wheel toward 15 MB,
so we keep `requirements.txt` lean (11 entries) and resist adding new
deps casually.

## CI / deploy environment variables to know about

Set in GitHub Actions repo secrets / vars (read by `backend-ci.yml`):

- `CI_SUPABASE_URL` (repo variable), `CI_SUPABASE_SERVICE_ROLE_KEY`
  (secret) -- placeholder by default
- `CI_DATABASE_URL` -- placeholder by default
- `CI_JWT_SECRET_KEY` -- placeholder by default (`ci-only-...`)

These are only used by the lint-and-test job so `Settings` reports a
configured runtime. Tests then bootstrap their own
SQLite in-memory DB via `conftest.py`. The placeholder values are safe
to keep in source.

## Known gaps / follow-ups

- **There is no staging environment.** [`E2E.md`](E2E.md) covers
  how DB-affecting changes are exercised instead: `frontend-e2e.yml` boots
  a complete local Supabase + FastAPI + frontend stack inside the CI job
  and runs the authenticated specs against that, on every run, for free.
  Vercel deploy previews work the way the rest of this section
  describes -- every PR gets a
  `<branch>-equip-frontend-vadyms-projects-dfb6f76f.vercel.app` URL that
  hits the **production** backend and database, so a DB-affecting change
  is not exercised against a disposable database by the preview itself
  (the CI job above is what exercises it safely).

  That substitution only started actually working on 2026-09-15.
  `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY` were set for the
  Production environment only, so `src/lib/supabase.ts` threw at module
  load on every preview and the page came up blank. Both are now set for
  Preview as well, pointing at production — which is what "previews hit
  the production database" above has always claimed. Neither value is a
  secret: both ship inside the production JS bundle.
- **No automatic migration apply.** Documented above. Worth revisiting
  once we enable point-in-time recovery (the project is on Pro; PITR is
  the paid add-on, currently OFF) -- the auto-apply story is much less
  scary when a fine-grained rollback is one click.
- **No deploy notification.** Vercel can ping a Slack channel on
  production deploy success/failure. Equip has no shared Slack today,
  so this is deferred until the team grows past one developer.
- **Edge functions deploy by hand and nothing notices the drift.** The
  gap is not the manual step -- migrations are manual too, on purpose --
  it is that nothing anywhere compares the deployed function against
  `main`. A check that fetched the running function and diffed it, or
  simply a CI job that deploys it on merge, would close it.
