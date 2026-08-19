import type { SheetRow } from "@/types"
import { formatPercent } from "@/i18n/number"

export interface PrintedResult {
  /** What goes in the result column. Already the document's own words. */
  text: string
  /** True when a teacher set it by hand — the director-visible glyph. */
  isOverride: boolean
}

/** i18n keys for a verdict with no symbol behind it. */
const STATE_KEY: Record<string, string> = {
  completion_pass: "vedomost.result.completionPass",
  not_attested: "vedomost.result.notAttested",
  pass: "vedomost.result.pass",
  fail: "vedomost.result.fail",
}

/**
 * The result column of a signed page.
 *
 * Rules, in order:
 *
 * 1. **A symbol prints as itself.** «A», «4», «зачёт» — the scheme's own word,
 *    because that is what the school grades in and what a transcript will
 *    later have to match.
 * 2. **A percentage prints as a percentage**, for a `percent` course that has
 *    no symbols.
 * 3. **Otherwise the verdict in words.** «Не аттестован» is neither a blank
 *    nor a zero: it says a person still has to decide, and an empty cell on a
 *    signed page reads as an oversight.
 *
 * Nothing here recomputes anything. Every input came off the frozen row.
 */
export function printedResult(row: SheetRow, t: (key: string) => string): PrintedResult {
  if (row.official_code) {
    return { text: row.official_code, isOverride: row.is_override }
  }
  if (row.official_score !== null && row.official_score !== undefined) {
    return { text: formatPercent(Number(row.official_score), 1), isOverride: row.is_override }
  }
  return {
    text: t(STATE_KEY[row.result_state] ?? "vedomost.result.notAttested"),
    isOverride: row.is_override,
  }
}
