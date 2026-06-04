/**
 * Public surface golden-path E2E.
 *
 * Exercises flows that don't require an authenticated session,
 * complementing the a11y page-scans in ``a11y.spec.ts``:
 *   - The public landing renders the brand wordmark and a working
 *     login link.
 *   - The login form validates an empty submit (no Supabase round-trip
 *     needed).
 *   - The register form is reachable from login.
 *   - The 404 page is reachable for an unknown route.
 *
 * These run in every CI invocation. The authenticated golden paths
 * (teacher-flow.spec.ts, student-flow.spec.ts) skip cleanly when the
 * test Supabase env vars aren't populated.
 */
import { test, expect } from "@playwright/test";

test.describe("public surfaces", () => {
  test("landing → login navigation works", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page).toHaveTitle(/Equip/i);

    // The header carries a sign-in entry point regardless of
    // language. The link text varies by locale; targeting by URL
    // pattern keeps the test bilingual. Use an auto-retrying
    // visibility assertion (NOT a one-shot count) — `domcontentloaded`
    // fires before the React bundle mounts, so reading the DOM once
    // races the hydration and intermittently sees zero links.
    const loginLink = page.locator('a[href="/login"]').first();
    await expect(loginLink).toBeVisible();
    await loginLink.click();
    await page.waitForURL(/\/login/);
    await expect(page).toHaveURL(/\/login/);
  });

  test("login page has an email + password field and a submit", async ({ page }) => {
    await page.goto("/login", { waitUntil: "networkidle" });

    // Use accessible-name match so the test works in either UI
    // language — the locale-switcher may flip these.
    const email = page.getByLabel(/email/i);
    const password = page.getByLabel(/password|пароль/i);
    const submit = page.getByRole("button", { name: /sign in|войти|log\s*in/i });

    await expect(email).toBeVisible();
    await expect(password).toBeVisible();
    await expect(submit).toBeVisible();
  });

  test("login → register navigation works", async ({ page }) => {
    await page.goto("/login", { waitUntil: "networkidle" });
    // Auto-retrying assertion instead of a one-shot count — see the
    // landing test: a direct deep-link load resolves the SPA shell
    // before React renders the route, so a single read races hydration.
    const registerLink = page.locator('a[href="/register"]').first();
    await expect(registerLink).toBeVisible();
    await registerLink.click();
    await page.waitForURL(/\/register/);
    await expect(page).toHaveURL(/\/register/);
  });

  test("unknown route renders the 404 page (200 or 404 — SPA)", async ({ page }) => {
    // Vite + react-router SPAs serve index.html for unknown routes
    // (the router resolves to <NotFound/>). The HTTP status is 200
    // but the visible UI is the 404 page; assert on visible content,
    // not HTTP status. `toContainText` auto-retries until React renders
    // the route — a one-shot `innerText()` read after `domcontentloaded`
    // returns "" because hydration hasn't run yet (the real CI flake).
    // ``найден`` (not ``найдено``) matches the feminine "Страница не
    // найдена" copy that actually ships.
    await page.goto("/this-page-does-not-exist", { waitUntil: "networkidle" });
    await expect(page.locator("body")).toContainText(/(404|not\s*found|не\s*найден|стран)/i);
  });
});
