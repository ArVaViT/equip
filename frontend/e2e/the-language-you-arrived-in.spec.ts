import { test, expect } from "@playwright/test";

/**
 * A stranger opens the site and reads it in their own language.
 *
 * This is the promise the product is built on, and the one place it can
 * be broken silently: the visitor has never been here, has nothing
 * stored, and all the site knows about them is the language their
 * browser asks for. If a German lands on Russian, or an American on
 * Ukrainian, nothing errors and nothing alerts — they just leave.
 *
 * The existing language spec seeds `localStorage` first, so it tests a
 * returning reader. This one tests arrival: a fresh browser context per
 * language, no storage, nothing but `Accept-Language` and
 * `navigator.language`.
 *
 * Two things are asserted, and both matter:
 *
 * 1. The **first frame**. `<html lang>`, the tab title and the meta
 *    description are set by `/locale-boot.js` before the bundle loads,
 *    so they are checked immediately after `domcontentloaded` — the
 *    state a visitor on a slow connection actually stares at.
 * 2. The **rendered page**, once React has booted: real words from
 *    that language's catalog, and none of the tell-tale words of
 *    another one.
 */

type Probe = {
  /** What the browser asks for. */
  browser: string;
  /** What the site must decide. */
  expected: "ru" | "en" | "de" | "uk";
  /** A word only this language's catalog produces on the public page. */
  expectWord: RegExp;
  /** Words that would mean the visitor was handed the wrong language. */
  rejectWords: RegExp;
  /** Part of the tab title `/locale-boot.js` sets before React exists. */
  expectTitle: RegExp;
};

const PROBES: Probe[] = [
  {
    browser: "de-DE",
    expected: "de",
    expectWord: /Bibel|Anmelden|Kurse/i,
    rejectWords: /Библии|Войти|Курсы|Вивчення/i,
    expectTitle: /Bibelstudium/i,
  },
  {
    browser: "en-US",
    expected: "en",
    expectWord: /Bible|Sign in|Courses/i,
    rejectWords: /Библии|Войти|Bibelstudium|Вивчення/i,
    expectTitle: /study the Bible/i,
  },
  {
    browser: "uk-UA",
    expected: "uk",
    expectWord: /Біблії|Увійти|Курси/i,
    rejectWords: /Bibelstudium|изучение Библии/i,
    expectTitle: /вивчення Біблії/i,
  },
  {
    browser: "ru-RU",
    expected: "ru",
    expectWord: /Библии|Войти|Курсы/i,
    rejectWords: /Bibelstudium|вивчення Біблії/i,
    expectTitle: /изучение Библии/i,
  },
];

for (const probe of PROBES) {
  test.describe(`a visitor whose browser says ${probe.browser}`, () => {
    test.use({ locale: probe.browser });

    test("gets that language, from the first frame onward", async ({
      page,
    }) => {
      // No stored choice, no session: this is the first visit.
      await page.context().clearCookies();

      await page.goto("/", { waitUntil: "domcontentloaded" });

      // ── the first frame, before the bundle has had a chance to run ──
      expect(await page.title(), `tab title for ${probe.browser}`).toMatch(
        probe.expectTitle,
      );
      expect(
        await page.locator("html").getAttribute("lang"),
        `<html lang> for ${probe.browser}`,
      ).toBe(probe.expected);

      // ── and once the app is up ──
      await page.waitForLoadState("networkidle");
      const body = await page.locator("body").innerText();

      expect(body, `visible copy for ${probe.browser}`).toMatch(
        probe.expectWord,
      );
      expect(
        body,
        `a ${probe.browser} visitor was shown another language`,
      ).not.toMatch(probe.rejectWords);
      expect(await page.locator("html").getAttribute("lang")).toBe(
        probe.expected,
      );
    });
  });
}

test.describe("a visitor whose language the platform does not serve", () => {
  test.use({ locale: "pl-PL" });

  test("is answered in English, not in Russian", async ({ page }) => {
    // The owner's decision, checked from outside: a visitor's language
    // comes from their browser, and when we do not serve it the last
    // resort is English. This used to accept any of the four served
    // languages, which passed just as happily on the Russian this
    // platform actually handed a Polish visitor.
    await page.goto("/", { waitUntil: "domcontentloaded" });

    expect(
      await page.locator("html").getAttribute("lang"),
      "a visitor whose language we do not serve is answered in English",
    ).toBe("en");

    await page.waitForLoadState("networkidle");
    // Deliberately not asserting the tab title at the first frame the way
    // the per-language probes above do: by the time this runs the app has
    // usually booted and replaced the boot script's title with the current
    // page's ("Home — Equip"), so the assertion would be a race. The boot
    // title for an unserved language is covered without a browser, in
    // `src/i18n/__tests__/localeBoot.test.ts`.
    expect(
      await page.title(),
      "the tab title settled in some other language",
    ).not.toMatch(/Главная|Головна|Startseite|Библии|Біблії/i);
    const body = await page.locator("body").innerText();
    expect(body.trim().length, "the page rendered something").toBeGreaterThan(
      20,
    );
    expect(body, "and the copy is English too, not just <html lang>").toMatch(
      /Bible|Sign in|Courses/i,
    );
    expect(
      body,
      "a visitor we know nothing about was handed Russian",
    ).not.toMatch(/Библии|Войти|Курсы|Bibelstudium|вивчення Біблії/i);
    // A raw i18next key would look like `header.home`; ordinary copy does not.
    expect(body).not.toMatch(/\b[a-z][a-zA-Z0-9]*(\.[a-z][a-zA-Z0-9]*){1,}\b/);
  });
});

test.describe("a returning reader outranks the browser", () => {
  test.use({ locale: "de-DE" });

  test("keeps the language they chose last time", async ({ page }) => {
    // The rule: a stated preference beats a detected one. A German
    // browser must not undo somebody's explicit switch to Ukrainian.
    await page.addInitScript(() => {
      window.localStorage.setItem("equip:locale", "uk");
    });

    await page.goto("/", { waitUntil: "domcontentloaded" });

    expect(await page.locator("html").getAttribute("lang")).toBe("uk");

    // Two titles are correct here, and which one you catch is a race the
    // test should not be trying to win: locale-boot sets the marketing
    // title before the bundle loads, and the router replaces it with the
    // page's own the moment it does. Both are Ukrainian, which is the
    // thing being asserted. Pinning the first one made this fail against
    // a perfectly correct app that had simply finished loading — the
    // received title was "Головна — Equip".
    expect(await page.title()).toMatch(/вивчення Біблії|Головна/i);
    // And it must not be either of the languages that could have won
    // instead: the browser's German, or the default Russian.
    expect(await page.title()).not.toMatch(
      /Bibel|Startseite|Главная|изучение/i,
    );
  });
});
