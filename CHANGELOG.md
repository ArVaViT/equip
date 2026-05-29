# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project does not yet follow [Semantic Versioning](https://semver.org/) but
will adopt it starting with v1.0.0.

## [Unreleased]

### Added — bilingual content (RU ↔ EN)

- **Interface i18n** — full UI in Russian and English via `react-i18next`,
  with native plural forms (`_one` / `_few` / `_many` / `_other`) for
  Russian. Auth flows, teacher dashboard, calendar, certificates, and
  notifications all translated; locale-aware date formatting.
- **Course content translation pipeline** — every teacher-authored field
  (course title/description, module, chapter title, chapter_block content,
  quiz / question / option, assignment, announcement, course_event,
  cohort name) is auto-translated to the other locale via the Google
  Gemini API. Results stored in `public.content_versions` (the Phase 5e
  series replaced the earlier `content_translations` cache table with a
  polymorphic versioned store keyed on `(entity_type, entity_id, field,
  locale)`); `source_hash` short-circuits unchanged text.
- **Bidirectional, no "main" language** — a course's `source_locale`
  derives from the teacher's `preferred_locale` at create time. Author
  in EN, RU students get RU. Author in RU, EN students get EN. No UI
  dropdown; no default forced on the user.
- **Canonical Bible quote substitution** — `app/services/bible/`
  detects `<blockquote>` + Bible reference pairs (Russian or English),
  swaps the verse with a sentinel marker, sends only the prose to
  Gemini, then restores the canonical target-locale text from the
  bundled KJV (1769) / Synodal (1876) JSON. Bible quotes always read
  as the published canonical text in the student's locale, never a
  paraphrase.

### Added — translation infrastructure / safety

- **Translation registry** — single source of truth for translatable
  entities (`backend/app/services/translation/registry.py`). Adding a
  new entity is a single registry entry plus a migration; the tree
  walker, resolve helpers, write hooks, and Postgres CHECK constraint
  are all driven from it.
- **Per-entity write hook** — `reconcile_entity_if_course_published`
  fires after each per-entity mutation (announcement create, cohort
  update, etc.) so fresh content is translated immediately; idempotent
  via `source_hash`.
- **CI guard** — `tests/test_translation_coverage.py` introspects every
  FastAPI route and enforces (a) GETs that return translatable schemas
  must accept `Accept-Language`, (b) writes that mutate translatable
  entities must reference one of the canonical hooks. Catches the
  endpoint regressions that produced two manual backfills earlier in
  the cycle.
- **Provider hardening** — Gemini provider now rejects truncated
  responses (`finishReason ≠ STOP`), rebuilds on API-key rotation,
  splits HTTP timeouts (connect/read/write/pool), uses `SecretStr`
  for the key, and recovers concurrent inserts via savepoint +
  `IntegrityError`. Default model is `gemini-2.5-flash-lite` (no
  thinking-token consumption — full Flash silently truncated long
  blocks).

### Added — translation queue (Phase 5av-5ax + 5ba)

- **`translation_jobs` queue table.** Publishing a course used to fan
  out 100 Gemini calls synchronously in the POST handler; Vercel's
  serverless function budget made this fragile. The queue moves it
  out-of-band — publish enqueues ONE row (~1ms) instead of running
  `translate_course_content` inline.
- **Cron-driven worker.** Vercel Cron hits
  `POST /api/v1/internal/translation-worker` every minute with
  `Authorization: Bearer <TRANSLATION_WORKER_SECRET>`. Worker claims one
  job via `SELECT ... FOR UPDATE SKIP LOCKED` (concurrent crons never
  grab the same row), runs the orchestrator, marks done / failed /
  failed_permanent (5-attempt budget), returns a small JSON payload the
  driver logs.
- **Operator surfaces.** `GET /api/v1/admin/translations/queue-status`
  returns per-state counts + oldest-queued age + stuck-job summary.
  `POST /api/v1/admin/translations/reset-by-ids` and `/reset-by-entity`
  unstick `failed_permanent` rows when an operator needs to retry.
- **RLS hardening (Phase 5bo).** The queue table now has RLS enabled
  with a blanket-deny policy for `authenticated` + `anon` — service_role
  bypasses RLS so the cron worker is unaffected. Closes the
  "RLS by default" architectural invariant gap.

### Added — typed error envelope (Phase 5ay-5bg)

- **Structured error responses.** Every backend route raises
  `equip_error(code, status_code, message, context)` instead of
  `HTTPException`. Detail shape is now:

  ```json
  {
    "detail": {
      "code": "course.enrolment_closed",
      "message": "Cohort enrollment period has ended",
      "context": { "cohort_id": "...", "enrollment_end": "..." }
    }
  }
  ```

  ~140 raise sites migrated across every route module in `app/api/v1/`.
- **Typed ErrorCode enum.** Backend `StrEnum` in `app/core/errors.py`
  (`auth.required`, `auth.forbidden`, `resource.not_found`,
  `course.not_published`, `course.already_enrolled`,
  `course.enrolment_closed`, `translation.disabled`,
  `translation.worker_unauthorized`,
  `translation.worker_unconfigured`, `quiz.not_open`,
  `quiz.attempts_exhausted`, `validation.failed`). Frontend mirror in
  `frontend/src/lib/errorCode.ts` keeps the union typed end-to-end.
- **Frontend `getErrorCode(err)`** returns the typed `ErrorCode` from
  an Axios error, or `null` for legacy string-detail responses.
  Backwards-compatible — routes still emitting the old shape work
  unchanged.

### Added — defensive infrastructure

- **OpenAPI route snapshot test (Phase 5at).** CI now fails when the
  set of routes / methods / parameters / responses changes without an
  intentional snapshot update. Catches contract drift before it
  reaches the frontend.
- **Admin "reset failed-permanent" endpoints (Phase 5au).** Operator
  can unstick translation-pipeline rows that hit the 5-attempt budget
  due to a transient outage (vs a true permanent failure like a safety
  filter).
- **ContentVersionStatus StrEnum (Phase 5ar).** The `status` column on
  `content_versions` now flows through a typed enum end-to-end
  (Postgres CHECK ↔ SQLAlchemy ORM ↔ Pydantic schema ↔ frontend
  type).
- **Chapter column / cv invariant test (Phase 5bm).** Unlike Course
  and Module, `chapters.title` deliberately keeps a real column dual-
  written to the source-locale cv row in the same transaction.
  `tests/test_chapter_column_cv_invariant.py` pins this invariant so a
  future refactor that forgets one side breaks CI. Docstring on the
  `Chapter` model documents the architectural decision.
- **Defensive pagination caps (Phase 5bn).** `GET /calendar/events`
  gained a `limit: Query(1000, ge=1, le=2000)` cap (oldest items drop
  off first — upcoming-events shape for the calendar UI) so a power
  user enrolled in 10+ courses with years of history can't blow the
  Vercel function budget. `GET /cohorts` (admin) gained standard
  `skip` + `limit: Query(100, ge=1, le=500)` pagination.

### Added — frontend refactors

- **Header.tsx component split (Phase 5bb).** The 322-line monolith
  became 6 focused files (composer + 5 sub-components: NavLink,
  ProfileMenu, NotificationBell wrapper, MobileSheet, role-aware nav).
  No behaviour changes; refactor only.
- **Localized fallback labels in shared UI primitives (Phase 5bj).**
  The `ConfirmProvider` / `PromptProvider` in `alert-dialog.tsx` now
  use `t("common.cancel")` / `t("common.confirm")` / `t("common.ok")`
  for fallback labels. `ErrorState` default title localized.
  `PageSpinner` default `aria-label` localized.

### Changed

- **Default Bible-quote prompt rule reframed** — the LLM is no longer
  asked to "preserve scripture verbatim" as a primary mechanism; the
  bible-substitution layer above handles canonical quotes. The prompt
  rule remains as a fallback for paraphrased quotes (similarity below
  0.80) so the prior behaviour is preserved for content the
  substitution layer can't confidently match.
- **Cohort / certificate / prerequisite views** now overlay
  teacher-authored text into the requested locale (course title on a
  certificate, cohort name in the student-facing list, prerequisite
  course title in the catalog).
- **Analytics endpoint now respects Accept-Language (Phase 5bi).**
  `GET /analytics/course/{course_id}` declared `Vary: Accept-Language`
  but called `populate_spine_texts(db, [course])` without a
  display_locale, so Russian teachers always saw the source-locale
  title regardless of their UI preference. Fixed by threading
  `Accept-Language` through; `populate_spine_texts` gained an optional
  `display_locale=None` kwarg that preserves source-locale behaviour
  for all other callers by default.
- **`Certificate.archived_course_title` archive (Phase 5bi).**
  `permanently_delete_course` was reading `course.title` (a runtime
  attribute that the caller may not have hydrated) when stamping the
  archive snapshot onto certs before the FK nulls. Replaced with a
  direct `fetch_cv_entity_texts_with_fallback` call so the service is
  self-sufficient and certs always end up with a readable archived
  name.

### Fixed

- **Audit-log titles after course delete (Phase 5bi).** `remove_course`
  + `permanently_remove_course` stamped `course.title` into the audit
  row without first calling `populate_spine_texts`, leaving the audit
  log with `None` (or an `AttributeError` depending on session state).
  Both routes now hydrate before logging.
- **Hardcoded English fallbacks in shared UI primitives (Phase 5bj).**
  Five strings localized: 4× `alert-dialog.tsx` fallback labels and
  `ErrorState` default title.

## [0.1.0] - 2026-04-24

First public release as an open-source project. Everything below was built
over the preceding months and is now available under the MIT license.

### Core platform

- **Role-based access control** — admin, teacher, and student roles with
  fine-grained API and UI guards.
- **Course authoring** — courses, modules, chapters, and rich content blocks
  via a TipTap editor (text, images, YouTube embeds, callouts, audio).
- **Quiz system** — `multiple_choice`, `true_false`, `short_answer`, and
  `essay` question types with per-quiz attempt limits and teacher-granted
  extra attempts.
- **Assignments** — submission, teacher grading queue, and automatic chapter
  completion on submission.
- **Enrollment and progress** — student enrollment, chapter-level progress
  tracking, and module/course completion.
- **Certificates** — automatic generation with teacher approval flow.
- **Cohorts** — group students for batch management and analytics.
- **Announcements** — admin/teacher broadcast system with banner display.
- **Calendar** — course and cohort event management.
- **Notifications** — in-app notification bell with read/unread state.
- **Teacher tools** — gradebook, analytics dashboard, pending-answers queue
  for essay/short-answer grading.
- **Admin tools** — user management, bulk operations, CSV export, soft
  delete, course cloning, full-text search.

### Design and UX

- **Design system** — editorial aesthetic (Fraunces + Inter), OKLCH semantic
  tokens, dark/light theme, responsive down to 360px.
- **UI primitives** — shadcn/ui + Radix (AlertDialog, DropdownMenu, Popover,
  Tooltip, Sheet, Tabs, Accordion, ScrollArea, Avatar, Badge).
- **Patterns** — InlineEdit, InlineEditCover, PageHeader, EmptyState,
  ErrorState, loading skeletons, error boundaries.
- **Inline editing** — course and module headers edit in place (no modals).

### Infrastructure

- **Backend** — Python 3.12, FastAPI, SQLAlchemy 2.0 (Mapped style),
  Pydantic 2, deployed as Vercel serverless functions.
- **Frontend** — React 18, TypeScript, Vite 8, Tailwind CSS 3, deployed as
  Vercel static site.
- **Database** — PostgreSQL via Supabase with RLS on every table; migrations
  managed via Supabase CLI.
- **Auth** — Supabase Auth (Google OAuth + email/password), JWTs verified
  server-side.
- **CI/CD** — GitHub Actions (lint, typecheck, test, Postgres schema smoke,
  `npm audit`, `pip-audit`), Dependabot for weekly dependency updates.
- **Monitoring** — Datadog RUM + Session Replay (opt-in).

### Security

- RLS enabled on all tables with per-role policies.
- Server-side HTML sanitization on content create/update.
- CORS locked to known origins with regex for Vercel previews.
- Pydantic `max_length` on all user-facing string fields.
- `pip-audit` and `npm audit` in CI.
- Production API docs disabled.
- `FOR UPDATE` + `IntegrityError` handling for race conditions.

### Content

- "Deyaniya Apostolov" (Acts of the Apostles) — 4 modules, ~5 hours,
  100-question final exam + per-module quizzes.
- "Bibliya kak istoricheskiy dokument" (Bible as a Historical Document) —
  mini-course with Bible Project video chapters and module quiz.

[Unreleased]: https://github.com/ArVaViT/equip/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ArVaViT/equip/releases/tag/v0.1.0
