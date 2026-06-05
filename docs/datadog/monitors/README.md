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

## UI-only monitors to CLEAN UP (alert-noise audit, 2026-06-05)

Two monitors created ad-hoc in the Datadog UI (NOT in this directory) are
the source of an inbox flood — each fires **three** emails per incident
(Triggered → Warn → Recovered) and trips on normal serverless/SPA
behaviour rather than real problems. They are not in git because they were
never codified; the fix is to remove/retune them in the Datadog UI:

- **`[P2] equip backend: error log spike`** (≈ "5+ backend error logs in
  10 min") — **DELETE.** It is a cruder, far more sensitive duplicate of
  `backend-unhandled-exception-rate.json` (which counts only *real*
  unhandled 500s via `equip.errors.unhandled_total`, not cold-start 503s
  or Datadog-Synthetics noise). A 90 s prod log tail on 2026-06-05 showed
  **zero** errors; the spikes are transient cold-start / deploy bursts
  (a busy deploy day alone trips it repeatedly). Keep the scoped P1.
- **`[P3] equip frontend: slow page load (avg LCP > 4s)`** — **retune or
  drop the email.** The SPA is client-rendered (no SSR), so LCP naturally
  exceeds 4 s on slower networks; a 15-min average trips on ordinary
  real-user variance. P3 should not email at all. Raise the threshold +
  lengthen the window, or convert to a dashboard widget only.
- For BOTH (and every monitor here): turn **off** re-notification on Warn
  and Recovered — one email on Trigger is enough.

### Redundant + failing Vercel log drain

The Vercel → Datadog **log drain** is failing ~80% (hourly "Drain failures
on Equip" emails) AND is redundant: the app already ships WARNING+ logs to
Datadog in-app via `DatadogHTTPHandler` (`backend/app/core/logging.py`).
**Remove the drain** in Vercel → Settings → Log Drains. Single log path =
the in-app handler; INFO stays in Vercel's own log viewer. Also turn off
deploy-failure emails (Vercel → Account → Notifications) — preview/prod
deploy failures are already visible in CI.

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
