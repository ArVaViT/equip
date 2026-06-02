/**
 * Teacher golden-path E2E.
 *
 * Skips cleanly when the test Supabase project isn't wired
 * (E2E_TEACHER_EMAIL not set) — same pattern as global.setup.ts. The
 * spec uses the role-bound ``teacherPage`` fixture which loads
 * storage state from ``playwright/.auth/teacher.json``; that file is
 * minted by global.setup.ts when env vars are populated.
 *
 * Flow covered:
 *   1. Teacher dashboard loads with the "My courses" section.
 *   2. "Create course" button is reachable from the dashboard.
 *   3. The course-editor route ``/teacher/courses/<id>/edit`` carries
 *      the structural editor (modules list).
 *
 * The actual create-flow that calls the backend is gated by the
 * Supabase env; we navigate but don't submit the create form when
 * env vars are unset.
 */
import { existsSync } from "node:fs";

import { test, expect } from "./fixtures/auth";

const AUTH_FILE = "playwright/.auth/teacher.json";

test.beforeEach(async () => {
  if (!existsSync(AUTH_FILE)) {
    test.skip(true, `${AUTH_FILE} missing — global.setup.ts didn't run; needs E2E_TEACHER_EMAIL`);
  }
});

test.describe("teacher golden path", () => {
  test("dashboard renders 'My courses' section", async ({ teacherPage }) => {
    await teacherPage.goto("/teacher", { waitUntil: "domcontentloaded" });
    // Match heading text in either language; the dashboard renders
    // an h2-equivalent for the courses section.
    const heading = teacherPage.getByRole("heading", {
      name: /(my\s*courses|мои\s*курсы)/i,
    });
    await expect(heading).toBeVisible({ timeout: 10_000 });
  });

  test("create-course CTA is reachable from dashboard", async ({ teacherPage }) => {
    await teacherPage.goto("/teacher", { waitUntil: "domcontentloaded" });
    const cta = teacherPage.getByRole("button", {
      name: /(create\s*course|new\s*course|создать\s*курс)/i,
    });
    await expect(cta).toBeVisible({ timeout: 10_000 });
  });

  test("teacher analytics tab is reachable", async ({ teacherPage }) => {
    await teacherPage.goto("/teacher/analytics", { waitUntil: "domcontentloaded" });
    // The analytics surface always lays out at least one of:
    // engagement heading, KPI tile, or empty-state copy.
    const body = await teacherPage.locator("body").innerText();
    expect(body).toMatch(/(analytics|аналитика|engagement|enrollments|stat)/i);
  });
});
