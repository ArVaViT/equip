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
translation monitors below, four of which are committed here and **not yet
applied** — `scripts/apply_datadog_monitors.py --apply` creates them the
moment a write-scoped application key exists (see "Applying" at the bottom).
The 4 synthetic uptime checks (`/health`, frontend `/`, `/api/v1/courses`,
Supabase) are managed in the Synthetics UI and are not mirrored here.

## Inventory (the mirrored monitors)

| File | What it catches | Notify |
|---|---|---|
| `backend-error-log-spike.json` | ≥10 backend `status:error` logs in 10 min | **email** |
| `send-email-failures.json` | send-email edge fn logging delivery/function errors (silent email outage — Auth sees 200, users get nothing) | **email** |
| `daily-challenge-schedule-dry.json` | the editorial schedule ran out and the live path is auto-filling from the pool (seed fresh questions) | **email** |
| `translation-jobs-stuck-processing.json` | jobs piling up in `processing` (workers dying mid-run) | **email** |
| `equip-frontend-rum-error-spike.json` | spike in real-user JS errors (RUM) | **email** |
| `equip-backend-warning-log-spike.json` | ≥20 backend `status:warning` logs in 15 min | dashboard-only |
| `equip-frontend-slow-page-load-p75-lcp-4s.json` | p75 LCP > 4s over an hour (client-rendered SPA — noisy by nature) | dashboard-only |
| `equip-frontend-frustration-signals-rage-clicks.json` | ≥5 rage-clicks in 30 min | dashboard-only |

### Translation and spend (added 2026-08-17, not yet applied)

Nothing watched the translation pipeline's cost or health before this, which
is how production spent 81 days on a thinking model at roughly 840 billed-but-
unread tokens per string without anyone noticing.

| File | What it catches | Notify |
|---|---|---|
| `gemini-spend-spike.json` | billed output tokens over 500k in an hour — a model change, a loop, or a genuine bulk import | **email** |
| `gemini-thinking-tokens-returned.json` | **BLOCKED** — the metric it queries has no log-based-metric rule, so it cannot fire and the apply script refuses to create it. `docs/datadog/README.md` has the recipe | **email** |
| `gemini-call-failures.json` | the provider timing out or refusing past its own retries — translations stop landing and a publishing course stays invisible | **email** |
| `translation-backlog-not-draining.json` | the queue never reaches empty for two hours: refilled as fast as it drains, or a job failing and re-queuing | **email** |
| `edits-held-too-long.json` | edits to a live course blocked on a translation that cannot resolve itself — invisible to students, silent to the teacher | **email** |

### Translation quality (added 2026-08-22)

| File | What it catches | Notify |
|---|---|---|
| `a-row-is-parked-and-nobody-was-told.json` | a translation failed a blocking check and was parked at `needs_review`; the reader keeps the old text and nothing retries it until a person looks. One warning line, below the spike monitor's threshold | **email** |
| `scripture-served-in-the-wrong-language.json` | the canonical verse could not be had for the target language and the reader gets the source-language verse inside translated prose (`verse_fallback_to_source`); usually the Bible API answering 429 | **email** |

> **Note on queries.** These all match the backend's actual **Python-logger**
> log shape (`status:error` / `status:warning`, `service:…`), not HTTP-access
> fields. An earlier generation of JSONs queried `@http.url_details.path` /
> `@http.status_code`, which our logs don't carry, so they sat in No-Data;
> those were retired in favour of this set.

### Checked against production, 2026-08-19

Every file in this directory was read back against the live org before the
apply script went in. A monitor that reads correctly and queries nothing is
the failure mode this whole directory exists to avoid, so the check is worth
repeating whenever a query changes.

* **Metrics.** Fourteen `equip.*` metrics reported in the last thirty days.
  `tokens_output_total`,
  `calls_total` (tagged `model` and `outcome` — `success`, `retry`,
  `transport` all seen) and `translation.queue_depth` all return points.
  `tokens_thinking_total` does not exist at all — see the BLOCKED row above.
* **Log lines.** `staged_edits_blocked`, `auto-filled schedule` and `jobs
  stuck in processing` each match nothing in thirty days, which is the
  correct answer: all three are emitted at WARNING (so they ship in-process,
  not via the drain) and all three describe things that have not happened.
  The emitter for each was read in `app/` rather than inferred from the
  absence of logs. `status:warn` is the value the index actually carries —
  286 of them on `service:equip-backend` in the last week.
* **Thresholds.** `min(last_2h):min:equip.translation.queue_depth > 0` never
  had a two-hour window without a zero in the last seven days, so it is quiet
  by construction. The spend threshold was 2M output tokens an hour against a
  busiest-observed eight-hour window of 92,478, and was lowered to 500k /
  250k; the reasoning is in the monitor's own message.
* **Two real defects found.** The live Daily Challenge monitor's query
  carries PowerShell backticks where quotes belong — ``logs("service:equip-
  backend `"auto-filled schedule`"")`` — so the monitor that watches for a
  silent editorial outage has itself been silent since 2026-06-09. Applying
  the committed file fixes it. And `gemini-call-failures.json` added two
  metric series together, which Datadog joins on timestamp, so the sum was
  empty whenever only one outcome had points — i.e. almost always. It is one
  query with an OR scope now.

## Applying

```
cd backend
python scripts/apply_datadog_monitors.py            # dry run — prints the diff
python scripts/apply_datadog_monitors.py --apply    # writes it
```

One command for the whole directory: it creates what is missing, updates what
has drifted, and stays quiet about what already matches. Running it twice is a
no-op the second time.

The committed key is read-only by design (least privilege — it reads logs,
metrics, dashboards and monitors, and nothing else), so `--apply` needs a
new application key with exactly `monitors_read` + `monitors_write`.
[`docs/datadog/README.md`](../README.md) has the scope list, the `op run`
form of the command, and why the API key is not the application key.

Nothing needs recording in this table afterwards — the script matches by
name, not by id, which is what lets the file be the source of truth without a
hand-maintained id column.

## Re-export after a UI change

This is the half the script cannot do for you. It pushes files *to* Datadog;
it never pulls a UI edit *back*. Drift is real and it is quiet: the LCP
monitor was retuned in the UI from `avg` over 15 minutes to `p75` over an
hour on 2026-06-13 and the file still said `avg` two months later — so the
one thing a run of the script would have done is silently undo a deliberate
improvement. Dry-run first, always, and read the diff before `--apply`.

```
GET https://api.us5.datadoghq.com/api/v1/monitor/<id>
```
Keep `name`, `type`, `query`, `message`, `tags`, `priority`, `options`; drop the
runtime `id`/`overall_state`. Commit the diff in the same PR as the change.
