import { beforeAll, describe, expect, it } from "vitest"

import i18n from "@/i18n/config"
import type { ReadinessCheck } from "@/services/courseReadiness"
import { readinessMessage } from "@/pages/Teacher/editor/readinessMessage"

/**
 * The checklist and the "Publish with issues?" dialog both used to print
 * the affirmative sentence for a check that was failing — "The course has
 * a cover image." under a heading listing what is *missing*. These pin
 * the rule: a failing check says what is missing, a passed one keeps the
 * sentence it gets crossed out with, and a key the frontend has never
 * heard of falls back instead of rendering nothing.
 *
 * Cyrillic assertions avoid ``\b`` on purpose: JavaScript's word boundary
 * is ASCII-only and never matches next to a Cyrillic letter.
 */

function check(over: Partial<ReadinessCheck>): ReadinessCheck {
  return {
    id: over.id ?? "x",
    severity: over.severity ?? "critical",
    passed: over.passed ?? false,
    message_key: over.message_key ?? "courseReadiness.checks.hasCoverImage",
    subject: over.subject ?? null,
    action: over.action ?? null,
  }
}

describe("readinessMessage", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru")
  })

  it("says what is missing while the check is failing", () => {
    const text = readinessMessage(i18n.t, check({ passed: false }))
    expect(text).toMatch(/(?<!\p{L})нет обложки(?!\p{L})/u)
    expect(text).not.toMatch(/(?<!\p{L})есть обложка(?!\p{L})/u)
  })

  it("keeps the affirmative sentence once the check has passed", () => {
    const text = readinessMessage(i18n.t, check({ passed: true }))
    expect(text).toMatch(/(?<!\p{L})есть обложка(?!\p{L})/u)
  })

  it("interpolates the subject title into the missing phrasing", () => {
    const text = readinessMessage(
      i18n.t,
      check({
        message_key: "courseReadiness.checks.moduleHasChapters",
        subject: { type: "module", id: "m-1", title: "Бытие" },
      }),
    )
    expect(text).toBe("В «Бытие» нет ни одной главы.")
  })

  it("does not say the course is on every language when it is not", () => {
    const text = readinessMessage(
      i18n.t,
      check({ message_key: "courseReadiness.checks.translationsComplete" }),
    )
    expect(text).toMatch(/(?<!\p{L})ещё не на всех языках(?!\p{L})/u)
  })

  it("falls back to the affirmative key for a check without a missing twin", () => {
    // A check the backend ships before the frontend learns its
    // ``missing`` twin must still read as a sentence, not a raw key.
    i18n.addResourceBundle(
      "ru",
      "translation",
      { courseReadiness: { checks: { brandNew: "У курса есть новое свойство." } } },
      true,
      true,
    )
    const text = readinessMessage(
      i18n.t,
      check({ message_key: "courseReadiness.checks.brandNew" }),
    )
    expect(text).toBe("У курса есть новое свойство.")
  })
})
