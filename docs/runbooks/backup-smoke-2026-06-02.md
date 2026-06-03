# Backup smoke — 2026-06-02 (read-only)

Companion to [`backup-restore.md`](./backup-restore.md). This is **not**
a full PITR drill (no restore was performed); it's a read-only
integrity check against prod that proves the *source* the next drill
will read is internally consistent. The cross-project restore step
in the runbook still requires a Supabase dashboard UI click + the
60-90 minute wall-clock window.

## Why split smoke from drill

Two distinct failure modes need protection:

| Failure | Smoke catches it? | Full drill catches it? |
|---|---|---|
| Prod data is internally corrupt (orphan FKs, missing rows) | ✅ | ✅ |
| WAL-G PITR backups are unreadable / restore mechanics broken | ❌ | ✅ |
| Restore produces a different-shaped DB (missing extensions, lost grants) | ❌ | ✅ |

The smoke runs in a Claude session in ~30s via the Supabase MCP
`execute_sql` tool. The drill needs Vadym's hands. Run smoke
**before** the drill (cheaply rules out source-data issues so the
drill isn't trying to restore garbage).

## What the smoke ran (2026-06-02 02:34 UTC)

Project: `Equip` (`rrisqutxlkamwfhcashl`), Postgres 17.6.1.054,
us-west-2, status `ACTIVE_HEALTHY`.

### Row counts (baseline for comparing future restores)

| Table | Rows |
|---|---:|
| `courses` | 4 |
| `modules` | 10 |
| `chapters` | 32 |
| `chapter_blocks` | 28 |
| `quizzes` | 7 |
| `enrollments` | 22 |
| `profiles` (users) | 17 |
| `certificates` | 2 |

These numbers are the **expected baseline** for the next full
restore. A restore that produces materially different counts (10x
fewer enrollments, half the profiles) indicates partial backup —
escalate per the runbook's *Incident recovery* path before promoting
the restore.

### Latest activity timestamps

| Signal | Value |
|---|---|
| Latest `profiles.created_at` (new signup) | 2026-05-26 07:52 UTC |
| Latest `enrollments.enrolled_at` | 2026-05-29 03:28 UTC |
| Latest `courses.updated_at` | 2026-05-27 22:29 UTC |
| Latest `chapter_progress.completed_at` | 2026-05-29 03:32 UTC |
| `daily_challenge_attempts.submitted_at` max | `NULL` (table empty — added by migration `add_daily_challenge_foundation` on 2026-05-29; no attempts written yet) |
| Smoke run time | 2026-06-03 02:34 UTC |

Latest activity is 5 days behind the smoke time — consistent with
Equip's pre-pilot traffic shape (no production users yet, per
[[project-equip-prerelease-risk-window]]). When pilot lands and
traffic increases, refresh this baseline.

### Referential integrity (all expected = 0)

| Orphan check | Count |
|---|---:|
| `enrollments` rows with no `profiles.id` match | 0 |
| `enrollments` rows with no `courses.id` match | 0 |
| `chapters` rows with no `modules.id` match | 0 |
| `chapter_blocks` rows with no `chapters.id` match | 0 |
| `modules` rows with no `courses.id` match | 0 |

**All clean.** FK enforcement at write-time is holding — no orphan
rows means the next restore won't be paving over latent data
corruption.

### Migration history sanity

79 migrations applied, version stamps continuous from
`20260226191601` (`enable_rls_all_tables`) through
`20260531132917` (`profiles_calendar_ical_min_iat`). Full list in
the Supabase `supabase_migrations.schema_migrations` table; visible
via the MCP `list_migrations` tool.

## What this proves

* Prod data is internally consistent — orphan FK count is 0
  across the 5 highest-traffic relationships.
* The application's write paths (enrollment, chapter completion,
  course edit) ARE writing to the tables they should write to (the
  timestamps line up with traffic).
* The migration history is intact (continuous version stamps).
* If we restored the latest backup today and the restore matched
  these numbers, we'd be confident the restore was complete.

## What this does NOT prove

* That a restore actually works end-to-end. WAL-G + Supabase's
  managed PITR path has never been exercised against this project.
* That the restore preserves extensions, grants, RLS policies, or
  the migration history table itself.

**Next action (still owed):** run the full drill per
[`backup-restore.md` § Routine drill](./backup-restore.md#routine-drill-quarterly).
Estimated 60-90 minutes. Schedule for next quarterly window.

## Re-running this smoke

When you want a fresh snapshot, re-run these three queries via
`supabase:supabase` MCP `execute_sql` against project ref
`rrisqutxlkamwfhcashl`:

```sql
-- 1. Row counts
SELECT
  (SELECT count(*) FROM courses) AS courses,
  (SELECT count(*) FROM modules) AS modules,
  (SELECT count(*) FROM chapter_blocks) AS blocks,
  (SELECT count(*) FROM enrollments) AS enrollments,
  (SELECT count(*) FROM profiles) AS users,
  (SELECT count(*) FROM chapters) AS chapters,
  (SELECT count(*) FROM quizzes) AS quizzes,
  (SELECT count(*) FROM certificates) AS certificates;

-- 2. Latest activity
SELECT
  (SELECT max(created_at) FROM profiles) AS latest_user_signup,
  (SELECT max(enrolled_at) FROM enrollments) AS latest_enrollment,
  (SELECT max(updated_at) FROM courses) AS latest_course_edit,
  now() AS now_utc;

-- 3. FK integrity (each value MUST be 0)
SELECT
  (SELECT count(*) FROM enrollments e
     LEFT JOIN profiles p ON p.id = e.user_id
     WHERE p.id IS NULL) AS orphan_enrollments_no_user,
  (SELECT count(*) FROM enrollments e
     LEFT JOIN courses c ON c.id = e.course_id
     WHERE c.id IS NULL) AS orphan_enrollments_no_course,
  (SELECT count(*) FROM chapters ch
     LEFT JOIN modules m ON m.id = ch.module_id
     WHERE m.id IS NULL) AS orphan_chapters_no_module,
  (SELECT count(*) FROM chapter_blocks cb
     LEFT JOIN chapters ch ON ch.id = cb.chapter_id
     WHERE ch.id IS NULL) AS orphan_blocks_no_chapter,
  (SELECT count(*) FROM modules m
     LEFT JOIN courses c ON c.id = m.course_id
     WHERE c.id IS NULL) AS orphan_modules_no_course;
```

Copy the results into this file, replace the table contents above
with the new numbers, and commit. Filename pattern:
`backup-smoke-YYYY-MM-DD.md`.
