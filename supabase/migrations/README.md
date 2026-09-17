# Supabase migrations

This directory is the **source of truth** for the production database
schema. Every file here has been applied to production, except the newest
one while its PR is waiting to be applied. Most files correspond 1:1 to a
row in `supabase_migrations.schema_migrations` with the same version; 32
are recorded there under a different timestamp (see "Adding a new
migration", step 4).

## File naming

```
<UTC-timestamp>_<snake_case_name>.sql
```

The timestamp prefix follows the Supabase CLI convention
(`YYYYMMDDHHMMSS`) and determines application order. Do not rename
historical files — the timestamps match the `version` column in
`schema_migrations` and renaming would make a fresh project believe it
still has pending work.

## Adding a new migration

1. Pick a fresh UTC timestamp (`python -c "from datetime import datetime,
   timezone; print(datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S'))"`)
   and a short snake-case name.
2. Drop the SQL into a new `<timestamp>_<name>.sql` file. Keep each
   migration focused and idempotent where reasonable (`IF NOT EXISTS`,
   `DROP POLICY IF EXISTS`, etc.) so replays on a clean project don't
   explode.
3. Mirror the change in the SQLAlchemy models under `backend/app/models/`
   and in `supabase/schema.sql`, in the same PR. The tests build their
   database from the models, and
   `backend/tests/test_the_models_refuse_what_production_refuses.py`
   fails when the models and `schema.sql` disagree on a PRIMARY KEY or
   UNIQUE column set, a column's nullability, or an index the models
   declare — so a constraint that exists only in production cannot hide
   behind green tests again.
4. After merge, apply **that one file** and record it under **its own
   timestamp**, as described in
   [`docs/DEPLOYMENT.md` → How to apply](../../docs/DEPLOYMENT.md#how-to-apply)
   (`supabase db query --linked --file`, plus the `schema_migrations`
   row, in one transaction).

**Do not use `supabase db push`, and do not use the MCP
`apply_migration` tool.** 32 files here are recorded in
`schema_migrations` under timestamps other than their own (MCP records
the time it ran, not the file name), so `db push` sees them as pending
and would re-run them against production once the recorded versions are
repaired out of its way. `DEPLOYMENT.md` explains the failure in full.

## Rebuilding a fresh database

These files alone **cannot** rebuild a fresh database — the base tables
(`users`, `courses`, …) pre-date migration tracking, so the earliest
migrations here `ALTER` tables that no file in this directory creates.
The replayable baseline is [`supabase/schema.sql`](../schema.sql), a
`pg_dump --schema-only` of prod regenerated in the same PR as every
schema change. See [`supabase/ci/README.md`](../ci/README.md) for the
`schema-replay-postgres` CI job that proves it loads on a clean
Postgres, and for the regeneration recipe.

## Relationship with the app code

- Runtime: schema is read through SQLAlchemy models
  (`backend/app/models/*.py`). The app never runs these migrations at
  startup.
- Tests: `backend/tests/conftest.py` creates an in-memory SQLite from
  the models and drops it per-test; the migrations here are not
  consulted. `test_the_models_refuse_what_production_refuses.py` holds
  the models to `supabase/schema.sql` instead.
- CI: `.github/workflows/backend-ci.yml` has a `schema-smoke-postgres`
  job that materializes the same models against a real Postgres service
  container as a drift/type-compat check.

There is intentionally no second migration tool (Alembic was removed in
favor of this directory) — one source of truth, one place to look.
