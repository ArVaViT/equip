/**
 * The edges of serving four languages instead of two.
 *
 * Adding German and Ukrainian to `SUPPORTED_LOCALES` is one line. What it
 * does NOT do is find the places that were written when there were two and
 * quietly assume it still. This file pins the ones that were found, so a
 * fifth language cannot re-open them:
 *
 *   * dates asked `startsWith("ru") ? "ru-RU" : "en-US"`, so a German
 *     reader was shown American dates — "August 15, 2026" where they
 *     expect "15. August 2026";
 *   * a browser announcing `de-DE` has to resolve to `de`, not fall
 *     through to the default;
 *   * every served locale needs an Intl tag and a native label, or it
 *     renders as a code.
 */

import { afterAll, describe, expect, it } from "vitest"

import i18n, {
  DEFAULT_LOCALE,
  LOCALE_INTL_TAGS,
  LOCALE_NATIVE_LABELS,
  SUPPORTED_LOCALES,
  activeIntlTag,
  isSupportedLocale,
} from "../config"
import { formatDate, formatDateLong } from "../format"

const SAMPLE = new Date("2026-08-15T10:30:00Z")

afterAll(async () => {
  await i18n.changeLanguage(DEFAULT_LOCALE)
})

describe("every served language is fully described", () => {
  it.each(SUPPORTED_LOCALES)("%s has an Intl tag", (locale) => {
    expect(LOCALE_INTL_TAGS[locale]).toMatch(/^[a-z]{2}-[A-Z]{2}$/)
  })

  it.each(SUPPORTED_LOCALES)("%s has a native label", (locale) => {
    expect(LOCALE_NATIVE_LABELS[locale]?.trim()).toBeTruthy()
  })

  it("labels are written in their own language, not translated", () => {
    expect(LOCALE_NATIVE_LABELS.de).toBe("Deutsch")
    expect(LOCALE_NATIVE_LABELS.uk).toBe("Українська")
  })
})

describe("regional browser variants resolve to a served language", () => {
  it.each([
    ["de-DE", "de"],
    ["de-AT", "de"],
    ["uk-UA", "uk"],
    ["ru-RU", "ru"],
    ["en-GB", "en"],
    ["EN-US", "en"],
  ])("%s → %s", (announced, expected) => {
    expect(activeIntlTag(announced)).toBe(LOCALE_INTL_TAGS[expected as never])
  })

  it("an unserved language falls back rather than breaking", () => {
    expect(isSupportedLocale("fr")).toBe(false)
    expect(activeIntlTag("fr-FR")).toBe(LOCALE_INTL_TAGS[DEFAULT_LOCALE])
  })
})

describe("dates read the way each audience reads them", () => {
  it("German gets German order, not American", async () => {
    await i18n.changeLanguage("de")
    const long = formatDateLong(SAMPLE)
    expect(long).toContain("August")
    // German writes the day first: "15. August 2026".
    expect(long.indexOf("15")).toBeLessThan(long.indexOf("August"))
  })

  it("Ukrainian gets Ukrainian month names", async () => {
    await i18n.changeLanguage("uk")
    expect(formatDateLong(SAMPLE)).toContain("серпня")
  })

  it("Russian still gets Russian", async () => {
    await i18n.changeLanguage("ru")
    expect(formatDateLong(SAMPLE)).toContain("август")
  })

  it("English still gets English", async () => {
    await i18n.changeLanguage("en")
    expect(formatDateLong(SAMPLE)).toContain("August")
  })

  it("the technical timestamp stays identical in every language", async () => {
    const rendered = new Set<string>()
    for (const locale of SUPPORTED_LOCALES) {
      await i18n.changeLanguage(locale)
      rendered.add(formatDate(SAMPLE))
    }
    // The whole point of the canonical format: one string, every locale.
    expect(rendered.size).toBe(1)
  })
})
