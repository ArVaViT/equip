# Observability runbook

How we see what production is doing, where alerts go, and how to debug a
prod incident. Companion to [`SECURITY.md`](SECURITY.md) (security
posture) and [`DEPLOYMENT.md`](DEPLOYMENT.md) (release process).

> **Note:** Section headings use Title Case and are stable -- other docs
> may link by anchor.

## What's wired up today

Everything below is live on `equipbible.com` / `api.equipbible.com`.
Configured 2026-05-11 to 2026-05-13. Org `arvavitcorp`, Datadog site
`us5.datadoghq.com`.

| Surface | Tool | Coverage |
|---|---|---|
| Frontend errors, sessions, replays, Core Web Vitals | Datadog RUM (`equip-frontend`) | 100 % session + 100 % replay sampling; React-Router integration so dashboards aggregate by route template |
| Backend WARNING / ERROR / CRITICAL logs | `DatadogHTTPHandler` in `backend/app/core/logging.py` | Per-record HTTPS POST to Datadog intake, tagged with env / service / version / vercel_region / vercel.request_id |
| Backend INFO logs + build logs + edge events | Vercel Log Drain `drn_DJUgg6MWFVruo4qV` ("Datadog (us5)", `deliveryFormat: json`) | json stream from Vercel → Datadog intake (the intake URL carries `ddtags` such as `env:production`); covers both `equip-frontend` and `equip-backend` projects. Replaced the original ndjson drain on 2026-06-11 -- Datadog intake answered 415 to ndjson payloads. |
| External uptime | 3 Datadog synthetic monitors (30 min cadence, 2 retries, aws:us-east-1) | `https://api.equipbible.com/health`, `https://equipbible.com/`, `https://api.equipbible.com/api/v1/courses` |
| Transactional email delivery | Supabase Edge Function `send-email` → Resend (verified domain `equipbible.com`) | Function ships its own logs to Datadog when `DD_API_KEY` is set; one monitor on its error stream |

We **do not** currently run Datadog APM (Python tracer). `ddtrace` is not
installed in the backend. End-to-end backend traces are out of scope
until per-request log volume proves we can afford the ingest. RUM is
already configured to add tracing headers (`allowedTracingUrls`); the
backend just doesn't pick them up yet.

We also do not run Sentry. The Datadog Error Tracking surface on top of
RUM (frontend) and Logs (backend) covers what Sentry would, with the
same alert flow.

## How a backend log gets to Datadog

```
FastAPI route raises / logger.warning / logger.error
       ↓
root logger configured in app.core.logging.setup_logging()
       ↓                                                    ↓
StreamHandler → stdout                          DatadogHTTPHandler.emit()
       ↓                                                    ↓
Vercel captures stdout                          synchronous POST with 0.5s timeout
       ↓                                          to https://http-intake.logs.us5.datadoghq.com
Vercel Log Drain drn_DJUgg6MWFVruo4qV                       ↓
       ↓                                          Datadog index "main" (15-day retention)
Datadog index "main"                                        ↓
                                              tagged: env, service, version (git SHA[:7]),
                                                      vercel_region, vercel.request_id
```

The two paths are **complementary, not duplicate**. The in-process
handler ships only WARNING and above, with structured fields and the
per-request `vercel.request_id` correlation key. The log drain ships
everything Vercel sees (including INFO request lines, build failures,
edge events, firewall events) but without the per-record tags.

Both end up in the same `main` index, so a Datadog log query that
filters by `service:equip-backend` gets both. The daily ingest cap is
**10 000 events / day** with a warning at 80 % -- a defensive cost
control against a logging-loop bug, not an expected ceiling.

### Request correlation

Every backend response carries an `X-Request-Id` header (PR #326). The
value is `x-vercel-id` when the request came through Vercel (so it
matches the Vercel log viewer), otherwise a UUID hex minted by the
backend. The same value is stashed in `app.core.logging.vercel_request_id`
and attached to every WARNING+ log shipped to Datadog as the field
`vercel.request_id` -- so a RUM session error, a Vercel log line, and a
Datadog log record all join on one id.

To pivot from a user bug report:

1. Ask them to paste the `X-Request-Id` from their network tab (or read
   it from the RUM error context).
2. In Datadog Logs: `service:equip-backend @vercel.request_id:<id>`.
3. From there, click into the trace if APM is ever enabled, or jump to
   the matching RUM session.

## Monitors and where they alert

All monitors notify `arvavitcorp@gmail.com`. There is no SMS / PagerDuty
routing today -- Equip is one-developer-on-call; email and the in-app
Datadog inbox are the routes.

| ID | Type | What it fires on | Severity |
|---|---|---|---|
| 19728703 | Synthetics alert | Backend `/health` fails (3 retries) | crit |
| 19728704 | Synthetics alert | Frontend `/` fails or body doesn't contain "Bible School" | crit |
| 19728705 | Synthetics alert | Backend `/api/v1/courses` non-200 or non-JSON | crit |
| 19728791 | RUM alert | ≥ 10 frontend errors in 10 min (warn at 5) | `priority:2` |
| 19728792 | RUM alert | ≥ 5 rage clicks in 30 min (warn at 3) | warn |
| 19728793 | RUM alert | avg LCP > 4 s over 15 min (warn 2.5 s). LCP is in **nanoseconds** in RUM events -- never use ms thresholds | warn |
| 19730778 | Log alert | ≥ 10 ERROR / CRITICAL backend log lines in 10 min (warn at 6), scoped `source:python` | `priority:2` |
| 19730779 | Log alert | ≥ 20 WARNING backend log lines in 15 min (warn at 10) -- usually IntegrityError noise. Scoped `source:python` | warn |
| 19761387 | Log alert | ≥ 3 error logs from `service:send-email status:error` in 10 min (warn at 1) | `priority:2` |
| 20465339 | Log alert | Translation jobs stuck in `processing` -- watches the worker's "jobs stuck in processing" WARNING line. (Replaced metric monitor `20393856`, deleted 2026-06-11 -- the metric it queried never existed, so it could never fire.) | `priority:3` |
| 20391511 | Log alert | Daily Challenge schedule ran dry -- watches the "auto-filled schedule" line, now logged at WARNING so it reaches Datadog (at INFO the monitor was blind) | warn |

The backend spike monitors (19730778 / 19730779) are scoped to
`source:python` so each record counts once -- without the scope, lines
arriving via both the in-process handler and the log drain would
double-count toward the threshold.

Dashboards:

- [Equip overview (RUM)](https://app.us5.datadoghq.com/dashboard/shf-kq8-bgf) -- `shf-kq8-bgf`
- [Equip backend (logs + synthetics)](https://app.us5.datadoghq.com/dashboard/x7b-cua-zrm) -- `x7b-cua-zrm`
- [Equip teacher load](https://app.us5.datadoghq.com/dashboard/54n-cn8-nhm) -- `54n-cn8-nhm` (grading throughput, time-to-grade)
- [Equip course engagement](https://app.us5.datadoghq.com/dashboard/dgr-dh4-n4x) -- `dgr-dh4-n4x` (active users, completion, drop-off, locale split)

The first two have a `$env` template variable that defaults to
`production`; the teacher-load and course-engagement dashboards are
JSON-managed in git -- see
[`docs/datadog/README.md`](datadog/README.md), the **source of truth
for custom metrics and dashboard specs**.

Behind those dashboards: the backend logs structured `equip.metric:`
lines, the log drain ships them, and the **'Equip — drain metric
parsing'** log pipeline parses them into the **18 `equip.*` log-based
distribution metrics**. The `main` index also carries **3 exclusion
filters** (translation-worker-tick INFO noise, the `equip.metric` lines
themselves, and lambda `START`/`END`/`REPORT` lines) to keep ingest
under the daily cap. Log-based metrics are generated **before** index
exclusion, so excluding the `equip.metric` lines from the index does
not affect the metrics.

## How to debug a production issue

### "Something is broken right now"

1. **Check synthetics first.** Open the [Equip backend dashboard](https://app.us5.datadoghq.com/dashboard/x7b-cua-zrm)
   and scan the synthetic status widgets. If any of the three is red,
   the failure mode is one of:
   - Backend down → check Vercel deployment status (`vercel inspect` or
     dashboard), look at the most recent build log.
   - Database down → query Supabase status; admin can hit
     `GET /health/db` for a 503 / 200 confirmation.
   - DNS / cert issue → `dig equipbible.com`, check Vercel domains page.

2. **Look at error spikes.** Datadog Logs query:
   `service:equip-backend status:error` over the last hour. A burst
   that started "now" almost always names the cause in the first 1-2
   stack frames (`logger.exception` writes them).

3. **Pivot via request id.** If the user reported a specific failing
   action, ask for `X-Request-Id`. Search Datadog Logs:
   `@vercel.request_id:<id>`. You'll get every WARNING+ line emitted
   during that request.

4. **Replay the session.** In RUM, search by user email or by error
   message; the Session Replay timeline shows clicks, scrolls, network
   calls. Inputs are masked (`mask-user-input`) so quiz answers and
   passwords don't leak into the recording, but the surrounding UI is
   visible.

### "I want to understand a slow page"

1. RUM → Performance → filter by `@view.name:<route>`. Look at LCP, INP,
   CLS percentiles. The monitor on LCP > 4 s fires at the dashboard
   average; individual long-tail views can be much slower.
2. Long-task events are tracked (`trackLongTasks: true`) -- the action
   stream in RUM marks any > 50 ms main-thread block.

### "Resend didn't send my email"

1. Check monitor `19761387` ("send-email: delivery / function errors").
2. Datadog Logs: `service:send-email status:error` -- the Edge Function
   logs the Resend error body when a send fails.
3. Manual check from PowerShell (see [resend-equip.md](../README.md)
   recipe section) -- list the last 20 sends and look at `last_event`.

## What's NOT wired up (known gaps)

These are deliberate omissions; revisit when traffic or budget grows.

- **No backend APM tracer.** `ddtrace.auto` would auto-instrument
  FastAPI / SQLAlchemy / httpx, but on Vercel serverless there is no
  local agent to ship traces to -- it would need an HTTPS trace
  forwarder. Skip until log shipping proves load is fine.
- **No SLOs.** Cheap to add once we have ~30 days of synthetic data.
- **No Resend webhooks.** Resend supports `email.sent`, `email.delivered`,
  `email.bounced`, `email.complained` webhooks; we're not subscribed.
  When delivery starts mattering, wire these to a tiny Edge Function
  that re-shapes the payload and POSTs to the Datadog HTTP logs intake.
  (Resend cannot post directly to DD because we can't add the
  `DD-API-KEY` header on Resend webhooks.)
- **No `/health/ready` endpoint.** `/health` only verifies the FastAPI
  process is up; it does not ping the DB. Vercel serverless functions
  rarely return "warm but DB down" (the DB call is in the same cold-start
  path), so the extra check is low-value today. `GET /health/db` exists
  but is admin-gated. Add `/health/ready` if we ever hit a real outage
  where the serverless function answers but DB writes are timing out.
- **No alert routing beyond email.** All monitors notify
  `arvavitcorp@gmail.com`. Add SMS / Slack / PagerDuty if the
  on-call rotation grows past one person.
- **No daily Resend send-count or bounce-rate monitor.** Resend Free
  tier is 3 000 / month; current volume is < 5. Revisit at ~1 000 /
  month when accidental loops or compromised templates become plausible.

## Source-controlled monitor JSONs

Per project policy we never auto-create Datadog monitors from agent
sessions, but we DO ship importable JSON specs under
[`docs/datadog/monitors/`](datadog/monitors/) so the next regression
has a paging gate ready. See that directory's README for the import
flow (Datadog UI → Monitors → New → Import) and the editing
convention (tweak in UI, re-export JSON to git in the same PR).

Shipped JSON specs (each one Vadym imports manually):

| File | What it catches | Priority |
|---|---|---|
| `backend-5xx-rate.json` | Backend 5xx rate > 5% over 10 min | P1 |
| `backend-unhandled-exception-rate.json` | `equip.errors.unhandled_total` count > 10 / 10 min — distinct from 5xx-rate (this catches uncategorised exceptions, the "a real bug just shipped" signal) | P1 |
| `translation-worker-401-rate.json` | Cron is firing but auth fails (≥ 5 401s in 15 min) | P2 |
| `worker-cron-silent.json` | Cron is NOT firing at all (≥ 15 min with no log line) | P2 |
| `translation-queue-backlog.json` | `equip.translation.queue_depth > 50` for > 1 h | P3 |

Still useful to add manually when Vadym has time:

1. **Backend P95 latency** — `avg:trace.fastapi.request.duration{service:equip-backend}.percentile(95) > 1500 ms over 15 min`. Requires APM enabled first; skip until then.
2. **Datadog daily ingest** — forecast monitor on the `main` index warning at 85 % of the 10 000 / day cap, alerting at 95 %.
3. **Synthetic latency drift** — on top of the existing pass/fail synthetic monitors, warn if the median response time on `/health` exceeds 2 s for 30 min. Cold-start latency creep is the first visible sign of Vercel runtime regression.
4. **Resend bounce rate** — requires Resend webhooks (see gap above). Alert at ≥ 5 % bounces over a 6 h rolling window.

To enable any of these, see the `Memory/datadog-equip.md` "Check
Datadog" PowerShell recipe and adapt the monitor JSON; do not let the
agent create them without explicit approval.

## "Check Datadog" -- one-shot status snapshot

When you want a quick "is everything fine?" answer, run the recipe
from `Memory/datadog-equip.md` (PowerShell). It prints:

- Status of all 3 synthetics (`live` vs failing).
- Any firing monitors.
- RUM event totals for the last hour (views, errors, rage clicks).
- A link to the Equip overview dashboard.
