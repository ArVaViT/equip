import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright E2E config — Equip frontend.
 *
 * Tests live in ``e2e/`` and run against a locally booted Vite dev
 * server (``npm run dev``) at http://localhost:5173. CI sets
 * ``CI=true`` so the runner uses retries + the GitHub reporter.
 *
 * Why Chromium-only: Equip's user base is the diaspora-Bible-school
 * + church audience; mobile Safari/Firefox usage is negligible per the
 * RUM dashboard (>95% Chromium-family). Adding the other browsers
 * doubles CI minutes without proportional value. Re-add when the RUM
 * mix shifts.
 *
 * The dev server is **NOT** auto-started by Playwright; we expect it
 * running. This avoids a flake where Playwright tries to boot Vite
 * before backend env vars are set. The CI workflow handles the boot
 * order explicitly.
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? "github" : "list",
  timeout: 30_000,
  expect: { timeout: 5_000 },

  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },

  projects: [
    // Global setup project — mints storage-state files for the
    // role-bound fixtures in ``fixtures/auth.ts``. No-ops cleanly
    // when the E2E_*_EMAIL env vars are unset (current CI state).
    {
      name: "setup",
      testMatch: /global\.setup\.ts/,
    },
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
      dependencies: ["setup"],
    },
  ],
});
