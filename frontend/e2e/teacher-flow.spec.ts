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
    // The teacher dashboard's primary CTA (ru: «Новый курс»).
    const cta = teacherPage.getByRole("button", {
      name: /(create\s*course|new\s*course|создать\s*курс|новый\s*курс)/i,
    });
    await expect(cta).toBeVisible({ timeout: 10_000 });
  });

  test("teacher analytics is reachable from a course", async ({ teacherPage }) => {
    // Analytics is per-course (route /teacher/courses/:id/analytics),
    // surfaced as an "Аналитика" action on each course card of the
    // dashboard — there is no standalone /teacher/analytics route.
    await teacherPage.goto("/teacher", { waitUntil: "domcontentloaded" });
    const analyticsLink = teacherPage
      .getByRole("link", { name: /(analytics|аналитика)/i })
      .first();
    await expect(analyticsLink).toBeVisible({ timeout: 10_000 });
    await analyticsLink.click();
    await teacherPage.waitForURL(/\/teacher\/courses\/.+\/analytics/);
    await expect(teacherPage.locator("body")).toContainText(
      /(analytics|аналитика|engagement|enrollments|stat|вовлечён|запис)/i,
      { timeout: 10_000 },
    );
  });
});
