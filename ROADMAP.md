# Roadmap

This document outlines the planned direction for Bible School LMS. It is a
living document — priorities may shift based on community feedback and
contributor interest.

Have an idea? Open a
[feature request](https://github.com/ArVaViT/biblie-school/issues/new?template=feature_request.yml)
or start a [discussion](https://github.com/ArVaViT/biblie-school/discussions).

## Legend

| Status | Meaning |
|--------|---------|
| :white_check_mark: Done | Shipped and available |
| :construction: In progress | Actively being worked on |
| :bulb: Planned | Accepted, not yet started |
| :thought_balloon: Exploring | Under consideration |

---

## v0.1 — Foundation (current)

:white_check_mark: Core LMS (courses, modules, chapters, blocks, quizzes,
assignments, certificates, enrollment, progress)

:white_check_mark: Role-based access (admin, teacher, student)

:white_check_mark: Design system (editorial aesthetic, dark/light theme,
responsive)

:white_check_mark: CI/CD (GitHub Actions, Dependabot, Vercel auto-deploy)

:white_check_mark: Open-source community health files (LICENSE, CoC,
CONTRIBUTING, SECURITY, templates)

---

## v0.2 — Quality and polish

:construction: **Visual overhaul v2** — Tailwind v4, shadcn CSS-first config,
OKLCH tokens refresh, ~10 implementation waves (design direction documented
internally).

:bulb: **Accessibility audit** — WCAG 2.1 AA compliance, screen reader
testing, keyboard navigation for all interactive elements.

:white_check_mark: **Bilingual content (RU↔EN)** — `react-i18next` for
the UI; Gemini-backed translation pipeline for all teacher-authored
fields (registry-driven, cached per source hash); canonical KJV /
Synodal substitution for `<blockquote>` Bible quotes; CI guard
prevents endpoint regressions. See the [Unreleased] entry in the
[CHANGELOG](CHANGELOG.md) for the full list of shipped pieces.

:bulb: **Ukrainian (UK) as a third locale** — extending the existing
RU/EN pipeline to UK is a registry change (locales tuple, `language_names`
prompt map, optional UK Bible) plus translation runs; deferred until
there's confirmed UK demand from the community.

:bulb: **Comprehensive test coverage** — push backend above 95%, add
Playwright E2E tests for critical student and teacher flows.

---

## v0.3 — Teacher experience

:bulb: **Bulk grading** — select multiple essay/short-answer submissions and
grade them in a batch view.

:bulb: **Rubric builder** — define grading rubrics per assignment/quiz and
apply them consistently.

:bulb: **Discussion forums** — threaded per-chapter discussions for student
Q&A (teacher-moderated).

:bulb: **Attendance tracking** — optional per-cohort attendance records for
in-person or hybrid programs.

---

## v0.4 — Student experience

:bulb: **Offline reading** — PWA with service worker caching for chapter
content (critical for areas with unreliable internet).

:bulb: **Mobile app** — React Native or Capacitor wrapper for iOS/Android.

:bulb: **Gamification** — optional streaks, badges, and leaderboards to
encourage daily study habits.

:bulb: **Student portfolio** — collect completed assignments and certificates
into a shareable profile page.

---

## v0.5 — Platform and scale

:thought_balloon: **Multi-tenancy** — allow multiple independent Bible
schools to share one deployment with isolated data.

:thought_balloon: **Plugin/extension system** — let nonprofits add custom
block types, grading logic, or integrations without forking.

:thought_balloon: **API v2** — GraphQL or tRPC for more efficient data
fetching as the feature set grows.

:thought_balloon: **Self-hosted installer** — one-command Docker Compose
setup for organizations that want to run their own instance.

---

## How to contribute to the roadmap

1. **Pick a :bulb: Planned item** and open an issue to discuss your approach.
2. **Propose a new item** via a feature request issue — if accepted, it gets
   added here.
3. **Tackle a `good first issue`** — smaller tasks that build toward roadmap
   goals are labeled in the issue tracker.

We especially welcome contributions from:
- **Nonprofit Bible schools** who can share their real-world needs.
- **Designers** who want to improve the student/teacher experience.
- **Translators** who can review and refine the AI-translated RU↔EN
  content (especially the canonical Bible-school terminology).
- **QA testers** who can help us find and fix bugs.
