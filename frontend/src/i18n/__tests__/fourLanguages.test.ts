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
 *     renders as a code;
 *   * the calendar kept a second copy of that same two-language map, in
 *     three functions, so its month names, weekday labels and clock went
 *     on being American for German and Ukrainian readers long after the
 *     date helpers were fixed;
 *   * numbers were `toFixed()`, which writes a period — and ru, de and uk
 *     all write a comma. That one lands on a printed grade sheet.
 *
 * The file pins `i18n/format.ts` and `i18n/number.ts` (the helpers) plus
 * `pages/Calendar` (the place that had its own), because a rival map is the
 * shape this class of bug takes: nothing errors, nobody is alerted, the
 * reader is simply handed somebody else's conventions.
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
import { formatNumber, formatPercent } from "../number"
import { getDayShortName, getMonthName } from "@/pages/Calendar/constants"
import { formatTime } from "@/pages/Calendar/utils"

const SAMPLE = new Date("2026-08-15T10:30:00Z")

/** Every language, one at a time, restoring nothing — `afterAll` does that. */
async function forEachLanguage(run: (locale: string) => void | Promise<void>): Promise<void> {
  for (const locale of SUPPORTED_LOCALES) {
    await i18n.changeLanguage(locale)
    await run(locale)
  }
}

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

/**
 * The calendar had its own two-language map, in three separate functions,
 * and nothing pointed at it — `format.ts` was fixed and the calendar was
 * not. These are the three.
 */
describe("the calendar reads in the language the rest of the app is in", () => {
  // August, and a Saturday. Picked because they are the cases where the
  // languages actually diverge: "August" is shared by en and de, "серпень"
  // is not, and "Sat" / "Sa" / "сб" are three different abbreviations.
  const AUGUST = 7

  it("names the month in each language, not in English", () => {
    expect(getMonthName(AUGUST, "de")).toBe("August")
    expect(getMonthName(AUGUST, "ru")).toBe("август")
    expect(getMonthName(AUGUST, "uk")).toBe("серпень")
    expect(getMonthName(AUGUST, "en")).toBe("August")
    // A Ukrainian used to be shown "August" here — the same word English
    // gets, from the same `en-US` the fallback handed them.
    expect(getMonthName(AUGUST, "uk")).not.toBe(getMonthName(AUGUST, "en"))
  })

  it("abbreviates weekdays the way each language abbreviates them", () => {
    const SATURDAY = 6
    expect(getDayShortName(SATURDAY, "en")).toBe("Sat")
    // German cuts to two letters, not three.
    expect(getDayShortName(SATURDAY, "de")).toBe("Sa")
    expect(getDayShortName(SATURDAY, "ru")).toBe("сб")
    expect(getDayShortName(SATURDAY, "uk")).toBe("сб")
  })

  it("resolves a regional tag the same way the rest of the app does", () => {
    // The old map keyed on `startsWith("ru")`; everything else, `de-AT`
    // included, fell into `en-US`.
    expect(getMonthName(AUGUST, "de-AT")).toBe(getMonthName(AUGUST, "de"))
    expect(getMonthName(AUGUST, "uk-UA")).toBe(getMonthName(AUGUST, "uk"))
  })

  it("shows a 14:30 lesson as 14:30 to everyone who reads a 24-hour clock", async () => {
    // Local time on purpose — the agenda shows the reader's own clock, so
    // the hour depends on the machine's timezone and only the *shape* is
    // assertable. That shape is the defect: a German was shown "02:30 PM".
    const at = "2026-08-15T14:30:00"

    for (const locale of ["de", "ru", "uk"]) {
      await i18n.changeLanguage(locale)
      expect(formatTime(at)).toMatch(/^\d{2}:\d{2}$/)
      expect(formatTime(at)).not.toMatch(/[AP]M/i)
    }

    await i18n.changeLanguage("en")
    expect(formatTime(at)).toMatch(/[AP]M/i)
  })
})

/**
 * Three of the four languages write the decimal separator as a comma.
 * Every grade in the app was `toFixed()`, which is specified to write a
 * period — including the grades printed on a signed grade sheet.
 */
describe("numbers are written the way each audience writes them", () => {
  it("uses a comma where the language uses a comma", async () => {
    await i18n.changeLanguage("de")
    expect(formatNumber(86.5)).toBe("86,5")
    await i18n.changeLanguage("ru")
    expect(formatNumber(86.5)).toBe("86,5")
    await i18n.changeLanguage("uk")
    expect(formatNumber(86.5)).toBe("86,5")
    await i18n.changeLanguage("en")
    expect(formatNumber(86.5)).toBe("86.5")
  })

  it("keeps the decimal places fixed so a column of grades lines up", async () => {
    await i18n.changeLanguage("en")
    expect(formatNumber(90)).toBe("90.0")
    expect(formatNumber(90, 0)).toBe("90")
    expect(formatPercent(90)).toBe("90.0%")
  })

  it("puts the percent sign straight after the number, in every language", async () => {
    // Deliberate: `Intl`'s percent style would insert a non-breaking space
    // for de / ru / uk. These strings sit in fixed-width table cells and on
    // a printed page, so the module changes the decimal mark and nothing
    // else — this pins that decision.
    await forEachLanguage(() => {
      expect(formatPercent(86.5)).toMatch(/^86[.,]5%$/)
    })
  })

  it("never renders NaN or Infinity at a reader", async () => {
    await forEachLanguage(() => {
      expect(formatNumber(Number.NaN)).toBe("")
      expect(formatPercent(Number.POSITIVE_INFINITY)).toBe("")
    })
  })

  it("gives every language its own notation, not one shared string", async () => {
    const rendered = new Set<string>()
    await forEachLanguage(() => {
      rendered.add(formatPercent(86.5))
    })
    // Two shapes: "86.5%" for en, "86,5%" for the other three. A single
    // entry would mean the helper is ignoring the active language.
    expect(rendered.size).toBe(2)
  })
})
