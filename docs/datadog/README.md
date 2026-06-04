# Datadog dashboards

This directory holds the JSON specs for Datadog dashboards Equip
keeps in source control. Each spec corresponds to one dashboard
that's importable via the Datadog UI:

| Spec | Purpose |
|---|---|
| `teacher-load-dashboard.json` | Per-teacher grading-queue depth, response time, active courses, enrollment counts. |
| `course-engagement-dashboard.json` | Per-course DAU, completion rate, time-to-first-drop-off, top drop-off chapters, locale split, average rating. |

## Why JSON, not Terraform

Equip's Datadog footprint is small enough that hand-importing two
dashboards via the UI is faster than standing up a Terraform
provider. When the dashboard count grows past ~5 or starts changing
weekly, it's worth converting these to
`datadog_dashboard_json` resources and managing through TF.

## Importing a dashboard

1. Datadog UI → `Dashboards` → `New Dashboard`.
2. Click the `Configure` (gear) icon → `Import dashboard JSON`.
3. Paste the file's contents.
4. Set sharing: `Teamwide` for the Equip team.

After import, the dashboard exists by ID. If you tweak it in the
UI, export the updated JSON and paste it back into the file in
this directory in the SAME PR — keeping source-of-truth out of
sync with prod is the fastest way for dashboards to silently rot.

## Required metrics

Both dashboards reference custom metrics with the `equip.*` namespace.
They're emitted via **log-based metrics** — structured INFO lines
under the `equip.metric` logger that Datadog parses into time series.
See `app/core/metrics.py` for the emitter contract.

Live emission today (sites tagged with the route file that wires them):

* **`equip.grading.graded_total`** + **`equip.grading.time_to_grade.p50`**
  — `app/api/v1/quizzes/grading.py` fires on the
  `pending → graded` transition (guarded against re-grade
  double-count).
* **`equip.activity.requests_total`** + **`equip.activity.duration_ms`**
  — the request-logging middleware in `app/main.py` tags every
  request with `course_id`, `locale`, `status_code`.
* **`equip.completion.course_avg_pct`** — `app/services/course_service/
  _enrollment.py::sync_enrollment_progress` emits a gauge on every
  progress recompute.
* **`equip.engagement.chapter_completed_total`** — emitted by all
  three chapter-completion paths (teacher-mark / quiz-pass /
  assignment-submit), tagged with `completion_type`, idempotent on
  no-op re-completion.
* **`equip.enrollments.created_total`** — `app/services/
  course_service/_enrollment.py::enroll_user_in_course` emits once
  per *new* row (idempotent on re-enroll).
* **`equip.reviews.rating_latest`** — `app/api/v1/reviews.py` emits
  per (user, course) on review create/update; the dashboard takes
  `avg` to produce the rating tile.
* **`equip.errors.unhandled_total`** — the global FastAPI exception
  handler in `app/main.py` fires this counter for every uncategorised
  exception (i.e. not IntegrityError → 409 and not SQLAlchemyError →
  503; those have hand-built handlers). Tagged with `method`,
  `path_prefix` (first 4 url segments), and `exception_type` (class
  name, never the message — message could carry PII). Drives the
  P1 `backend-unhandled-exception-rate` monitor.
* **`equip.translation.queue_depth`** +
  **`equip.translation.queue_processing`** +
  **`equip.translation.queue_failed_permanent`** — `app/api/v1/
  internal_translation_worker.py::_emit_queue_gauges` fires three
  per-status gauges on every cron tick. Drives the Course
  Engagement dashboard's *Translation queue health* group and the
  `translation-queue-backlog` monitor.
* **`equip.translation.duration_ms`** — `app/api/v1/
  internal_translation_worker.py::_emit_translation_duration` times
  each `translate_course_content` run. Tagged with
  `outcome={done,failed}` so the dashboard can split the latency
  curve by success vs failure — a sustained gap usually means the
  failure path is timing out on an upstream call.
* **`equip.gemini.calls_total`** + **`equip.gemini.tokens_input_total`**
  + **`equip.gemini.tokens_output_total`** —
  `app/services/translation/gemini.py::translate` emits per Gemini
  API call. Tagged with `model` (so a future flash → pro migration
  keeps cost curves separable) and `outcome={success,retry,fatal}`.
  `tokens_*_total` use the token count as the metric VALUE so
  `sum:` over the window equals cumulative token spend → multiply
  by Gemini's $/million rate to get $-burn.
* **`equip.daily_challenge.attempt_total`** — `app/api/v1/
  daily_challenge.py::submit_attempt` fires per **new** attempt
  (`is_new_attempt=True`); idempotent re-submits return 201 but
  do NOT increment. Tagged with `challenge_date` + `is_correct`
  so the dashboard can chart attempts-per-day and derive a correct-
  rate without a second metric.

Drop-off rate is computed in the dashboard query as:

```
100 * (1 - (chapter_completed_total / enrollments.created_total))
```

over the chosen window — no separate emitter required.

Still TODO (panels render "no data" gracefully):

* `equip.questions.*` — course Q&A surface when it lands.
* `equip.completion.chapter_avg_pct` — per-chapter aggregate.
* `equip.engagement.first_dropoff.p50` — needs session-window
  computation; deferred until session_id tagging lands.

## See also

- `docs/OBSERVABILITY.md` — Datadog setup, log forwarder config,
  monitor inventory.
- `Memory/datadog-equip.md` — current monitor IDs (in the private
  ops repo).
