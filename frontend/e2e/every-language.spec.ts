import { test, expect } from "@playwright/test";

/**
 * The interface renders in each language, and never renders its keys.
 *
 * Production spent an unknown number of days showing readers
 * `header.home`, `courses.pageTitleAuthed`, `common.appName` — the raw
 * translation keys — because one failed catalog fetch is remembered
 * forever by i18next. Nothing caught it: Vitest preloads the catalogs
 * synchronously, so the failure mode does not exist there, and no
 * check ever looked at the rendered page.
 *
 * This is the check that would have. It boots the real bundle in a
 * real browser, switches the stored locale, and asserts that what
 * lands on screen is words rather than dotted identifiers.
 */

const LOCALES = ["ru", "en", "de", "uk"] as const;

// A key that leaked would look exactly like this: two or more
// dot-separated identifiers, no spaces. Ordinary copy never does.
const LOOKS_LIKE_A_KEY = /\b[a-z][a-zA-Z0-9]*(\.[a-z][a-zA-Z0-9]*){1,}\b/;

test.describe("every language renders", () => {
  for (const locale of LOCALES) {
    test(`${locale}: no raw translation keys on the public page`, async ({ page }) => {
      await page.addInitScript((lng) => {
        window.localStorage.setItem("equip:locale", lng);
      }, locale);

      await page.goto("/", { waitUntil: "domcontentloaded" });
      // The catalog is a lazy chunk; give it the same grace a reader would.
      await page.waitForTimeout(2000);

      const title = await page.title();
      expect(title, `document title in ${locale}`).not.toMatch(LOOKS_LIKE_A_KEY);

      const nav = await page.locator("header, nav").first().innerText().catch(() => "");
      if (nav.trim()) {
        expect(nav, `header text in ${locale}`).not.toMatch(LOOKS_LIKE_A_KEY);
      }

      const html = await page.locator("html").getAttribute("lang");
      expect(html, `<html lang> in ${locale}`).toBe(locale);
    });
  }

  test("a failed catalog fetch does not leave the page in key mode", async ({ page }) => {
    // Fail the first catalog request, let the rest through: the loader
    // retries, and the reader never sees an identifier.
    //
    // The pattern has to name the catalog precisely, and this is the second
    // attempt at it. The first was `/locales|i18n|\.json/`, which in a
    // production build matched no catalog at all — the bundle emits them as
    // `assets/ru-<hash>.js`, one per language — and instead aborted a chunk
    // called `i18next-<hash>.js`, the library. The case passed for months
    // while testing something other than what it says. It only came apart
    // when an unrelated import changed the chunk graph and that library
    // chunk stopped existing under that name.
    //
    // Two shapes, because this suite runs against both a dev server and a
    // built preview:
    //   dev   /src/i18n/locales/ru.json
    //   build /assets/ru-EjTN45ib.json
    const CATALOG = /\/locales\/(ru|en|de|uk)\.json|\/assets\/(ru|en|de|uk)-[\w-]+\.json/;

    let aborted: string | null = null;
    await page.route(CATALOG, (route) => {
      if (aborted === null) {
        aborted = route.request().url();
        return route.abort("failed");
      }
      return route.continue();
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);

    // A test that aborted nothing proves nothing: without this the
    // whole case passes on a page that never had a catalog request to
    // fail in the first place.
    expect(aborted, "no catalog request was intercepted").not.toBeNull();
    expect(aborted!, "aborted something that is not a catalog").toMatch(CATALOG);
    expect(await page.title()).not.toMatch(LOOKS_LIKE_A_KEY);
  });
});
