/**
 * The one place a grade percentage becomes text.
 *
 * There were three. The progress board rounded in Python, the Grade Table
 * rounded again with `Math.round`, and the Summary tab printed one decimal —
 * so a student on 86.5 read 86%, 87% and 86.5% on three screens, because
 * Python rounds a .5 tie to even and JavaScript rounds it up.
 *
 * Two decimals, because that is the precision the letter is chosen at. The
 * backend rounds every score to two places and reads the band table from
 * that number; printing one place put 89.95 on the page as «90,0% B» next to
 * a scale that says 90 is an A. The teacher was left holding two facts that
 * contradict each other, and the one they could see was the wrong one. The
 * number is never rounded again before the symbol is chosen (2026-10-19).
 */
import { formatPercent } from "@/i18n/number"

/** Decimal places a grade is shown at — the backend's own rounding. */
export const GRADE_FRACTION_DIGITS = 2

export function formatGradePercent(score: number, locale?: string): string {
  // In the reader's own notation. `toFixed` always emits a period; ru, de and
  // uk all write 86,50. This is the number that ends up printed on a signed
  // grade sheet — ``locale`` is for that document, which speaks its own
  // language rather than the interface's.
  return formatPercent(score, GRADE_FRACTION_DIGITS, locale)
}
