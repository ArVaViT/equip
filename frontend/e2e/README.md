# Equip E2E (Playwright)

End-to-end browser tests for the Equip frontend.

## Why Playwright

Vitest covers component unit tests with jsdom; Playwright covers the
real-browser interactions Vitest can't: navigation, multi-step forms,
auth redirects, route guards, and cross-page state.

## Running locally

In one terminal, start the backend + frontend the normal way:

```powershell
cd backend
uvicorn app.main:app --reload   # http://localhost:8000

cd frontend
npm run dev                      # http://localhost:5173
```

Then in another terminal:

```powershell
cd frontend
npm run test:e2e                  # headless
npm run test:e2e:headed           # see the browser
npm run test:e2e -- --debug       # step-debugger
```

To run a single file:

```powershell
npm run test:e2e -- e2e/smoke.spec.ts
```

## Conventions

- File suffix: `*.spec.ts` (Playwright's default).
- One feature per file. Group related scenarios in `test.describe`.
- Prefer `page.getByRole`/`page.getByLabel` over CSS selectors so the
  tests survive class renames in the design system.
- For surfaces that need a logged-in user, use the fixtures in
  `fixtures/auth.ts`. `global.setup.ts` signs in the student / teacher /
  admin accounts named by the `E2E_*_EMAIL` / `E2E_*_PASSWORD` env vars
  and stores their sessions under `playwright/.auth/`; without those
  vars the authenticated specs skip themselves.
- Network mocking: prefer `page.route` over patching the SUT — the
  whole point is to exercise the real frontend code path.

## What's in here

Public (run everywhere, no credentials):

- `smoke.spec.ts` — the home / public catalog renders without
  errors. Pinning this catches the "blank page on hard refresh"
  class of regressions that don't surface in Vitest because jsdom
  doesn't run the actual bundle.
- `public-flows.spec.ts` — the public routes a visitor can reach.
- `a11y.spec.ts` — axe over the real pages (also runnable through
  `./scripts/gate.sh a11y`).
- `no-sideways-scroll.spec.ts` — nothing scrolls horizontally on a phone.
- `every-language.spec.ts`, `the-language-you-arrived-in.spec.ts` — the
  four locales render and the arrival language sticks.

Authenticated (need the `E2E_*` env vars, otherwise skipped):

- `student-flow.spec.ts` — catalog → enroll → chapter → quiz.
- `teacher-flow.spec.ts` — create course → publish → student visibility.

## CI

`.github/workflows/frontend-e2e.yml` builds the frontend, serves it, runs
the suite and uploads traces + screenshots on failure. The authenticated
specs run only while the repo variable `STAGING_ACTIVE` is `true` and the
`E2E_*` secrets point at staging (see `docs/STAGING.md`); in every other
state the build falls back to placeholder env and only the public specs
run -- a green run does not by itself prove the student and teacher paths.
