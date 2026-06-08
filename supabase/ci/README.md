# Schema replay (DR + drift guard)

`supabase/schema.sql` is a faithful `pg_dump --schema-only` of the **production**
`public` schema. It is the answer to "can we rebuild prod from zero?" — the CI
job `schema-replay-postgres` (in `.github/workflows/backend-ci.yml`) loads it
into a clean Postgres 17 on every PR that touches schema artifacts, after first
stubbing the Supabase-managed primitives the dump references
(`replay_bootstrap.sql`: the `auth` schema + `auth.uid()`/`auth.role()` +
`anon`/`authenticated`/`service_role` roles).

## Why this exists

The `supabase/migrations/*.sql` files are **incremental history**, not a
replayable baseline: the base tables (`users`, `courses`, …) were created in the
Supabase dashboard before migration tracking began, so the first migration
`ALTER`s tables that a from-scratch replay doesn't have. `schema.sql` closes
that gap — it is the single replayable source of truth for the current shape.

It also doubles as a **drift detector**: prod was once changed out-of-band (the
`cohorts.name` drop never reached the repo, silently breaking cohort creation).
Regenerating `schema.sql` after any prod change surfaces the delta as a reviewable
diff. If the dump stops matching reality, the replay job's table-count guard or a
later migration will fail.

## Regenerating after an intentional prod schema change

From a machine with PostgreSQL 17 client tools (`pg_dump`) and the prod
**session-pooler** connection string (port 5432, not the 6543 transaction pooler):

```bash
pg_dump --schema=public --schema-only --no-owner --no-privileges --no-comments \
  --dbname="postgresql://postgres.<ref>:<pwd>@<host>:5432/postgres?sslmode=require" \
  -f supabase/schema.sql
```

Commit the regenerated file in the same PR as the migration that caused the
change. The replay job will confirm it still loads from scratch.

> This file never runs against prod. It is read-only DR/CI tooling.
