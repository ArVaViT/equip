import { test as setup } from "@playwright/test";
import { mkdirSync, existsSync } from "node:fs";

import { getTestUser, signInViaForm } from "./fixtures/auth";

/**
 * Global setup for the Playwright suite.
 *
 * Signs in as each role-test user against the test Supabase project
 * and saves the resulting browser storage state to
 * ``playwright/.auth/<role>.json``. Each subsequent test reuses the
 * file via the role-bound fixtures in ``fixtures/auth.ts``.
 *
 * This file currently only runs when the env vars
 * ``E2E_STUDENT_EMAIL`` / ``E2E_TEACHER_EMAIL`` / ``E2E_ADMIN_EMAIL``
 * (etc.) are set. Until the test Supabase project lands in CI, the
 * setup is a no-op: it logs the skip reason and exits cleanly so the
 * smoke specs can still run.
 */

const AUTH_DIR = "playwright/.auth";

setup("authenticate as student", async ({ page }) => {
  if (!process.env.E2E_STUDENT_EMAIL) {
    setup.skip(true, "E2E_STUDENT_EMAIL not set — skipping student auth setup");
    return;
  }
  if (!existsSync(AUTH_DIR)) mkdirSync(AUTH_DIR, { recursive: true });
  const user = getTestUser("student");
  await signInViaForm(page, user);
  await page.context().storageState({ path: `${AUTH_DIR}/student.json` });
});

setup("authenticate as teacher", async ({ page }) => {
  if (!process.env.E2E_TEACHER_EMAIL) {
    setup.skip(true, "E2E_TEACHER_EMAIL not set — skipping teacher auth setup");
    return;
  }
  if (!existsSync(AUTH_DIR)) mkdirSync(AUTH_DIR, { recursive: true });
  const user = getTestUser("teacher");
  await signInViaForm(page, user);
  await page.context().storageState({ path: `${AUTH_DIR}/teacher.json` });
});

setup("authenticate as admin", async ({ page }) => {
  if (!process.env.E2E_ADMIN_EMAIL) {
    setup.skip(true, "E2E_ADMIN_EMAIL not set — skipping admin auth setup");
    return;
  }
  if (!existsSync(AUTH_DIR)) mkdirSync(AUTH_DIR, { recursive: true });
  const user = getTestUser("admin");
  await signInViaForm(page, user);
  await page.context().storageState({ path: `${AUTH_DIR}/admin.json` });
});
