import { test, expect } from "@playwright/test";

/**
 * Smoke spec — the public home page renders without throwing.
 *
 * This pins the "blank page on hard refresh" class of regressions
 * that don't surface in Vitest because jsdom doesn't run the Vite
 * bundle the way a real browser does. If the bundle has an unhandled
 * top-level await, a missing env var, or a route guard that 500s
 * the public surface, this test catches it.
 */

test.describe("public surface", () => {
  test("home renders without runtime errors", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));
    page.on("console", (msg) => {
      // Filter out the React DevTools nag and Vite's noisy HMR
      // pings; we only care about actual runtime errors here.
      if (msg.type() !== "error") return;
      const text = msg.text();
      if (text.includes("Download the React DevTools")) return;
      errors.push(text);
    });

    await page.goto("/");
    // The Equip header text is rendered on every public page.
    await expect(page).toHaveTitle(/Equip/i);

    // Empty errors array means no top-level explosions during load.
    expect(errors, errors.join("\n")).toHaveLength(0);
  });

  test("login page is reachable", async ({ page }) => {
    await page.goto("/login");
    // The form has an email + password input + a submit. We use role
    // selectors so the test survives Tailwind class renames.
    await expect(page.getByRole("button", { name: /sign in|войти/i })).toBeVisible({
      timeout: 10_000,
    });
  });
});
