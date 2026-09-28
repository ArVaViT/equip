import { describe, expect, it } from "vitest"

import { LOCALE_MENU_ORDER, SUPPORTED_LOCALES } from "../config"

describe("the language menu", () => {
  it("lists every served language exactly once, English first", () => {
    // A language missing here is a language nobody can pick; a duplicate is
    // two identical rows. Sorting both sides compares the sets.
    expect([...LOCALE_MENU_ORDER].sort()).toEqual([...SUPPORTED_LOCALES].sort())
    expect(LOCALE_MENU_ORDER).toEqual(["en", "ru", "uk", "de"])
  })
})
