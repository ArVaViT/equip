import { test, expect } from "@playwright/test";

/**
 * Nothing pushes a phone sideways.
 *
 * A page one pixel wider than the phone scrolls horizontally, and on a
 * touch screen that reads as breakage: the reader swipes down the text
 * and the whole column drifts left. Production shipped it — the legal
 * pages' `<h1>` was `text-3xl`, and "Политика конфиденциальности" is a
 * single 26-character word that does not fit 358px at 30px serif. It
 * pushed the document to 397px on a 390px viewport. No test looked,
 * because every test until now ran at desktop width.
 *
 * German is the reason this runs in four languages rather than one:
 * "Datenschutzerklärung" and "Nutzungsbedingungen" are longer than
 * anything English would have caught.
 *
 * 390px is the iPhone 14/15 class; 320px is the narrowest phone still
 * in the wild (iPhone SE 1st gen, a folded Galaxy Fold) and the width
 * where a heading that merely *fits* at 390 gives up.
 */

const LOCALES = ["ru", "en", "de", "uk"] as const;
const PUBLIC_PAGES = ["/", "/login", "/register", "/courses", "/verify", "/privacy", "/terms"];
const WIDTHS = [390, 320];

/** Names the element that overflows, so a failure points at a file rather than a number. */
async function measureOverflow(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const root = document.documentElement;
    const vw = root.clientWidth;
    const offenders: Array<{ tag: string; cls: string; right: number; text: string }> = [];
    for (const el of Array.from(document.querySelectorAll("body *"))) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      // A visually-hidden skip link is laid out off-canvas on purpose.
      const style = window.getComputedStyle(el);
      if (style.position === "fixed" || style.position === "absolute") continue;
      if (r.right > vw + 1) {
        offenders.push({
          tag: el.tagName.toLowerCase(),
          cls: String((el as HTMLElement).className).slice(0, 60),
          right: Math.round(r.right),
          text: (el.textContent ?? "").trim().slice(0, 40),
        });
      }
    }
    return { vw, scrollWidth: root.scrollWidth, offenders: offenders.slice(0, 5) };
  });
}

for (const width of WIDTHS) {
  test.describe(`${width}px viewport`, () => {
    test.use({ viewport: { width, height: 844 } });

    for (const locale of LOCALES) {
      test(`${locale}: no public page scrolls sideways`, async ({ page }) => {
        await page.addInitScript((lng) => {
          window.localStorage.setItem("equip:locale", lng);
        }, locale);

        for (const path of PUBLIC_PAGES) {
          await page.goto(path, { waitUntil: "domcontentloaded" });
          // The catalog is a lazy chunk; a heading measured before it
          // arrives is still in the fallback language and proves nothing.
          await page.waitForTimeout(1500);

          const { vw, scrollWidth, offenders } = await measureOverflow(page);
          const blame = offenders
            .map((o) => `<${o.tag} class="${o.cls}"> ends at ${o.right}px — "${o.text}"`)
            .join("; ");
          expect(
            scrollWidth,
            `${path} in ${locale} at ${width}px: document is ${scrollWidth}px wide in a ${vw}px viewport. ${blame}`,
          ).toBeLessThanOrEqual(vw + 1);
        }
      });
    }
  });
}
