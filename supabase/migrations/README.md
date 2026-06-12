# Supabase migrations

This directory is the **source of truth** for the production database
schema. Every file here corresponds 1:1 to a row in
`supabase_migrations.schema_migrations` on the linked Supabase project
and has already been applied to production.

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
3. Apply the migration to the target project. Two options:
   - Via the Supabase MCP tool `apply_migration` (one call per migration).
   - Via the Supabase CLI: `supabase db push --linked`.
4. Mirror the change in the SQLAlchemy models under `backend/app/models/`
   so tests (which bootstrap the schema via `Base.metadata.create_all()`)
   stay aligned with production.

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
  consulted.
- CI: `.github/workflows/backend-ci.yml` has a `schema-smoke-postgres`
  job that materializes the same models against a real Postgres service
  container as a drift/type-compat check.

There is intentionally no second migration tool (Alembic was removed in
favor of this directory) — one source of truth, one place to look.
