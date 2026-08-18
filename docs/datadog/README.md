# Datadog dashboards

This directory holds the JSON specs for Datadog dashboards Equip
keeps in source control. Each spec corresponds to one **live**
dashboard (US5 site):

| Spec | Live ID | Purpose |
|---|---|---|
| — (UI-managed) | `shf-kq8-bgf` | Equip overview. |
| — (UI-managed) | `x7b-cua-zrm` | Equip backend. |
| `teacher-load-dashboard.json` | `54n-cn8-nhm` | Per-teacher grading throughput + median time-to-grade, platform enrollment context. |
| `course-engagement-dashboard.json` | `dgr-dh4-n4x` | Per-course active users (RUM), completion rate, drop-off, translation queue, locale split, average rating. |

## Why JSON, not Terraform

Equip's Datadog footprint is small enough that hand-importing two
dashboards via the UI is faster than standing up a Terraform
provider. When the dashboard count grows past ~5 or starts changing
weekly, it's worth converting these to
`datadog_dashboard_json` resources and managing through TF.

## Importing a dashboard

Via UI:

1. Datadog UI → `Dashboards` → `New Dashboard`.
2. Click the `Configure` (gear) icon → `Import dashboard JSON`.
3. Paste the file's contents.
4. Set sharing: `Teamwide` for the Equip team.

Via API: `POST https://api.us5.datadoghq.com/api/v1/dashboard` with
`DD-API-KEY` / `DD-APPLICATION-KEY` headers and the file body
(strip any top-level `id` / `url` / `created_at` / `author_handle`
fields first — POST rejects them).

After import, the dashboard exists by ID — record it in the table
above. If you tweak it in the UI, export the updated JSON and paste
it back into the file in this directory in the SAME PR — keeping
source-of-truth out of sync with prod is the fastest way for
dashboards to silently rot.

## How the metrics work

All `equip.*` custom metrics are **log-based distribution metrics**:
the backend logs structured `equip.metric:` lines (see
`app/core/metrics.py` for the emitter contract), the Vercel log
drain ships them to Datadog, and the log pipeline **'Equip — drain
metric parsing'** parses them into generated metrics
(type: distribution).

Consequences for queries:

* `avg:` / `max:` / `sum:` query shapes work on every metric;
  counters take `.as_count()`.
* Percentile queries (`p50:`, `p95:`, …) work ONLY where noted below.
* There is **no `env` tag** — Equip runs a single prod env, and the
  backend skips non-main builds, so dashboards don't carry an `env`
  template variable. (RUM data does have `env`, but the RUM widgets
  here don't need it.)
* `teacher_id` exists ONLY on the two grading metrics — on the
  Teacher Load dashboard, the `$teacher_id` template variable
  affects the Grading group only.

## Metrics that exist today (2026-06-11)

| Metric | Tags | Percentiles | Emitter |
|---|---|---|---|
| `equip.activity.requests_total` | `locale`, `course_id`, `status_code` | — | request-logging middleware, `app/main.py` |
| `equip.activity.duration_ms` | `locale`, `course_id` | yes | request-logging middleware, `app/main.py` |
| `equip.errors.unhandled_total` | `method`, `path_prefix`, `exception_type` | — | global exception handler, `app/main.py`; drives the P1 `backend-unhandled-exception-rate` monitor; `exception_type` is the class name, never the message (PII) |
| `equip.engagement.chapter_completed_total` | `course_id`, `completion_type` | — | all three completion paths (teacher-mark / quiz-pass / assignment-submit), idempotent on re-completion |
| `equip.reviews.rating_latest` | `course_id` | — | `app/api/v1/reviews.py`, gauge per (user, course) on create/update; dashboard takes `avg` |
| `equip.daily_challenge.attempt_total` | `is_correct` | — | `app/api/v1/daily_challenge.py::submit_attempt`, fires per NEW attempt only |
| `equip.grading.graded_total` | `teacher_id` | — | `app/api/v1/quizzes/grading.py` on the `pending → graded` transition (guarded against re-grade double-count) |
| `equip.grading.time_to_grade.p50` | `teacher_id` | yes | same site; submission → grade latency in seconds |
| `equip.youversion.api_calls_total` | `bible_id`, `outcome` | — | `app/services/verse_of_the_day.py::_fetch_passage`; `outcome=not_in_bible` is the version-difference walk-forward case, not a failure |
| `equip.enrollments.created_total` | `course_id`, `cohort_id` | — | `app/services/course_service/_enrollment.py::enroll_user_in_course`, once per NEW row |
| `equip.completion.course_avg_pct` | `course_id` | — | `..._enrollment.py::sync_enrollment_progress`, gauge on every progress recompute |
| `equip.translation.queue_depth` / `equip.translation.queue_processing` / `equip.translation.queue_failed_permanent` | (none) | — | `app/api/v1/internal_translation_worker.py::_emit_queue_gauges` on every cron tick; drives the `translation-queue-backlog` monitor |
| `equip.translation.duration_ms` | `outcome` (`done`/`failed`) | yes | `..._emit_translation_duration` times each `translate_course_content` run |
| `equip.gemini.calls_total` | `model`, `outcome` (`success`/`retry`/`fatal`/`transport`) | — | `app/services/translation/gemini.py::translate` per Gemini API call |

Emitted in logs but **no generated-metric rule yet** (logged values
are queryable in Log Explorer, not as metrics):

* `equip.gemini.tokens_input_total` + `equip.gemini.tokens_output_total`
  + `equip.gemini.tokens_thinking_total` —
  `app/services/translation/gemini.py` uses the token count as the
  log value; add a distribution rule on the pipeline if $-burn
  tracking should move from logs to metrics.

  The **thinking** count is the one to watch, and the reason it exists
  as its own series. Those tokens are spent before the model answers,
  never appear in the reply, and are billed as output. Production ran
  81 days on a thinking model at roughly 840 of them per translated
  string — six times the output it actually produced — and nothing
  showed it, because nothing measured it. It is emitted on every
  successful call including as zero, so the chart is a flat line at
  nought rather than an absent series, and a model change that brings
  thinking back is visible the same hour.

  `docs/datadog/monitors/gemini-thinking-tokens-returned.json` and
  `gemini-spend-spike.json` alert on these.

## Derived / replaced panels

* **Active users** (Course Engagement) comes from **RUM**, not a
  custom metric: unique `@usr.id` over `@type:session
  service:equip-frontend`. There is no
  `equip.activity.daily_active_users` metric.
* **Cumulative enrollments** (Teacher Load) is
  `cumsum(sum:equip.enrollments.created_total{*}.as_count())` —
  cumulative over the dashboard window, not an all-time gauge
  (there is no `equip.enrollments.count` point-in-time metric).
* **Grading load** (Teacher Load) is graded **throughput** +
  median time-to-grade — there is no pending-queue depth gauge
  (`equip.grading.pending` does not exist).
* **Drop-off rate** is computed in the dashboard query as
  `100 * (1 - (chapter_completed_total / enrollments.created_total))`
  over the chosen window — no separate emitter required.

Metrics that earlier drafts referenced but that do NOT exist (do not
re-add widgets for these without wiring an emitter + pipeline rule
first): `equip.grading.pending`, `equip.questions.open`,
`equip.questions.response_time.p50`,
`equip.activity.daily_active_users`,
`equip.completion.chapter_avg_pct`,
`equip.engagement.first_dropoff.p50`, `equip.courses.active_7d`,
`equip.enrollments.count`.

The `test_every_dashboard_metric_is_emitted_or_documented` sentinel
(`backend/tests/test_metric_readme_sentinel.py`) enforces both
directions: every emitted metric must appear in this README, and
every metric a dashboard queries must be emitted or documented here.

## See also

- `docs/OBSERVABILITY.md` — Datadog setup, log forwarder config,
  monitor inventory.
- `Memory/datadog-equip.md` — current monitor IDs (in the private
  ops repo).
