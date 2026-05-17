# Contributing to Equip

Thank you for considering a contribution! This project is built by and for
nonprofit Bible schools, ministries, and individual believers who want a
modern, free LMS. Every contribution — code, docs, translations, bug reports —
makes a real difference.

## Table of contents

- [Quick start](#quick-start)
- [Project structure](#project-structure)
- [Development workflow](#development-workflow)
- [Commit conventions](#commit-conventions)
- [Pull request process](#pull-request-process)
- [Finding work to do](#finding-work-to-do)
- [Style guides](#style-guides)
- [Getting help](#getting-help)

## Quick start

### Prerequisites

| Tool       | Version  | Notes |
|------------|----------|-------|
| Node.js    | >= 22.12 | matches CI (`22.18.0`); `node -v` to check |
| npm        | >= 10    | ships with Node 22+ |
| Python     | 3.12     | must match CI and Vercel runtime |
| Git        | any      | |

### 1. Fork and clone

```bash
gh repo fork ArVaViT/equip --clone
cd equip
```

### 2. Install dependencies

```bash
# Frontend
cd frontend && npm ci && cd ..

# Backend (runtime + tooling)
# requirements-ci.txt is a superset of requirements.txt; installing it
# mirrors the CI environment so `pytest`, `mypy`, `ruff`, `pip-audit`
# all work locally.
cd backend && pip install -r requirements-ci.txt && cd ..
```

### 3. Configure environment

```bash
cp frontend/.env.example frontend/.env.local
cp backend/.env.example  backend/.env
```

Fill in the Supabase credentials. If you don't have a Supabase project, you
can run backend tests without one (they use SQLite in-memory).

### 4. Start development servers

```bash
# Terminal 1 — API
cd backend && uvicorn app.main:app --reload    # http://localhost:8000

# Terminal 2 — SPA
cd frontend && npm run dev                     # http://localhost:5173
```

### 5. Run tests

```bash
cd backend  && python -m pytest tests/   # 540+ tests, ~10s
cd frontend && npm run test:run           # Vitest + jsdom
```

If all tests pass, you're ready to contribute!

### Architecture decision records

Major architectural decisions live under [`docs/adr/`](docs/adr/).
Read the index before changing anything that crosses module
boundaries (cohorts, translation pipeline, soft-delete behaviour,
etc.).

## Project structure

```
backend/            Python FastAPI application
  app/
    api/v1/         route modules
    core/           config, database, auth helpers
    models/         SQLAlchemy ORM models
    schemas/        Pydantic request/response models
    services/       business logic
  tests/            pytest suite (SQLite in-memory)

frontend/           React SPA (Vite + TypeScript)
  src/
    components/     UI components (shadcn/ui + custom)
    pages/          route-level pages
    services/       API client (axios) + Supabase helpers
    context/        React contexts (auth, theme)

supabase/
  migrations/       SQL migrations — production schema source of truth

.github/
  workflows/        CI pipelines (lint, test, build, audit)
  ISSUE_TEMPLATE/   bug/feature templates
```

## Development workflow

1. **Create a branch** off `main`. The branch name should mirror the commit
   type so the intent is visible in the branch list:
   ```bash
   git checkout -b feat/quiz-extra-attempts
   git checkout -b fix/audit-invalid-uuid
   git checkout -b docs/readme-refresh
   git checkout -b refactor/role-const
   ```
   Common prefixes: `feat/`, `fix/`, `docs/`, `chore/`, `refactor/`, `test/`,
   `design/` (UI-only polish). Use `kebab-case` for the rest.
2. **Make your changes** — keep each PR focused on a single concern.
3. **Run linters and tests locally** before pushing:
   ```bash
   # Backend
   cd backend && ruff check . && mypy app/ && python -m pytest tests/

   # Frontend
   cd frontend && npm run lint && npx tsc --noEmit && npm run test:run
   cd frontend && npm run i18n:check    # locale parity (see "Bilingual workflow")
   ```
4. **Push** and open a pull request against `main`.

## Commit conventions

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): short description

Optional longer body explaining *why*, not *what*.
```

| Type       | When to use |
|------------|-------------|
| `feat`     | New feature or capability |
| `fix`      | Bug fix |
| `docs`     | Documentation only |
| `chore`    | Maintenance, deps, CI config |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `test`     | Adding or updating tests |
| `style`    | UI / design polish (CSS, animation, micro-interactions) |

**Scope** is optional but encouraged: `feat(quiz)`, `fix(auth)`,
`chore(ci)`, `docs(readme)`, `style(frontend)`.

### Multi-line commit messages on Windows / PowerShell

`git commit -m "..."` only accepts a single quoted line on PowerShell, and
PowerShell does not support bash heredocs. For commits with a body, write
the message to a file and pass it with `-F`:

```powershell
@'
feat(quiz): allow teacher-gifted extra attempts

A student who runs out of attempts can be granted more without
resetting the whole `attempts_used` counter. Implemented as a new
`quiz_extra_attempts` row keyed on (quiz_id, user_id).
'@ | Set-Content .commit-msg.tmp -Encoding utf8
git commit -F .commit-msg.tmp
Remove-Item .commit-msg.tmp
```

`.commit-msg.tmp` and `.tmp-commit-msg.txt` are gitignored exactly so you
can do this without staging the scratch file by accident.

## Pull request process

1. Fill in the PR template (summary + checklist).
2. Ensure CI passes — we require `Frontend CI / lint-and-build`,
   `Backend CI / lint-and-test`, and `Backend CI / schema-smoke-postgres`.
3. Self-review your diff before requesting review.
4. A maintainer will review, possibly request changes, and merge.

Keep PRs small and atomic. A 200-line PR with tests gets reviewed in hours;
a 2000-line PR sits for weeks.

## Finding work to do

| Label | Description |
|-------|-------------|
| `good first issue` | Ideal starting point for new contributors |
| `help wanted` | Maintainers would love external help here |
| `bug` | Something is broken |
| `enhancement` | Improvement to existing functionality |
| `documentation` | Docs, README, or inline help improvements |

Check the [open issues](https://github.com/ArVaViT/equip/issues) and
the [ROADMAP](ROADMAP.md) for bigger-picture direction.

## Style guides

### Backend (Python)

- **Linter/formatter:** [Ruff](https://docs.astral.sh/ruff/) — config in
  `backend/ruff.toml`.
- **Type checking:** `mypy` with strict mode on the entire `app/` directory.
- **Zero warnings policy** — CI fails on any lint or type error.

### Frontend (TypeScript/React)

- **Linter:** ESLint flat config — `frontend/eslint.config.js`.
- **Type checking:** strict `tsc --noEmit`.
- **UI library:** [shadcn/ui](https://ui.shadcn.com/) + Radix primitives.
- **Icons:** `lucide-react` only. Sizes 16/20/24, `strokeWidth={1.75}`.
- **CSS:** Tailwind with semantic tokens (no raw palette classes like
  `bg-blue-500`). See `docs/DESIGN.md` for the full design guide.

### General

- Code, comments, commit messages, and docs are in **English**.
- The application UI is **bilingual** RU↔EN with the design language
  targeting Russian-speaking Bible schools first. Every user-facing
  string goes through `t(...)`. See [the bilingual workflow](docs/I18N.md)
  for the full pattern (locale bundles, plural categories, the parity
  guard, and how to add a key for a DB-persisted enum value).
- No Docker — the project intentionally avoids container-based
  workflows today. A potential self-hosted installer (which may use
  Docker Compose) is on the long-term roadmap; if/when that lands the
  rule changes only for that path. Until then: deploy via Vercel,
  develop natively.

### Bilingual workflow (UI strings)

Short version:

- All user-facing strings come from `frontend/src/i18n/locales/{en,ru}.json`.
- Never hand-edit only one of the two files — they must stay in parity.
  `npm run i18n:check` (and a stricter `keyCoverage` Vitest test) enforces
  this in CI.
- Russian uses the four plural categories `_one`, `_few`, `_many`, `_other`.
  English uses `_one` and `_other`. i18next picks the right form at
  runtime based on the count argument.

See [`docs/I18N.md`](docs/I18N.md) for the full guide — including how to
add a translation key for a Postgres-persisted enum value (course status,
quiz question type, certificate status, etc.) so the same string can map
to a DB row.

### Backend ↔ Frontend ↔ Database: the four-way enum mirror

Every persisted enum value (role, course status, quiz question type,
certificate status, audit action, …) is declared in **four** places that
must stay in lockstep:

1. **Postgres `CHECK` constraint** on the column — the runtime guard.
2. **Pydantic `Literal[...]`** in `backend/app/schemas/` — the API
   contract (and what FastAPI's OpenAPI export advertises).
3. **TypeScript union type** in `frontend/src/types/` — what the client
   knows about.
4. **TypeScript `const` object** in `frontend/src/types/` (e.g. `ROLES`,
   `STATUSES`) — the no-typo accessor every callsite uses.

When you add or change a value, change all four. The pattern is
documented at the `ROLES` const in `frontend/src/types/index.ts`. A typo
in `"adimn"` is caught by TypeScript when you use `ROLES.ADMIN`; the
bare string would silently fail the role check.

### Conventions library

Tracked-in-git references that every contributor reads:

- [`docs/DESIGN.md`](docs/DESIGN.md) — design system: aesthetic, tokens,
  typography, spacing, motion, icons, banned patterns, the
  four-check rule for adding a library.
- [`docs/COMPONENTS.md`](docs/COMPONENTS.md) — the patterns library
  (`<Badge>`, `<StatCard>`, `<EmptyState>`, `<ErrorState>`,
  `<InlineEdit>`, `<PageHeader>`, `<Modal>`) and when to reach for each.
- [`docs/I18N.md`](docs/I18N.md) — bilingual workflow, plural categories,
  parity guard, how to add a key for a DB-persisted enum value.
- [`docs/UI-DECISIONS.md`](docs/UI-DECISIONS.md) — log of frozen UI
  decisions (don't re-litigate without sign-off).
- [`docs/adr/`](docs/adr/) — Architecture Decision Records for
  cross-module choices.
- [`supabase/migrations/README.md`](supabase/migrations/README.md) —
  append-only migration workflow.

> If you have Cursor installed locally, a `.cursor/rules/` directory of
> editor-targeted rules can give the AI assistant the same conventions
> in a more concise form. That directory is gitignored (each contributor
> maintains their own); the tracked docs above are the source of truth.

## Getting help

- **Discussions:** Use [GitHub Discussions](https://github.com/ArVaViT/equip/discussions)
  for questions, ideas, and community conversation.
- **Issues:** Open a [bug report](https://github.com/ArVaViT/equip/issues/new?template=bug_report.yml)
  or [feature request](https://github.com/ArVaViT/equip/issues/new?template=feature_request.yml).
- **Email:** arvavitcorp@gmail.com for anything sensitive.

---

By contributing, you agree that your contributions will be licensed under the
[MIT License](LICENSE).
