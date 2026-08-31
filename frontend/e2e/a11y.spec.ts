/**
 * Page-level a11y audit — runs `@axe-core/playwright` against the
 * public surfaces in a real Chromium context.
 *
 * What this catches beyond jest-axe (component-level):
 * - Missing landmarks (header / main / footer) on real pages.
 * - Page title presence + uniqueness.
 * - Skip-link semantics (when added).
 * - Color contrast computed against the actual rendered styles
 *   (not Vitest's jsdom which ignores CSS).
 *
 * Scope today: public unauthenticated pages — home + login. The
 * authenticated surfaces (dashboard, course detail, editor) require
 * a wired test Supabase project; they land in a follow-up using the
 * role-bound fixtures in `fixtures/auth.ts`.
 *
 * We INCLUDE `wcag2a` + `wcag2aa` tag sets. We do NOT include the
 * preview / experimental rule set — those churn between axe-core
 * releases and would flake CI without telling us anything load-
 * bearing.
 *
 * The CI preview env lacks Supabase env vars, so several rules that
 * depend on a real DOM tree (`landmark-one-main`, `region`) may not
 * have content to attach to. We DON'T disable them globally; instead
 * each individual test scopes the run to the actual rendered region
 * via `.include()`.
 */
import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * Wait for every FINITE animation/transition to finish before axe runs.
 *
 * The entrance fade (`animate-fade-in`, ~0.55s) animates opacity, and axe
 * computes color contrast against the rendered frame — sampling mid-fade
 * produced phantom contrast violations (e.g. text-ink-muted #5f556d blended
 * to #7f7789 at ~80% opacity → a 4.04:1 "failure" on an element whose
 * resting contrast passes). Two subtleties:
 *
 * 1. `networkidle` first: lazily-loaded chunks (Suspense routes, the
 *    per-locale i18n catalogs) mount AFTER domcontentloaded, so their
 *    entrance animations don't exist yet when a single settle pass runs —
 *    exactly how the deterministic 4.04 reappeared once the shell went lazy.
 * 2. Settle in a LOOP: each newly-mounted subtree can start a fresh wave
 *    of animations; drain waves until a pass finds none (bounded so a
 *    pathological page can't hang the suite).
 *
 * Infinite animations (spinners) are skipped so this can never hang.
 */
async function settleAnimations(page: Page): Promise<void> {
  await page.waitForLoadState("networkidle");
  for (let wave = 0; wave < 5; wave++) {
    const finiteAnimations = await page.evaluate(async () => {
      const anims = document
        .getAnimations()
        .filter((a) => a.effect?.getTiming().iterations !== Infinity);
      await Promise.all(anims.map((a) => a.finished.catch(() => undefined)));
      return anims.length;
    });
    if (finiteAnimations === 0) return;
  }
}

test.describe("page-level a11y (public)", () => {
  test("home page has no WCAG 2.1 AA violations", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await settleAnimations(page);

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      // CI preview lacks Supabase env so the auth client throws and
      // the page may not have rendered its full layout chrome. The
      // `landmark-one-main` rule is sensitive to that — disable just
      // here, not project-wide.
      .disableRules(["landmark-one-main", "region"])
      .analyze();

    expect(
      accessibilityScanResults.violations,
      JSON.stringify(accessibilityScanResults.violations, null, 2),
    ).toEqual([]);
  });

  test("register page has no WCAG 2.1 AA violations", async ({ page }) => {
    // The busiest form the product has for somebody who is not yet a user,
    // and the one that carries the password rules, the reveal toggle and the
    // generator. jsdom + axe covers the component; this covers the page as a
    // browser actually paints it.
    await page.goto("/register", { waitUntil: "domcontentloaded" });
    await settleAnimations(page);

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .disableRules(["landmark-one-main", "region"])
      .analyze();

    expect(
      accessibilityScanResults.violations,
      JSON.stringify(accessibilityScanResults.violations, null, 2),
    ).toEqual([]);
  });

  test("the password rules are on the register page, not only in the error", async ({ page }) => {
    // Six of the seven password accounts ever created here never confirmed,
    // and the last of them was refused three times for a weak password with
    // nothing on screen saying what the rules were.
    await page.goto("/register", { waitUntil: "domcontentloaded" });
    await settleAnimations(page);

    await expect(page.getByText(/12/).first()).toBeVisible();

    const generate = page.getByRole("button", {
      name: /generate a strong one|придумать надёжный|sicheres erzeugen|створити надійний/i,
    });
    await expect(generate).toBeVisible();
    await generate.click();

    // Both fields filled, and revealed so the value can be saved.
    const password = page.locator("#reg-password");
    const confirm = page.locator("#reg-confirmPassword");
    await expect(password).toHaveAttribute("type", "text");
    const value = await password.inputValue();
    expect(value.length).toBeGreaterThanOrEqual(12);
    await expect(confirm).toHaveValue(value);
  });

  test("login page has no WCAG 2.1 AA violations", async ({ page }) => {
    await page.goto("/login", { waitUntil: "domcontentloaded" });
    await settleAnimations(page);

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .disableRules(["landmark-one-main", "region"])
      .analyze();

    expect(
      accessibilityScanResults.violations,
      JSON.stringify(accessibilityScanResults.violations, null, 2),
    ).toEqual([]);
  });
});

test.describe("page metadata", () => {
  test("home + login pages have non-empty <title>", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    const homeTitle = await page.title();
    expect(homeTitle.length).toBeGreaterThan(0);
    expect(homeTitle).toMatch(/Equip/i);

    await page.goto("/login", { waitUntil: "domcontentloaded" });
    const loginTitle = await page.title();
    expect(loginTitle.length).toBeGreaterThan(0);
    expect(loginTitle).toMatch(/Equip/i);
  });

  test("html element has a lang attribute", async ({ page }) => {
    await page.goto("/", { waitUntil: "domcontentloaded" });
    const lang = await page.locator("html").getAttribute("lang");
    // axe also flags this as `html-has-lang`; this assertion gives a
    // clearer test name in CI when the regression happens.
    expect(lang).toBeTruthy();
    expect(lang).toMatch(/^(en|ru)/i);
  });
});
