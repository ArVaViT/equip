import { describe, expect, it } from "vitest"
import { printedResult } from "../resultLabel"
import type { SheetRow } from "@/types"

/** The component passes i18next's `t`; here the key itself is the assertion. */
const t = (key: string) => key

function row(over: Partial<SheetRow> = {}): SheetRow {
  return {
    student_id: "s1",
    student_name: "Иванов Иван",
    result_state: "pass",
    official_code: null,
    official_score: null,
    is_override: false,
    ...over,
  }
}

describe("printedResult", () => {
  it("prints the scheme's own symbol", () => {
    // «A», «4», «зачёт» — what the school grades in, and what a transcript
    // will later have to match.
    expect(printedResult(row({ official_code: "4" }), t).text).toBe("4")
  })

  it("prints a percentage for a course that has no symbols", () => {
    expect(printedResult(row({ official_score: "87.50" }), t).text).toBe("87.5%")
  })

  it.each([
    ["pass", "vedomost.result.pass"],
    ["fail", "vedomost.result.fail"],
    ["completion_pass", "vedomost.result.completionPass"],
    ["not_attested", "vedomost.result.notAttested"],
  ])("prints the verdict in words for %s", (state, key) => {
    expect(printedResult(row({ result_state: state as SheetRow["result_state"] }), t).text).toBe(key)
  })

  it("never leaves the cell blank", () => {
    // An empty cell on a signed page reads as an oversight. «Не аттестован»
    // says a person still has to decide, which is the truth.
    const printed = printedResult(row({ result_state: "not_attested" }), t)

    expect(printed.text).toBeTruthy()
  })

  it("carries the hand-set glyph through every shape of result", () => {
    // The one thing a signing director should not have to ask about.
    expect(printedResult(row({ official_code: "B", is_override: true }), t).isOverride).toBe(true)
    expect(printedResult(row({ official_score: "60.00", is_override: true }), t).isOverride).toBe(
      true,
    )
    expect(printedResult(row({ result_state: "fail", is_override: true }), t).isOverride).toBe(true)
  })

  it("prefers the symbol over the state when both are present", () => {
    // A frozen row carries both: «B» and "pass". The page shows what the
    // school grades in, not the machine's verdict word.
    expect(printedResult(row({ official_code: "B", result_state: "pass" }), t).text).toBe("B")
  })

  it("falls back to not-attested for a state it does not recognise", () => {
    // Rather than printing a raw enum value onto a document.
    expect(printedResult(row({ result_state: "щ" as SheetRow["result_state"] }), t).text).toBe(
      "vedomost.result.notAttested",
    )
  })
})
