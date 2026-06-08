# Datadog monitors — Equip

Source-controlled monitor definitions for the Datadog log-alert
monitors that watch Equip's prod surface. Same pattern as the
dashboard JSON files in `../`: tweak in the Datadog UI when needed,
re-export the JSON back into this directory in the same PR so the
source of truth stays in git.

## Why monitors live here in JSON

We hit a real outage on 2026-06-03: the translation-worker cron
returned 401 every minute for ~37 minutes (`CRON_SECRET` env var
missing, Vercel sent no auth header). No monitor caught it — we
noticed only when sweeping logs by hand. These JSON files exist so
the next missing-secret regression pages on minute 6, not minute 37.

## Inventory

| File | What it catches | Priority |
|---|---|---|
| `translation-worker-401-rate.json` | Cron is firing but auth fails (≥ 5 401s in 15 min) | P2 |
| `worker-cron-silent.json` | Cron is NOT firing at all (≥ 15 min with no log line) | P2 |
| `backend-5xx-rate.json` | Backend 5xx rate > 5% over 10 min | P1 |
| `backend-unhandled-exception-rate.json` | Real unhandled 500s via `equip.errors.unhandled_total` | P2 |
| `translation-queue-backlog.json` | `translation_jobs` queued is not draining | P3 |

## Importing into Datadog

1. Datadog UI → `Monitors` → `New Monitor` → `Import` (bottom right).
2. Paste the file contents.
3. Confirm the slack handle in the `message` field matches the
   actual on-call channel (each monitor uses `@slack-equip-oncall`
   as a placeholder; rename when wiring).
4. Save.

## Editing convention

When tuning a threshold in the UI:

1. Open the monitor → `Edit JSON` (right side of the edit form).
2. Copy the JSON back into the matching file in this directory.
3. Same PR that ships the new threshold value to prod.

Out-of-band tweaks rot fast — within a month nobody remembers why
the threshold is 7 instead of 5.

## UI-only monitors — alert-noise audit (2026-06-05) — RETUNED 2026-06-08

Two monitors created ad-hoc in the Datadog UI (NOT in this directory) were
the source of an inbox flood — 81 alert emails in 7 days, all from these two,
each firing on Triggered → Recovered pairs and tripping on normal
serverless/SPA behaviour rather than real problems. Status after the
2026-06-08 retune (done via the Datadog API):

- **`[P2] equip backend: error log spike`** — **RETUNED.** Threshold raised
  from `≥ 5 errors / 10 min` to `≥ 10`, the warning level (was 2) dropped
  entirely, and a 60 s evaluation delay added so transient cold-start /
  deploy / pooler-restart blips self-recover before notifying. Still a
  cruder duplicate of `backend-unhandled-exception-rate.json` (which counts
  only *real* unhandled 500s); fold it into that scoped monitor when
  convenient, but it no longer floods.
- **`[P3] equip frontend: slow page load (avg LCP > 4s)`** — **self-cleared.**
  The big LCP fix (PR #746, anonymous-paint seed) brought the metric back
  under threshold; 0 events on 2026-06-08. Left as-is (now quiet).
- General rule for every monitor here: keep re-notification **off** — one
  email on Trigger is enough (all current monitors already set `renotify=0`).

### Failing Vercel log drain — FIX it, do NOT just delete it

The Vercel → Datadog **log drain** is failing ~80% (hourly "Drain failures
on Equip" emails). It is tempting to call it redundant because the app ships
logs to Datadog in-app via `DatadogHTTPHandler` — **but that handler is
WARNING+ only** (`logging.py`), while every `equip.*` metric is emitted as an
**INFO** log line (`app/core/metrics.py`). INFO reaches Datadog ONLY through
this drain. **So deleting the drain silently kills the entire metric +
dashboard layer** (engagement, translation-queue health, the
`translation-queue-backlog` monitor) — only the WARNING+ pages survive.

Correct fix order: **first** give `equip.metric` a second transport (a
dedicated low-level HTTP path in the handler, or POST to the Datadog metrics
API), verify metrics still flow, **then** the drain can be fixed or removed.
Until then, repair the drain (it's the only metric pipeline) — do not delete
it. (Deploy-failure emails are separate and safe to turn off: Vercel →
Account → Notifications.)

## Open follow-ups

- **`equip.engagement.drop_off_rate` monitor** — once the dashboard
  derived-metric stabilizes, add a P3 monitor that pages on a 30%
  drop-off ceiling per course.
- **`equip.translation.queue_depth` saturation monitor** — when
  `translation_jobs` queued > 50 for > 1h, page; queue isn't draining
  fast enough. (Requires adding a gauge emitter in
  `app/services/translation/queue.py` first.)
- **Vercel-side cron health check via Vercel Cron Audit log** —
  belt + braces over the Datadog log-presence check; Vercel's own
  cron history page surfaces failures even if Datadog forwarder
  breaks.

## Related

- `../course-engagement-dashboard.json` and `../teacher-load-dashboard.json` — the dashboards these monitors complement.
- [[reference-equip-vercel-cron-secret]] in personal memory — the
  trap the 401-rate monitor is built to catch.
