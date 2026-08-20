/// <reference types="node" />
/**
 * What a fifth language costs on this side, answered by CI.
 *
 * The counterpart of `backend/tests/test_a_fifth_language_is_refused_not_ignored.py`,
 * and the same argument. `fourLanguages.test.ts` pins the places that were
 * written for two languages and quietly assumed it; this one is the list
 * itself — every table keyed by locale, with the set of languages it
 * actually carries — so that adding a code to `SUPPORTED_LOCALES` turns red
 * once per table still to be filled, each with the work named.
 *
 * Two assertions per table, and the second is the one that keeps the first
 * honest: it must carry every language the app serves, and it must NOT
 * carry a language nobody serves. A coverage check that nothing can fail is
 * not a guard — which is exactly what the backend's typography pass had,
 * and why a fifth language would have been pointed like Russian with a
 * green pipeline.
 *
 * The strongest gates here are not in this file at all: `LOCALE_NATIVE_LABELS`,
 * `LOCALE_INTL_TAGS` and `LOCALE_LOADERS` are typed `Record<SupportedLocale, …>`,
 * so a missing language is a compile error before it is a test failure, and
 * `LANGUAGE_NAME_KEYS` was moved out of `ProfilePage.tsx` into the same shape
 * by the same change — it was `Record<string, string>` behind a
 * `?? "language.russian"`, which labelled a reader of any unknown language
 * "Russian". This file asserts them anyway, because the point is to have one
 * place that answers the question.
 *
 * Deliberately not here:
 *
 *   * `scripts/i18n-check.mjs` — its list of target bundles used to be
 *     typed out; it now reads the locales directory, so it cannot go
 *     stale and there is nothing to assert.
 *   * `e2e/every-language.spec.ts` and `e2e/the-language-you-arrived-in.spec.ts`
 *     — hand-written locale arrays, checked by Playwright rather than
 *     vitest. A fifth language simply gets no smoke coverage there, which
 *     is a gap in coverage rather than a check reporting a pass.
 *   * `index.html`'s `hreflang` links — SEO markup, no runtime behaviour.
 */

import { describe, expect, it } from "vitest"
import { readdirSync } from "node:fs"
import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"

import {
  LANGUAGE_NAME_KEYS,
  LOCALE_INTL_TAGS,
  LOCALE_NATIVE_LABELS,
  SUPPORTED_LOCALES,
  isSupportedLocale,
} from "../config"
import { LOCALES as BOOT_LOCALES } from "../../../scripts/build-locale-boot.mjs"

/** A language this app does not serve. The backend probe uses the same one. */
const FIFTH = "pl"

const localesDir = resolve(dirname(fileURLToPath(import.meta.url)), "../locales")
const bundlesOnDisk = readdirSync(localesDir)
  .filter((name) => name.endsWith(".json"))
  .map((name) => name.replace(/\.json$/, ""))

const TABLES: ReadonlyArray<{ name: string; where: string; covers: readonly string[]; fix: string }> = [
  {
    name: "LOCALE_NATIVE_LABELS",
    where: "src/i18n/config.ts",
    covers: Object.keys(LOCALE_NATIVE_LABELS),
    fix: "Name the language in itself — a reader hunting for their own scans for the word they know.",
  },
  {
    name: "LOCALE_INTL_TAGS",
    where: "src/i18n/config.ts",
    covers: Object.keys(LOCALE_INTL_TAGS),
    fix: "Give the language its BCP-47 tag, or its readers get American dates and periods for commas.",
  },
  {
    name: "the catalogs",
    where: "src/i18n/locales/*.json",
    covers: bundlesOnDisk,
    fix: "Add the bundle with full key coverage, and register it in LOCALE_LOADERS.",
  },
  {
    name: "build-locale-boot LOCALES",
    where: "frontend/scripts/build-locale-boot.mjs",
    covers: BOOT_LOCALES,
    fix: "Add the language, or its readers get somebody else's title and description on the first paint.",
  },
  {
    name: "LANGUAGE_NAME_KEYS",
    where: "src/i18n/config.ts",
    covers: Object.keys(LANGUAGE_NAME_KEYS),
    fix: "Add the key that names the language on the profile page.",
  },
]

describe("a fifth language", () => {
  it("is not one this app serves — everything below depends on that", () => {
    expect(isSupportedLocale(FIFTH)).toBe(false)
  })

  it.each(TABLES.map((table) => [table.name, table] as const))(
    "%s carries every language the app serves",
    (_name, table) => {
      const missing = SUPPORTED_LOCALES.filter((locale) => !table.covers.includes(locale))
      expect(missing, `${table.where} has nothing for ${missing.join(", ")}. ${table.fix}`).toEqual([])
    },
  )

  it.each(TABLES.map((table) => [table.name, table] as const))(
    "%s does not carry a language nobody serves",
    (_name, table) => {
      // Otherwise the assertion above is satisfied by a table that
      // accepts anything, and a table that accepts anything cannot fail.
      expect(table.covers).not.toContain(FIFTH)
    },
  )
})
