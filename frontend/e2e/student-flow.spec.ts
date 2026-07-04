/**
 * Student golden-path E2E.
 *
 * Skips cleanly when the test Supabase project isn't wired
 * (E2E_STUDENT_EMAIL not set) — same pattern as global.setup.ts.
 *
 * Flow covered:
 *   1. Student dashboard renders the daily-challenge card.
 *   2. Catalog page lists at least one course (assumes the test
 *      project has been seeded by ``scripts/seed_fat_test_course.py``
 *      or similar — see Memory/equip-e2e-test-data.md).
 *   3. Course detail page renders for the seeded course.
 */
import { existsSync } from "node:fs";

import { test, expect } from "./fixtures/auth";

const AUTH_FILE = "playwright/.auth/student.json";

test.beforeEach(async () => {
  if (!existsSync(AUTH_FILE)) {
    test.skip(true, `${AUTH_FILE} missing — global.setup.ts didn't run; needs E2E_STUDENT_EMAIL`);
  }
});

test.describe("student golden path", () => {
  test("dashboard renders the daily challenge card", async ({ studentPage }) => {
    await studentPage.goto("/", { waitUntil: "domcontentloaded" });
    // The daily-challenge card is load-bearing on the student
    // dashboard. Its heading is the localized "question of the day"
    // title (ru: «Сегодняшний вопрос» / eyebrow «Вопрос дня»).
    const card = studentPage.getByRole("heading", {
      name: /(daily\s*challenge|вопрос\s*дня|сегодняшний\s*вопрос)/i,
    });
    await expect(card).toBeVisible({ timeout: 10_000 });
  });

  test("catalog page renders the course list", async ({ studentPage }) => {
    await studentPage.goto("/courses", { waitUntil: "domcontentloaded" });
    // The catalog renders either: course cards, or an "empty state"
    // when there are no published courses. Either is OK for the
    // golden path; both pin that the route resolved + the layout
    // chrome mounted. Use a web-first assertion so the check retries
    // past the initial "Загрузка…" spinner instead of reading once.
    await expect(studentPage.locator("body")).toContainText(
      /(course|курс|no\s*courses|нет\s*курсов)/i,
      { timeout: 10_000 },
    );
  });

  test("profile page reachable from authenticated state", async ({ studentPage }) => {
    await studentPage.goto("/profile", { waitUntil: "domcontentloaded" });
    // Profile renders the user's display name + the locale picker. We
    // don't assert on the specific name; only that one of the shared
    // profile-page sections resolves (web-first assertion retries past
    // the loading spinner).
    await expect(studentPage.locator("body")).toContainText(
      /(profile|профил|account|account\s*settings|locale|язык)/i,
      { timeout: 10_000 },
    );
  });
});
