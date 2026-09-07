import { describe, expect, it } from "vitest"
import ru from "../locales/ru.json"

/**
 * Two things the Russian catalog kept getting wrong, both invisible to
 * anyone reading the product in English.
 *
 * 1. A comma before «чтобы». Six strings shipped without it, including the
 *    first sentence a new account ever reads ("Несколько настроек чтобы всё
 *    подготовить"). It is not a stylistic preference — the comma is
 *    mandatory before a subordinate clause.
 *
 * 2. One voice. The landing page addressed the reader as «ты»
 *    ("Зарегистрируйся", "который тебе интересен") while every other screen
 *    used «вы» — and Ukrainian, the closest language in the set, was on
 *    «ви» throughout. A product that switches how it addresses someone
 *    between two screens reads as two products.
 */

type Json = { [key: string]: string | Json }

function walk(node: Json, path = ""): Array<[string, string]> {
  return Object.entries(node).flatMap(([key, value]) => {
    const here = path ? `${path}.${key}` : key
    return typeof value === "string" ? [[here, value] as [string, string]] : walk(value, here)
  })
}

const ENTRIES = walk(ru as Json)

describe("the Russian catalog", () => {
  it("puts a comma before «чтобы»", () => {
    // With the comma the character before the space is «,»; without it, a
    // letter. That is the whole rule. «Для того чтобы» is the one fixed
    // phrase that takes no comma there, so it is removed before the test.
    //
    // NOT `\b`: JavaScript computes word boundaries over ASCII, so `чтобы\b`
    // never matches at all and the check silently passes on everything. Both
    // rules here were written that way first and caught nothing — the
    // mutation run is the only reason this reads `(?!\p{L})` today.
    const offenders = ENTRIES.filter(([, value]) =>
      /\p{L}\s+чтобы(?!\p{L})/u.test(value.replace(/для того\s+чтобы/giu, "")),
    )

    expect(
      offenders.map(([k, v]) => `${k}: ${v}`),
      "Russian requires a comma before a «чтобы» clause.",
    ).toEqual([])
  })

  it("addresses the reader as «вы», never «ты»", () => {
    // Imperatives in the singular and the informal pronoun. The formal
    // imperative («откройте») does not match, which is the point.
    const informal =
      /(?<!\p{L})(зарегистрируйся|войди|открой|начни|выбери|пройди|нажми|попробуй|создай|запишись|проверь|изучай|проходи|забирай|твой|твоя|твои|твоё|тебе|тебя)(?!\p{L})/iu

    const offenders = ENTRIES.filter(([, value]) => informal.test(value))

    expect(
      offenders.map(([k, v]) => `${k}: ${v}`),
      "The product says «вы» everywhere else; a screen on «ты» reads as a different product.",
    ).toEqual([])
  })
})
