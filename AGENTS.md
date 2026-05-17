# AGENTS.md — Guidance for AI Coding Agents

This file orients AI coding assistants (Claude Code, Cursor, Aider, Codex,
Continue, Windsurf, Cline, etc.) working on this repository. Human
contributors should read [`CONTRIBUTING.md`](CONTRIBUTING.md) instead;
this is a tighter agent-focused mirror of the same conventions.

If you are an AI agent reading this in a contributor's local checkout:
follow these rules. If they conflict with explicit instructions from the
user, the user wins — but flag the conflict in your reply so the user
knows there is one.

## What this project is

**Equip** is an open-source learning management system for Bible schools,
church ministries, and nonprofit educational programs. Live instance at
https://equipbible.com. MIT-licensed. Stack:

- **Frontend** — React 18 + TypeScript + Vite, shadcn/ui + Radix, Tailwind, TipTap rich text. Lives in `frontend/`.
- **Backend** — FastAPI on Python 3.12, SQLAlchemy 2.0 ORM, Pydantic 2 schemas. Lives in `backend/`.
- **Database / auth / storage** — Supabase (managed Postgres + Auth + Storage). Schema source of truth is `supabase/migrations/`.
- **Hosting** — Vercel. Frontend at `equipbible.com`, backend at `api.equipbible.com`. Production deploys from `main`; PRs get preview deploys.

The UI is bilingual EN/RU; the design language targets Russian-speaking
Bible schools first. Code, comments, commits, and docs are written in
English.

## Source of truth — read these before non-trivial changes

- [`CONTRIBUTING.md`](CONTRIBUTING.md) — dev workflow, branch naming, Conventional Commits, the PowerShell commit-message workflow.
- [`docs/DESIGN.md`](docs/DESIGN.md) — design tokens, banned patterns, the four-check rule for adding a library.
- [`docs/COMPONENTS.md`](docs/COMPONENTS.md) — pattern library (`<Badge>`, `<StatCard>`, `<EmptyState>`, `<ErrorState>`, `<InlineEdit>`, `<PageHeader>`, `<Modal>`) — always reach for these before writing a custom equivalent.
- [`docs/I18N.md`](docs/I18N.md) — bilingual workflow, plural categories, locale parity guard, DB-enum localization recipe.
- [`docs/UI-DECISIONS.md`](docs/UI-DECISIONS.md) — frozen UI decisions; do not re-litigate without sign-off from a maintainer.
- [`docs/adr/`](docs/adr) — Architecture Decision Records for cross-module choices.
- [`supabase/migrations/README.md`](supabase/migrations/README.md) — append-only migration workflow.

## Hard rules — do not violate

These are load-bearing for the project. Violating them produces noisy
PRs that get bounced.

- **No raw Tailwind palette classes.** No `bg-blue-500`, `text-gray-700`, `border-red-300`. Use the semantic tokens from `docs/DESIGN.md` (`bg-primary`, `text-muted-foreground`, `border-input`, etc.).
- **No `window.alert / prompt / confirm`.** Confirmations go through `useConfirm()` + Radix `AlertDialog`. Toasts go through `sonner`.
- **Icons:** `lucide-react` only. Sizes are `16`, `20`, or `24`. `strokeWidth={1.75}` on every icon.
- **All user-facing strings go through `t(...)`.** Locale bundles live in `frontend/src/i18n/locales/{en,ru}.json` and must stay in parity. CI fails on drift.
- **Conventional Commits.** `feat(quiz): ...`, `fix(auth): ...`, `chore(ci): ...`. Branch name mirrors the commit prefix (`feat/quiz-extra-attempts`, `fix/audit-invalid-uuid`).
- **Migrations are append-only.** Never edit an `.sql` file under `supabase/migrations/` that has already been applied. Create a new timestamped file (`YYYYMMDDHHMMSS_<slug>.sql`) instead.
- **The four-way enum mirror.** A new persisted enum value must be added in **four** places that stay in lockstep: Postgres `CHECK` constraint, Pydantic `Literal[...]`, TypeScript union type, and the TypeScript `const` accessor (e.g. `ROLES`). See `frontend/src/types/index.ts` for the pattern.
- **No Docker.** The project deliberately avoids container workflows today. Do not suggest one.

## Pre-PR verification

Run locally before pushing — CI is zero-warnings on all of these:

```bash
# Backend
cd backend
ruff check .
ruff format --check .
mypy --config-file mypy.ini
python -m pytest tests/

# Frontend
cd frontend
npm run lint        # eslint --max-warnings 0
npx tsc --noEmit    # strict
npm run i18n:check  # locale parity
npm run test:run    # vitest
npm run build       # tsc && vite build
```

## Commit conventions — including AI co-authorship

We follow [Conventional Commits](https://www.conventionalcommits.org/).
**If you are an AI agent committing on behalf of a human contributor, add
a `Co-Authored-By:` trailer crediting yourself** so the contribution
history reflects how the change was actually made:

```
feat(quiz): allow teacher-gifted extra attempts

A student who runs out of attempts can be granted more without
resetting the whole `attempts_used` counter. Implemented as a new
`quiz_extra_attempts` row keyed on (quiz_id, user_id).

Co-Authored-By: Claude <noreply@anthropic.com>
```

Use the appropriate identity for your tool. If unsure, use your tool's
documented Co-Authored-By identity or pick the closest:

- Claude Code / Claude — `Co-Authored-By: Claude <noreply@anthropic.com>`
- Cursor — `Co-Authored-By: Cursor <noreply@cursor.sh>`
- Aider — `Co-Authored-By: Aider <noreply@aider.chat>`
- GitHub Copilot — `Co-Authored-By: GitHub Copilot <noreply@github.com>`
- OpenAI Codex / ChatGPT — `Co-Authored-By: ChatGPT <noreply@openai.com>`

This is a **transparency** convention, not a gate. PRs are not rejected
for missing trailers. It just lets us — and you, looking back at history
— see how the codebase actually got built. We want that signal to be
honest.

## What you must NOT do

- **Do not fabricate API behavior or types.** If you don't know what an endpoint returns, read the route in `backend/app/api/v1/` and the matching Pydantic schema in `backend/app/schemas/`. Never invent fields.
- **Do not edit applied migrations.** Always add a new timestamped file.
- **Do not introduce a new library** without running the four-check rule from `docs/DESIGN.md`: (1) is it actually needed, (2) does an existing dep cover it, (3) is it actively maintained, (4) does it fit the stack idioms.
- **Do not commit secrets.** `.env`, `*.key`, `*.pem`, `credentials.json`, `serviceAccountKey.json` are blocked by the `pr-quality` CI job; GitHub secret-scanning push-protection blocks known token formats at push time.
- **Do not skip CI hooks** (`--no-verify` etc.) unless the user explicitly asks.
- **Do not amend already-pushed commits.** Add a new commit instead — the project values legible PR history.

## Getting unstuck

If a convention in this file (or a linked doc) conflicts with the
existing code, **the existing code is authoritative** unless the
contradiction is clearly a bug. Mention the conflict in the PR
description so a maintainer can decide which is canonical.

Open questions go in [GitHub Discussions](https://github.com/ArVaViT/equip/discussions),
not buried in code comments.
