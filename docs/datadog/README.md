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
They're emitted by:

* **`equip.grading.*`** — `app/api/v1/grades.py` and the manual-
  grading flow in `app/api/v1/quizzes/grading.py` push a Datadog
  StatsD metric every time a pending item enters or leaves the queue.
* **`equip.questions.*`** — the course Q&A surface (when it lands)
  will emit these; for now the panels render "no data" gracefully.
* **`equip.activity.*`** — the request-logging middleware in
  `app/main.py` tags every request with `course_id` and `locale`
  when available; the DAU metric is derived from unique
  `user_id` per day.
* **`equip.completion.*`** — `app/services/student_progress_service.py`
  updates a per-course/per-chapter completion rate on each
  `mark_chapter_complete` call.
* **`equip.engagement.first_dropoff.*`** — `dropoff_count` is the
  count of enrollments where activity stopped without completion;
  computed by a scheduled Datadog query.

The teacher-load dashboard's grading queue tile + the course-
engagement DAU tile are both live as of this PR; the others need
the metric emission to be wired in subsequent PRs. The dashboards
ship now so we can see the no-data tiles + know which metrics are
still TODO.

## See also

- `docs/OBSERVABILITY.md` — Datadog setup, log forwarder config,
  monitor inventory.
- `Memory/datadog-equip.md` — current monitor IDs (in the private
  ops repo).
