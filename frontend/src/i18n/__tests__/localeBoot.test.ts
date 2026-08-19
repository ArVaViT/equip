/**
 * The language decision that happens before the app exists.
 *
 * `public/locale-boot.js` runs ahead of the bundle and sets the three things
 * that exist that early — `<html lang>`, the tab title, the meta
 * description. It is generated, so this suite runs the generator's output
 * rather than the committed copy of it, and `scripts/i18n-check.mjs` is what
 * keeps the two the same.
 *
 * The case that motivated the file: the boot script read only
 * `equip:locale`, while `i18n/config.ts` migrates `bible-school:locale`
 * onto it — at module load, which is *after* the first paint. A returning
 * reader who still carried only the old key was decided by their browser
 * for one frame and then flipped by the bundle to the language they had
 * actually chosen. A real flash, and it hit the people who had been here
 * longest.
 */

import { beforeEach, describe, expect, it } from "vitest"

import { LEGACY_STORAGE_KEY, STORAGE_KEY, buildLocaleBoot } from "../../../scripts/build-locale-boot.mjs"
import { DEFAULT_LOCALE, SUPPORTED_LOCALES } from "../config"

const SCRIPT = buildLocaleBoot()

/** Minimal `localStorage` stand-in — the boot script only reads. */
function storage(entries: Record<string, string> = {}) {
  return {
    getItem: (key: string) => entries[key] ?? null,
  }
}

/**
 * Run the generated script against a made-up browser and report what the
 * first frame would have looked like.
 *
 * `new Function` with the three globals as parameters keeps the real
 * document out of it, so one case cannot leak into the next through
 * `document.documentElement.lang`.
 */
function boot(options: {
  stored?: Record<string, string>
  languages?: string[]
  throwOnStorage?: boolean
}): { lang: string; title: string; description: string } {
  const doc = {
    documentElement: { lang: "" },
    title: "",
    description: "",
    querySelector: (selector: string) =>
      selector === 'meta[name="description"]'
        ? { setAttribute: (_name: string, value: string) => void (doc.description = value) }
        : null,
  }
  const fakeWindow = {
    localStorage: options.throwOnStorage
      ? {
          getItem() {
            throw new Error("blocked")
          },
        }
      : storage(options.stored),
  }
  const fakeNavigator = { languages: options.languages ?? [], language: options.languages?.[0] ?? "" }

  new Function("window", "navigator", "document", SCRIPT)(fakeWindow, fakeNavigator, doc)
  return { lang: doc.documentElement.lang, title: doc.title, description: doc.description }
}

describe("locale-boot picks the language before the bundle can", () => {
  it("honours a stored choice over the browser", () => {
    expect(boot({ stored: { [STORAGE_KEY]: "uk" }, languages: ["de-DE"] }).lang).toBe("uk")
  })

  it("honours the pre-rebrand key the bundle has not migrated yet", () => {
    // The flash: this used to return "de" for one frame and then flip to
    // "uk" the moment `i18n/config.ts` evaluated its migration.
    expect(boot({ stored: { [LEGACY_STORAGE_KEY]: "uk" }, languages: ["de-DE"] }).lang).toBe("uk")
  })

  it("prefers the current key when a reader carries both", () => {
    // Mid-migration: config.ts copies across only when the new key is
    // empty, so the new key is the more recent fact whenever both exist.
    expect(
      boot({ stored: { [STORAGE_KEY]: "en", [LEGACY_STORAGE_KEY]: "uk" } }).lang,
    ).toBe("en")
  })

  it("ignores a stored value the app does not serve", () => {
    expect(boot({ stored: { [LEGACY_STORAGE_KEY]: "fr" }, languages: ["de-DE"] }).lang).toBe("de")
  })

  it("falls through to the browser, then to the default", () => {
    expect(boot({ languages: ["de-AT", "en-GB"] }).lang).toBe("de")
    expect(boot({ languages: ["fr-FR", "es-ES"] }).lang).toBe(DEFAULT_LOCALE)
    expect(boot({}).lang).toBe(DEFAULT_LOCALE)
  })

  it("survives a browser that refuses storage entirely", () => {
    // Private mode, blocked cookies — not knowing has to be survivable, the
    // script runs before anything that could catch a throw.
    expect(boot({ throwOnStorage: true, languages: ["uk-UA"] }).lang).toBe("uk")
  })

  it("sets the tab title and description in the same language it picked", () => {
    for (const locale of SUPPORTED_LOCALES) {
      const frame = boot({ stored: { [LEGACY_STORAGE_KEY]: locale } })
      expect(frame.lang).toBe(locale)
      expect(frame.title).toBeTruthy()
      expect(frame.description).toBeTruthy()
    }
    // And they are actually different per language — a shared string would
    // pass every assertion above while showing everyone Russian.
    const titles = new Set(
      SUPPORTED_LOCALES.map((locale) => boot({ stored: { [STORAGE_KEY]: locale } }).title),
    )
    expect(titles.size).toBe(SUPPORTED_LOCALES.length)
  })
})

describe("the generator and the committed file agree", () => {
  let committed: string

  beforeEach(async () => {
    const { readFileSync } = await import("node:fs")
    const { OUT_FILE } = await import("../../../scripts/build-locale-boot.mjs")
    committed = readFileSync(OUT_FILE, "utf8")
  })

  it("public/locale-boot.js is what the generator produces today", () => {
    // `scripts/i18n-check.mjs` asserts this too, in CI. Asserting it here as
    // well means a developer who edits the generator and forgets to run it
    // finds out from the test suite they were already running.
    expect(committed).toBe(SCRIPT)
  })
})
