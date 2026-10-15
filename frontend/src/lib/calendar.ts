/**
 * Shared date math for the hand-rolled Mon-start month grid used by the
 * two calendar pickers (`DateTimePicker`, `DateRangePicker`).
 * These were copy-pasted byte-for-byte across all three before extraction.
 *
 * NOTE: this is the date-INPUT grid (Mon-start, 6 rows, no event bucketing).
 * The event calendar (`pages/Calendar/`) builds its own rows, but starts
 * the week on Monday too (2026-10-03): it used to start on Sunday, beside
 * pickers that start on Monday, for readers whose week starts on Monday.
 */

const DAYS_IN_WEEK = 7

/** Local `YYYY-MM-DD` key (no timezone shift — uses the date's own Y/M/D). */
export function ymdKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
}

/** Parse a strict `YYYY-MM-DD` string to a local Date, or `null`. */
export function parseYmd(s: string): Date | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null
  const y = Number(s.slice(0, 4))
  const m = Number(s.slice(5, 7))
  const d = Number(s.slice(8, 10))
  const out = new Date(y, m - 1, d)
  return Number.isNaN(out.getTime()) ? null : out
}

/** Day of week with Monday = 0 … Sunday = 6. */
export function weekdayMonStart(d: Date): number {
  return (d.getDay() + 6) % DAYS_IN_WEEK
}

export function startOfMonth(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), 1)
}

export function addMonths(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth() + n, 1)
}

/**
 * The 42 dates (6 weeks) of the Mon-start grid containing `anchor`'s month,
 * including the leading/trailing days from adjacent months. Selection state
 * is left to the caller — the grid itself is selection-agnostic.
 */
export function buildMonthMatrix(anchor: Date): Date[] {
  const year = anchor.getFullYear()
  const month = anchor.getMonth()
  const offset = weekdayMonStart(new Date(year, month, 1))
  const gridStart = new Date(year, month, 1 - offset)
  return Array.from(
    { length: 42 },
    (_, i) => new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i),
  )
}

/** Monday of the week `d` falls in, at local midnight. */
export function startOfWeekMon(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() - weekdayMonStart(d))
}

/** `n` days after `d`, at local midnight — calendar days, not 24-hour steps. */
export function addDays(d: Date, n: number): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n)
}
