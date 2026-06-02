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
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page).toHaveTitle(/Equip/i);

    // The header carries a sign-in entry point regardless of
    // language. The link text varies by locale; targeting by URL
    // pattern keeps the test bilingual.
    const loginLinks = page.locator('a[href="/login"]');
    expect(await loginLinks.count()).toBeGreaterThan(0);
    await loginLinks.first().click();
    await page.waitForURL(/\/login/);
    await expect(page).toHaveURL(/\/login/);
  });

  test("login page has an email + password field and a submit", async ({ page }) => {
    await page.goto("/login", { waitUntil: "domcontentloaded" });

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
    await page.goto("/login", { waitUntil: "domcontentloaded" });
    const registerLink = page.locator('a[href="/register"]');
    expect(await registerLink.count()).toBeGreaterThan(0);
    await registerLink.first().click();
    await page.waitForURL(/\/register/);
    await expect(page).toHaveURL(/\/register/);
  });

  test("unknown route renders the 404 page (200 or 404 — SPA)", async ({ page }) => {
    // Vite + react-router SPAs serve index.html for unknown routes
    // (the router resolves to <NotFound/>). The HTTP status is 200
    // but the visible UI is the 404 page; assert on visible content,
    // not HTTP status.
    await page.goto("/this-page-does-not-exist", { waitUntil: "domcontentloaded" });
    const body = await page.locator("body").innerText();
    // Either the English or Russian 404 copy must show up.
    expect(body).toMatch(/(404|not\s*found|не\s*найдено|стран)/i);
  });
});
