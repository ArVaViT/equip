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
| Node.js    | >= 20    | `node -v` to check |
| npm        | >= 10    | ships with Node 20+ |
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

# Backend
cd backend && pip install -r requirements.txt && cd ..
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
cd backend  && python -m pytest tests/   # 396+ tests
cd frontend && npm run test:run           # Vitest + jsdom
```

If all tests pass, you're ready to contribute!

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

1. **Create a branch** off `main`:
   ```bash
   git checkout -b feat/my-feature
   ```
2. **Make your changes** — keep each PR focused on a single concern.
3. **Run linters and tests locally** before pushing:
   ```bash
   # Backend
   cd backend && ruff check . && mypy app/ && python -m pytest tests/

   # Frontend
   cd frontend && npm run lint && npx tsc --noEmit && npm run test:run
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

**Scope** is optional but encouraged: `feat(quiz)`, `fix(auth)`,
`chore(ci)`, `docs(readme)`.

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
- The application UI is in **Russian** (target audience).
- No Docker — the project intentionally avoids container-based workflows.

## Getting help

- **Discussions:** Use [GitHub Discussions](https://github.com/ArVaViT/equip/discussions)
  for questions, ideas, and community conversation.
- **Issues:** Open a [bug report](https://github.com/ArVaViT/equip/issues/new?template=bug_report.yml)
  or [feature request](https://github.com/ArVaViT/equip/issues/new?template=feature_request.yml).
- **Email:** arvavitcorp@gmail.com for anything sensitive.

---

By contributing, you agree that your contributions will be licensed under the
[MIT License](LICENSE).
