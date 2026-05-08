<p align="center">
  <img src="frontend/public/favicon.svg" width="80" alt="Bible School LMS logo" />
</p>

<h1 align="center">Bible School LMS</h1>

<p align="center">
  A free, open-source learning management system built for Bible schools,
  church ministries, and nonprofit educational programs.
</p>

<p align="center">
  <a href="https://github.com/ArVaViT/biblie-school/blob/main/LICENSE">
    <img src="https://img.shields.io/github/license/ArVaViT/biblie-school?style=flat-square" alt="MIT License" />
  </a>
  <a href="https://github.com/ArVaViT/biblie-school/actions/workflows/backend-ci.yml">
    <img src="https://img.shields.io/github/actions/workflow/status/ArVaViT/biblie-school/backend-ci.yml?label=backend&style=flat-square" alt="Backend CI" />
  </a>
  <a href="https://github.com/ArVaViT/biblie-school/actions/workflows/frontend-ci.yml">
    <img src="https://img.shields.io/github/actions/workflow/status/ArVaViT/biblie-school/frontend-ci.yml?label=frontend&style=flat-square" alt="Frontend CI" />
  </a>
  <a href="https://github.com/ArVaViT/biblie-school/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22">
    <img src="https://img.shields.io/github/issues/ArVaViT/biblie-school/good%20first%20issue?style=flat-square&color=7057ff&label=good%20first%20issues" alt="Good first issues" />
  </a>
</p>

<p align="center">
  <a href="https://biblie-school-frontend.vercel.app">Live demo</a> &middot;
  <a href="ROADMAP.md">Roadmap</a> &middot;
  <a href="CONTRIBUTING.md">Contributing</a> &middot;
  <a href="CHANGELOG.md">Changelog</a>
</p>

---

## Why this project?

Hundreds of small Bible schools, home churches, and missionary training
programs around the world still manage courses on paper, WhatsApp, or
spreadsheets. Commercial LMS platforms are expensive, overkill, or require
technical expertise that volunteer-run organizations simply don't have.

**Bible School LMS** is designed to change that:

- **Free forever** — MIT-licensed, no paywalls, no "premium" tiers.
- **Simple to deploy** — one-click Vercel deploy with a free Supabase
  database. No Docker, no servers to manage.
- **Built for small scale** — optimized for 20-100 students, not enterprise
  pricing models.
- **Contributor-friendly** — clear docs, conventional commits, issue
  templates, and a welcoming community.

---

## Features

| Area | What you get |
|------|-------------|
| **Course authoring** | Courses, modules, chapters, rich content blocks (TipTap editor with images, YouTube, callouts, audio) |
| **Assessments** | Multiple-choice, true/false, short-answer, and essay quizzes with attempt limits and teacher grading |
| **Assignments** | Student submissions, grading queue, automatic chapter completion |
| **Progress tracking** | Per-chapter progress, module/course completion, enrollment management |
| **Certificates** | Auto-generated certificates with teacher approval flow |
| **Teacher tools** | Gradebook, analytics dashboard, cohort management, calendar, announcements |
| **Admin tools** | User management, bulk operations, CSV export, course cloning, soft delete |
| **Design** | Editorial aesthetic, dark/light theme, responsive (360px+), OKLCH semantic tokens |
| **Bilingual content (RU↔EN)** | Auto-translation of all teacher-authored text via Gemini, cached per (entity, field, locale); canonical KJV / Synodal substitution for Bible quotes; symmetric — author writes in their language, students read in theirs |
| **Security** | RLS on every table, server-side HTML sanitization, CORS lockdown, audit pipeline |

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, TipTap, Radix |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic 2 |
| Database | PostgreSQL (Supabase) with Row Level Security |
| Auth | Supabase Auth (Google OAuth + email/password) |
| Storage | Supabase Storage (avatars, course assets, materials) |
| Deploy | Vercel (static frontend + Python serverless backend) |
| CI/CD | GitHub Actions (lint, typecheck, test, audit) + Dependabot |

---

## Quick start

### Prerequisites

- **Node.js** 22.x (`.nvmrc` pins 22.18.0), **npm** >= 10
- **Python** 3.12
- A free [Supabase](https://supabase.com) project (or just run backend
  tests with SQLite — no Supabase needed)

### 1. Clone and install

```bash
git clone https://github.com/<your-username>/biblie-school.git
cd biblie-school

# Frontend
cd frontend && npm ci && cd ..

# Backend
cd backend && pip install -r requirements.txt && cd ..
```

### 2. Configure environment

```bash
cp frontend/.env.example frontend/.env.local   # fill in VITE_* vars
cp backend/.env.example  backend/.env           # fill in Supabase creds
```

See each `.env.example` for a description of every variable.

### 3. Start development

```bash
# Terminal 1 — API
cd backend && uvicorn app.main:app --reload     # http://localhost:8000

# Terminal 2 — SPA
cd frontend && npm run dev                      # http://localhost:5173
```

### 4. Run tests

```bash
cd backend  && python -m pytest tests/    # 396+ tests (SQLite in-memory)
cd frontend && npm run test:run           # Vitest + jsdom
```

---

## Project structure

```
backend/            Python FastAPI application
  app/
    api/v1/         Route modules
    core/           Config, database, auth helpers
    models/         SQLAlchemy ORM models
    schemas/        Pydantic request/response schemas
    services/       Business logic
  tests/            pytest suite

frontend/           React SPA (Vite + TypeScript)
  src/
    components/     UI components (shadcn/ui + custom)
    pages/          Route-level pages
    services/       API client + Supabase helpers
    context/        React contexts (auth, theme)

supabase/
  migrations/       SQL migration files (production schema source of truth)

.github/
  workflows/        CI pipelines
  ISSUE_TEMPLATE/   Bug report and feature request forms
```

---

## Contributing

We welcome contributions of all sizes — from typo fixes to new features.

1. Read [CONTRIBUTING.md](CONTRIBUTING.md) for setup and workflow details.
2. Check [open issues](https://github.com/ArVaViT/biblie-school/issues)
   — look for the `good first issue` label if you're new.
3. See the [ROADMAP](ROADMAP.md) for bigger-picture direction.

**We especially welcome:**
- Nonprofit Bible schools sharing their real-world needs
- Designers improving the student/teacher experience
- Translators reviewing and refining the AI-translated content (the platform is already RU↔EN bilingual; human review of the canonical Bible-school terminology is what would push quality from "good" to "great")
- QA testers finding and reporting bugs

---

## For nonprofits

If you're a Bible school, ministry, or educational nonprofit considering
this platform:

- **It's free.** MIT license means you can use, modify, and deploy it with
  zero cost.
- **No vendor lock-in.** Host it yourself or use the free tiers of Vercel +
  Supabase.
- **You don't need a developer on staff.** Follow the quick start above, or
  open a [discussion](https://github.com/ArVaViT/biblie-school/discussions)
  and the community will help.
- **Your feedback shapes the product.** Open a feature request — the roadmap
  is driven by real ministry needs.

---

## Community

- [GitHub Discussions](https://github.com/ArVaViT/biblie-school/discussions) — questions, ideas, show & tell
- [Issue tracker](https://github.com/ArVaViT/biblie-school/issues) — bug reports and feature requests
- [Changelog](CHANGELOG.md) — what's new in each release
- [Security policy](SECURITY.md) — how to report vulnerabilities

---

## License

[MIT](LICENSE) — free for personal, educational, and commercial use.
