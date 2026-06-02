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
- For surfaces that need a logged-in user, use `auth.setup.ts`
  (Playwright global setup; populated when we wire real auth E2E).
- Network mocking: prefer `page.route` over patching the SUT — the
  whole point is to exercise the real frontend code path.

## What's in here so far

- `smoke.spec.ts` — the home / public catalog renders without
  errors. Pinning this catches the "blank page on hard refresh"
  class of regressions that don't surface in Vitest because jsdom
  doesn't run the actual bundle.

## What's coming (per the roadmap)

- Auth flows (login, password reset, sign-up).
- Student golden path: catalog → enroll → chapter → quiz submit.
- Teacher golden path: create course → publish → student visibility.

## CI

The GitHub workflow at `.github/workflows/frontend-e2e.yml` boots
the dev server, runs the suite, and uploads traces + screenshots on
failure. Until that workflow lands, tests are local-only.
