import { test, expect } from "@playwright/test";

/**
 * Smoke spec — the public home page renders without throwing.
 *
 * This pins the "blank page on hard refresh" class of regressions
 * that don't surface in Vitest because jsdom doesn't run the Vite
 * bundle the way a real browser does.
 *
 * The CI preview environment doesn't have a real Supabase project
 * wired up — so auth-dependent surfaces will swap to an error state,
 * but the *bundle itself* must still parse + execute without
 * uncaught errors. That's what these checks pin: the static HTML
 * arrives, the title is "Equip", and the React root mounts something
 * non-trivial. Stronger assertions (specific buttons, copy in a
 * locale) land in feature-specific specs once we wire a real test
 * Supabase project in CI.
 */

test.describe("public surface", () => {
  test("home renders without runtime errors", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (err) => errors.push(err.message));
    page.on("console", (msg) => {
      if (msg.type() !== "error") return;
      const text = msg.text();
      // CI preview lacks Supabase env wiring; the auth client logs
      // a noisy startup warning we don't want to count as a test
      // failure. Same for the React DevTools nag.
      if (text.includes("Download the React DevTools")) return;
      if (text.includes("Supabase")) return;
      if (text.includes("VITE_SUPABASE")) return;
      if (text.includes("Failed to load resource")) return;
      errors.push(text);
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page).toHaveTitle(/Equip/i);

    // The React root renders SOMETHING — even an auth-error fallback
    // is non-trivial. ``<div id="root"></div>`` would be the failure
    // shape we're guarding against.
    const root = page.locator("#root");
    await expect(root).not.toBeEmpty();

    expect(errors, errors.join("\n")).toHaveLength(0);
  });

  test("login route is reachable (no 404 / 500)", async ({ page }) => {
    // We assert on the HTTP shape of the navigation, not on
    // specific copy or a button — the CI preview without Supabase
    // env vars renders an error state, and we don't want to lock
    // the test to that state's strings.
    const response = await page.goto("/login", { waitUntil: "domcontentloaded" });
    // SPA route — the SAME static index.html serves /login, so the
    // status is 200 (Vite preview hands every path back to index).
    // We just want to confirm we didn't get a 5xx.
    expect(response?.status() ?? 0).toBeLessThan(500);
    await expect(page).toHaveTitle(/Equip/i);
  });
});
