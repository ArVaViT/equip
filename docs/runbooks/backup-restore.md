# Supabase backup + restore runbook

> ✅ **STATUS — 2026-06-06: DAILY BACKUPS ACTIVE.**
>
> Equip prod is on Supabase **Pro**. Daily physical (WAL-G) backups
> run automatically with ~8 days retained, so a lost project can be
> restored from the previous day. **PITR (point-in-time recovery,
> ~$100/mo) is still OFF** — recovery granularity is therefore "last
> daily snapshot", not "any second".
>
> **2026-06-11: a LOGICAL restore drill PASSED** (see drill log) —
> full pg_dump of prod restored into a throwaway project with exact
> row-count parity (incl. auth.users + all 37 RLS policies) and the
> throwaway deleted the same hour. The dashboard click-through
> drill against a WAL-G physical backup (the flow below) still
> needs one manual run by Vadym — the logical drill proves the DATA
> is recoverable, not the Supabase physical-backup pipeline.
>
> History: prod ran on the Free tier (no backups) by deliberate
> decision until 2026-06-06, when Vadym upgraded to Pro and daily
> backups switched on. The earlier "no recovery path" warning no
> longer applies.

Equip's database lives on Supabase managed Postgres. Once on Pro,
WAL-G point-in-time recovery (PITR) becomes available as a paid
add-on. This runbook covers the two operational scenarios that
matter:

1. **Routine drill** — a quarterly restore of the latest backup into
   a throwaway target, to prove the backup is actually usable.
2. **Incident recovery** — restoring after data loss in prod (a
   bad migration, accidental delete, ransom event).

If you've never run a restore against Equip before, do the drill
first. The first real-incident restore is the worst time to learn
where the dashboards live and what the env vars are called.

---

## Prerequisites

| Item | How to verify |
|---|---|
| Supabase project access at **Admin** role | Log in to https://supabase.com/dashboard, open the Equip project, confirm the `Database -> Backups` tab is visible |
| Vercel project access for `equip-backend` | `vercel projects ls --scope vadyms-projects-dfb6f76f` lists `equip-backend` |
| Local `supabase` CLI installed | `supabase --version` returns >= 2.0 |
| A non-prod Supabase project to restore INTO (drill) | Create a throwaway project once; document its `ref` here |

When the throwaway project exists, paste its ref below so future
runs don't have to recreate it:

```
DRILL_TARGET_PROJECT_REF: <fill in once created>
```

---

## Routine drill (quarterly)

**Why:** Backups that have never been restored are not backups. We've
shipped the WAL-G config but never proven it. Run this once a
quarter so the next real incident isn't the first time.

**Time budget:** 60-90 minutes including write-up.

### Steps

1. **Pick the backup window to restore.** Supabase keeps daily
   automated backups + PITR for the configured retention. For the
   drill, restore the most recent automated backup — it's the
   fastest and exercises the same code path as a real recovery.

2. **In the Supabase dashboard for the DRILL target project:**

   * `Database -> Backups -> Restore`.
   * Source: select the prod project (Supabase prompts for cross-
     project restore; needs Admin on both).
   * Backup: the most recent automated backup.
   * Confirm the wipe-and-replace warning — the drill target is
     intentionally throwaway.

3. **Watch the progress.** Supabase surfaces a progress bar +
   estimated completion. A typical restore for a course-school-
   scale dataset takes 10-30 minutes. If it stalls > 60 minutes,
   file a Supabase support ticket and continue with `Postmortem`
   below.

4. **Once the restore is "Complete", validate the data:**

   ```bash
   supabase db remote --project-ref $DRILL_TARGET_PROJECT_REF psql

   # Sanity row counts — these numbers should be in the same
   # order-of-magnitude as the drill source captured below.
   SELECT
     (SELECT count(*) FROM courses) AS courses,
     (SELECT count(*) FROM modules) AS modules,
     (SELECT count(*) FROM chapter_blocks) AS blocks,
     (SELECT count(*) FROM enrollments) AS enrollments,
     (SELECT count(*) FROM profiles) AS users;

   # Latest activity is within the backup window.
   SELECT max(created_at) FROM courses;
   SELECT max(created_at) FROM chapter_progress;
   ```

5. **Diff against the source snapshot.** Before kicking off the
   restore, capture the same row counts from prod (read-only query
   via Supabase MCP `execute_sql` works). Paste the diff in the
   drill log. Anything more than the expected delta (= writes
   between the backup timestamp and your snapshot capture)
   indicates the restore lost rows.

6. **Tear down.** Delete the drill target project so it doesn't
   accrue Supabase compute charges. If the same throwaway project
   is reused next quarter, you'll need to re-pause it via
   `Settings -> General -> Pause project` to keep the bill at $0.

7. **Update this runbook.** Append a row to the drill log table
   below with the date, who ran it, the source backup timestamp,
   the row-count delta observed, and any gotcha you hit. The
   point of the drill is to keep the runbook honest as Supabase's
   UI evolves.

### Drill log

| Date | Operator | Source backup | Row delta | Notes |
|---|---|---|---|---|
| 2026-06-11 | Claude (autonomous) | live pg_dump (logical variant, not WAL-G) | **0** — exact parity: courses 12, modules 15, blocks 28, enrollments 28, profiles 19, auth.users 19, dc_questions 204, content_versions 3606; 37 RLS policies present | Throwaway project `equip-restore-drill-20260611` created + deleted via Management API same hour. Gotchas: (1) new-project pooler DNS lags a few minutes — use the DIRECT host `db.<ref>.supabase.co:5432`; (2) `content_versions` circular self-FK is `DEFERRABLE INITIALLY DEFERRED`, so load data with `psql --single-transaction` and ordering doesn't matter; (3) load order: public schema → auth.users data → public data. Physical (dashboard) drill still pending. |

---

## Incident recovery

**Trigger conditions:**

* Catastrophic data loss confirmed (multiple tables truncated,
  ransom message, accidental `DROP TABLE` on prod).
* A bad migration was applied and forward-fix is harder than rollback.
* Suspected data integrity breach where the integrity window is
  known.

**Not a trigger:**

* A single row was deleted by mistake. Use the Supabase point-in-
  time query feature or undo via app code — restoring the whole
  database to recover one row is a much bigger blast radius than the
  original mistake.
* A bug shipped a few bad records. Same — fix-forward.

### Step 0 — Triage

Spend **5 minutes** answering these before touching anything:

1. What was the data state at time `T_GOOD` (most recent timestamp
   when prod was known-correct)?
2. What is the minimum acceptable RPO (recovery point objective)
   for THIS incident? If the answer is "anything in the last 24
   hours is fine", we use the daily backup. If "we cannot lose
   more than 10 minutes", we use PITR.
3. Who is the comms lead? Vadym defaults to lead on his own; for a
   pilot-school incident loop in the school director by email
   BEFORE the restore so they're not surprised by the brief outage.

### Step 1 — Freeze writes

Cut user traffic so the restore doesn't race with live writes.
Two options, in order of preference:

**A. Vercel maintenance mode (preferred — fast)**

```bash
# Set the env var that the backend respects as a kill switch:
vercel env add MAINTENANCE_MODE production
# value: "true"
vercel --prod equip-backend  # redeploy with the flag
```

(If `MAINTENANCE_MODE` isn't wired yet in the backend, fall through
to B.)

**B. Pause the Supabase project**

```bash
supabase projects pause --project-ref $PROD_PROJECT_REF
```

This blocks all reads and writes. Less surgical than maintenance
mode (the frontend gets a hard error), but guaranteed to stop
writes regardless of caller.

### Step 2 — Restore

Two paths depending on RPO:

**Path A — daily automated backup (RPO up to 24h)**

Same flow as the drill, but the target is **prod** and the source
backup is the most recent one taken BEFORE the incident timestamp.

* Supabase dashboard -> Backups -> Restore.
* Select the backup row dated immediately before `T_INCIDENT`.
* Confirm restore. **Verify the target project in the confirmation
  modal one more time** — restoring into the wrong project would be
  catastrophic.

**Path B — point-in-time recovery (RPO under 24h)**

* Supabase dashboard -> Backups -> Point in time recovery.
* Pick the exact timestamp `T_GOOD` (UTC).
* Same confirm modal — verify target.

### Step 3 — Verify

Before lifting the maintenance flag:

```sql
-- 1. Row counts match expectations for T_GOOD.
SELECT count(*) FROM courses;
SELECT count(*) FROM enrollments;
SELECT count(*) FROM chapter_progress;

-- 2. The latest record is at or before T_GOOD.
SELECT max(created_at) FROM courses;

-- 3. RLS policies survived (they did — Supabase restores them, but
--    visually confirm in the dashboard's Policies tab).

-- 4. Spot-check 3-5 known-good user accounts you can verify from
--    memory. If their data looks right, the restore worked.
```

Boot the backend locally against the restored DB and click through
the dashboard as a known-good user:

```bash
# Point your local dev backend at the restored project's connection
# string just for this check.
DATABASE_URL="postgres://..." uvicorn app.main:app
```

### Step 4 — Lift the freeze

Reverse step 1:

```bash
vercel env rm MAINTENANCE_MODE production  # or unpause the project
vercel --prod equip-backend
```

Sanity-check the prod dashboard one more time as a real user. The
first 15 minutes of traffic is when remaining issues will surface.

### Step 5 — Postmortem

Within 24 hours, write a postmortem:

* What was the root cause of the incident?
* What was the actual RPO (gap between `T_INCIDENT` and the
  restored `T_GOOD`)?
* Wallclock time for triage, restore, verify, lift.
* What broke in this runbook? Update the runbook with the fix in
  the SAME PR as the postmortem.

---

## Datadog hooks

* `equip.backup.last_restore_drill` — single-value gauge, age in
  days since the most recent drill log entry. Wired via a Datadog
  scheduled query against this file. (Configured in
  `equipbible-docs/runbooks/backup-monitoring.md`; the alert fires
  if the value exceeds 100 days.)
* Backup completion / failure events from Supabase land in Datadog
  via the existing Supabase log forwarder.

## Why no automation

The restore flow is intentionally a click-through, not a script.
Restoring the database is destructive — a runaway script that
accidentally targets prod would be the worst kind of incident. The
dashboard's confirm modals are a deliberate forcing function.

## See also

* [`OBSERVABILITY.md`](../OBSERVABILITY.md) — Datadog setup +
  dashboards.
* [`DEPLOYMENT.md`](../DEPLOYMENT.md) — Vercel deploy + env-var
  inventory.
* [`SECURITY.md`](../SECURITY.md) — RLS posture (relevant when
  restoring — RLS policies survive but should be re-verified).
