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
| Backend INFO logs + edge events | Vercel Log Drain `drn_anVGfaiUT6UPtBCo` ("Datadog us5", `deliveryFormat: json`) | json stream from Vercel → Datadog intake (the intake URL carries `ddtags` such as `env:production`); covers both `equip-frontend` and `equip-backend` projects. Sources: `static`, `lambda`, `edge`, `external`, `firewall` — **not** `build`, dropped 2026-09-15, see the ingest cap below. Replaced the original ndjson drain on 2026-06-11 (Datadog intake answered 415 to ndjson payloads) and the `build`-carrying drain on 2026-09-15. |
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
Vercel Log Drain drn_anVGfaiUT6UPtBCo                       ↓
       ↓                                          Datadog index "main" (15-day retention)
Datadog index "main"                                        ↓
                                              tagged: env, service, version (git SHA[:7]),
                                                      vercel_region, vercel.request_id
```

The two paths are **complementary, not duplicate**. The in-process
handler ships only WARNING and above, with structured fields and the
per-request `vercel.request_id` correlation key. The log drain ships
what Vercel sees at runtime (INFO request lines, edge events, firewall
events) but without the per-record tags. Build output is **not** shipped
-- see below.

Both end up in the same `main` index, so a Datadog log query that
filters by `service:equip-backend` gets both. The daily ingest cap is
**10 000 events / day** with a warning at 80 %.

#### The cap is a real ceiling, not a theoretical one

It was written as a defensive control against a logging-loop bug. It is
not: on 2026-09-14 a review found the cap had been touched on 8 of the
previous 30 days and **fully consumed three times** (20.08, 31.08,
07.09). On 07.09 indexing stopped at 19:13 UTC and nothing was recorded
for the rest of the day -- almost five hours that read, in a dashboard,
exactly like a quiet evening.

Two sources accounted for nearly all of it:

- **Build stdout** (`@source:build`) -- the per-chunk listing `vite build`
  prints, plus sourcemap-upload banners. Zero on a quiet day, 2 000-7 000
  on a deploy day; 70 % of the whole cap on 07.09. No diagnostic value
  once the deploy is green: the same output is in the Vercel build log.
- **Edge access logs** -- one line per HTTP request, including static
  assets and Datadog's own synthetics. ~3 200/day, peaking at 7 490.

`build` was removed from the drain's sources on 2026-09-15, which leaves
the busiest observed day inside the cap. Edge access logs were kept
deliberately: they are how a 404 on a vanished asset chunk becomes
visible (see `frontend/vercel.json`).

A hypothesis worth recording as **disproved**: WordPress scanner traffic
(`/xmlrpc.php`, `/?rest_route=`) is under 0.3 % of the cap. Do not spend
an exclusion filter on it.

If the cap is hit again, the honest fix is to sample successful static
hits -- not to raise the number, which just pays to index noise.

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
| 19728793 | RUM alert | p75 LCP > 4 s over 1 h (warn 3.5 s) -- retuned in the UI 2026-06-13, robust to a single cold-start view. LCP is in **nanoseconds** in RUM events -- never use ms thresholds | warn |
| 19730778 | Log alert | ≥ 10 ERROR / CRITICAL backend log lines in 10 min (warn at 6), scoped `source:python` | `priority:2` |
| 19730779 | Log alert | ≥ 20 WARNING backend log lines in 15 min (warn at 10) -- usually IntegrityError noise. Scoped `source:python` | warn |
| 20393855 | Log alert | ≥ 3 error logs from `service:send-email status:error` in 15 min | `priority:2` |
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

1. Check monitor `20393855` (`send-email-failures.json` -- errors from
   `service:send-email`).
2. Datadog Logs: `service:send-email status:error` -- the Edge Function
   logs the Resend error body when a send fails.
3. Manual check against the Resend API (`GET https://api.resend.com/emails`
   with the key from 1Password via `op run`) -- list the last 20 sends and
   look at `last_event`.

## Two noisy signals that were investigated and are not problems

Written down because both look alarming in a log query, and both cost a
day to rule out. Do not re-derive this.

### `Warp server error: Thread killed by timeout manager` (PostgREST)

79 occurrences over 09-08…09-14, rising to 34 on 09-12 and fading after.
The obvious theory — a slow query against `content_versions` (28 950 rows,
25 204 sequential scans) hanging the REST API — **is wrong**:

- Each event was matched against `/rest/v1/*` in `edge_logs` within ±2 s.
  **1 of 79 matched**, and that one was a healthy `GET /profiles`, 200 in
  342 ms. The other 78 correspond to no logged request at all.
- Across six days: **zero 5xx** on `/rest/v1/*`, exactly one response over
  2 s. Total REST traffic is 48-128 requests/day, nearly all browser
  preflights and Datadog synthetics — the app talks to Postgres through
  the backend and the pooler, not PostgREST.
- `content_versions` already carries 9 indexes, including partial ones
  matching the real access pattern. The batched ORM lookups average
  0.07-28 ms. The sequential scans come from occasional manual
  `text LIKE '%…%'` queries run through the SQL editor as `postgres`.
- Not the same mechanism as `statement_timeout` (3 s anon / 8 s
  authenticated), which surfaces as an HTTP 500 saying "canceling
  statement" and would appear in `edge_logs`.

Warp is PostgREST's internal HTTP server. An error there with no matching
edge request is almost certainly an internal readiness probe against the
PostgREST pod. **No index, no config change.** If it recurs, look at the
pod's health and restart history on the Supabase side, not at SQL.

### `database "template1" has a collation version mismatch`

~10 000 warnings a week — over 99 % of all Postgres WARNING volume — at
roughly one a minute. `template1` reports collation version 153.120 while
the OS provides 153.121, after a glibc upgrade underneath the instance.

The application database is **not** affected (153.121 both sides), and
`template1` holds no data: it is the template new databases are cloned
from. So this is pure log noise, not a correctness risk — but it drowns
the Postgres WARNING stream, which is why the stream is worth nothing
today.

Fixed by one statement, which needs an operator (it alters a shared
database, so agents are blocked from running it):

```sql
ALTER DATABASE template1 REFRESH COLLATION VERSION;
```

Confirm with:

```sql
SELECT datname, datcollversion, pg_database_collation_actual_version(oid)
FROM pg_database WHERE datname = 'template1';
```

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
sessions, but we DO ship JSON specs under
[`docs/datadog/monitors/`](datadog/monitors/) so the next regression
has a paging gate ready. That directory's README holds the current
inventory -- it is the one place the list lives, because a second copy
here went stale the moment five specs were retired in #777 and this
table went on advertising them for two months.

Applying them is one command, run deliberately by a human with a
write-scoped key:

```
cd backend
python scripts/apply_datadog_monitors.py            # dry run
python scripts/apply_datadog_monitors.py --apply    # writes
```

The editing convention is unchanged: tweak in the UI, re-export the
JSON to git in the same PR. Dry-run before applying -- the script
pushes files to Datadog and never pulls a UI edit back, so an
un-exported retune would be silently reverted. The application key
needs `monitors_read` + `monitors_write` and nothing else; see
[`docs/datadog/README.md`](datadog/README.md).

Still useful to add manually when Vadym has time:

1. **Backend P95 latency** — `avg:trace.fastapi.request.duration{service:equip-backend}.percentile(95) > 1500 ms over 15 min`. Requires APM enabled first; skip until then.
2. **Datadog daily ingest** — forecast monitor on the `main` index warning at 85 % of the 10 000 / day cap, alerting at 95 %.
3. **Synthetic latency drift** — on top of the existing pass/fail synthetic monitors, warn if the median response time on `/health` exceeds 2 s for 30 min. Cold-start latency creep is the first visible sign of Vercel runtime regression.
4. **Resend bounce rate** — requires Resend webhooks (see gap above). Alert at ≥ 5 % bounces over a 6 h rolling window.

To enable any of these, adapt one of the monitor JSONs under
`docs/datadog/monitors/` and apply it with the script above; do not let
the agent create them without explicit approval.

## "Check Datadog" -- one-shot status snapshot

When you want a quick "is everything fine?" answer, run the maintainer's
"Check Datadog" recipe (kept in private notes, not in this repository;
it is a handful of `GET /api/v1/synthetics/tests` and
`GET /api/v1/monitor` calls with the read-only application key). It
prints:

- Status of all 3 synthetics (`live` vs failing).
- Any firing monitors.
- RUM event totals for the last hour (views, errors, rage clicks).
- A link to the Equip overview dashboard.
