/**
 * Number formatting for the language on screen.
 *
 * Sibling of `format.ts`, and it exists for one reason: three of the four
 * languages this product serves write the decimal separator as a comma.
 * Russian, German and Ukrainian readers all write 86,5 — and every grade,
 * percentage and average in the app was `toFixed()`, which is defined to
 * emit a period no matter who is reading.
 *
 * It looks like a small thing on a dashboard. It is not a small thing on the
 * ведомость: the grade sheet is printed, signed by the teacher and the
 * director, and handed to a student as a record. A document in German that
 * says `86.5%` is a document that was typed by someone who was not paying
 * attention, and that is the first impression it makes on whoever it is
 * shown to.
 *
 * # Display only
 *
 * Nothing here goes near a stored value or a request body. `Intl` output is
 * for eyes; `86,5` parsed back with `Number()` is `86`. Everything sent to
 * the API keeps using the raw number.
 *
 * # Why the percent sign stays a literal
 *
 * `Intl.NumberFormat` has a `style: "percent"`, and it would put a
 * non-breaking space before the sign for de / ru / uk — which is correct
 * typography. It is deliberately not used: these strings sit in fixed-width
 * table cells and on a printed page, an invisible U+00A0 is a character
 * nobody can see but every diff and every grep can, and the callers already
 * own the `%` glyph. This module changes the decimal mark and nothing else.
 */

import i18n, { activeIntlTag } from "./config"

/**
 * A number with the active language's decimal separator, at a fixed number
 * of decimal places.
 *
 * Fixed rather than "up to": a column of grades reading 86,5 / 90 / 78,2 is
 * harder to scan than 86,5 / 90,0 / 78,2, and the one-decimal contract is
 * load-bearing (see `formatGradePercent` — a grade rounded before its letter
 * is chosen contradicts the band table it sits next to).
 */
export function formatNumber(value: number, fractionDigits = 1): string {
  if (!Number.isFinite(value)) return ""
  return new Intl.NumberFormat(activeIntlTag(i18n.resolvedLanguage ?? i18n.language), {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(value)
}

/**
 * A percentage: the number above, then the sign. `86.5` → `86,5%` for a
 * German reader, `86.5%` for an English one.
 */
export function formatPercent(value: number, fractionDigits = 1): string {
  if (!Number.isFinite(value)) return ""
  return `${formatNumber(value, fractionDigits)}%`
}
