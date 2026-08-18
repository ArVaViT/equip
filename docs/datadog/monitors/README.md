# Datadog monitors — Equip

Source-controlled definitions for the live Datadog monitors. The Datadog org
is the runtime source of truth; these JSONs are the committed mirror — when you
retune a monitor in the UI, re-export its JSON here in the same PR.

## Philosophy: quiet by default

A solo operator drowns in a noisy inbox and then ignores it. So the rule is:
**email fires only on a real, actionable incident; everything else is
dashboard-only.** Concretely:

- Uptime + hard failures (synthetics down, error bursts, email-delivery
  failures, a stuck queue, the daily-challenge running dry) → **email**. These
  fire rarely, only when something is genuinely wrong.
- UX / tuning signals (LCP, rage-clicks) and backend *warnings* →
  **dashboard-only** (no `@` handle in the message). They're worth watching,
  not worth an email.
- Every monitor sets `notify_no_data: false` and `renotify_interval: 0` — one
  email per incident, never a "no data" page, never re-nags.

The live set is **12 monitors, 9 email / 3 dashboard-only**, plus the five
translation monitors below, which are committed here and **not yet applied**
(the Datadog key in 1Password is deliberately read-only, so they need a human
to import them — see "Applying" at the bottom). The 4 synthetic uptime checks
(`/health`, frontend `/`, `/api/v1/courses`, Supabase) are managed in the
Synthetics UI and are not mirrored here.

## Inventory (the mirrored monitors)

| File | What it catches | Notify |
|---|---|---|
| `backend-error-log-spike.json` | ≥10 backend `status:error` logs in 10 min | **email** |
| `send-email-failures.json` | send-email edge fn logging delivery/function errors (silent email outage — Auth sees 200, users get nothing) | **email** |
| `daily-challenge-schedule-dry.json` | the editorial schedule ran out and the live path is auto-filling from the pool (seed fresh questions) | **email** |
| `translation-jobs-stuck-processing.json` | jobs piling up in `processing` (workers dying mid-run) | **email** |
| `equip-frontend-rum-error-spike.json` | spike in real-user JS errors (RUM) | **email** |
| `equip-backend-warning-log-spike.json` | ≥20 backend `status:warning` logs in 15 min | dashboard-only |
| `equip-frontend-slow-page-load-avg-lcp-4s.json` | avg LCP > 4s (client-rendered SPA — noisy by nature) | dashboard-only |
| `equip-frontend-frustration-signals-rage-clicks.json` | ≥5 rage-clicks in 30 min | dashboard-only |

### Translation and spend (added 2026-08-17, not yet applied)

Nothing watched the translation pipeline's cost or health before this, which
is how production spent 81 days on a thinking model at roughly 840 billed-but-
unread tokens per string without anyone noticing.

| File | What it catches | Notify |
|---|---|---|
| `gemini-spend-spike.json` | billed output + thinking tokens over 2M in an hour — a model change, a loop, or a genuine bulk import | **email** |
| `gemini-thinking-tokens-returned.json` | the model is spending "thinking" tokens again: invisible in the reply, billed as output, and unnecessary for translation | **email** |
| `gemini-call-failures.json` | the provider timing out or refusing past its own retries — translations stop landing and a publishing course stays invisible | **email** |
| `translation-backlog-not-draining.json` | the queue never reaches empty for two hours: refilled as fast as it drains, or a job failing and re-queuing | **email** |
| `edits-held-too-long.json` | edits to a live course blocked on a translation that cannot resolve itself — invisible to students, silent to the teacher | **email** |

> **Note on queries.** These all match the backend's actual **Python-logger**
> log shape (`status:error` / `status:warning`, `service:…`), not HTTP-access
> fields. An earlier generation of JSONs queried `@http.url_details.path` /
> `@http.status_code`, which our logs don't carry, so they sat in No-Data;
> those were retired in favour of this set.

## Applying a new monitor

The committed key is read-only by design (least privilege — it reads logs,
metrics, dashboards and monitors, and nothing else), so importing needs a key
that can write. Either paste the JSON in the UI (`Monitors` → `New Monitor` →
`Import Monitor from JSON`), or with a write-scoped key:

```
curl -X POST "https://api.us5.datadoghq.com/api/v1/monitor" \
  -H "DD-API-KEY: $DD_API_KEY" -H "DD-APPLICATION-KEY: $DD_APP_KEY" \
  -H "Content-Type: application/json" \
  -d @docs/datadog/monitors/gemini-spend-spike.json
```

Then record the returned `id` in this table, so the next person can find the
live monitor from the file.

## Re-export after a UI change

```
GET https://api.us5.datadoghq.com/api/v1/monitor/<id>
```
Keep `name`, `type`, `query`, `message`, `tags`, `priority`, `options`; drop the
runtime `id`/`overall_state`. Commit the diff in the same PR as the change.
