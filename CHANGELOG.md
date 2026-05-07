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
  Gemini API. Results cached in `public.content_translations` so
  re-publish is free; `source_hash` short-circuits unchanged text.
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

[Unreleased]: https://github.com/ArVaViT/biblie-school/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ArVaViT/biblie-school/releases/tag/v0.1.0
