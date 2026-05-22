/**
 * Date / time formatting helpers.
 *
 * # The contract (one canonical format for technical timestamps)
 *
 * Every date the user sees as a technical timestamp — table cells,
 * audit logs, last-activity columns, "joined on", "created at",
 * "submitted at" — is rendered in **ISO-8601 form, in the browser's
 * local timezone**:
 *
 *   * `formatDate(d)`        → `YYYY-MM-DD`
 *   * `formatDateTime(d)`    → `YYYY-MM-DD HH:mm:ss`
 *   * `formatDateTimeMs(d)`  → `YYYY-MM-DD HH:mm:ss.SSS`
 *
 * Two consequences are deliberate:
 *
 *   1. The string is **identical across locales**. EN and RU users see
 *      the same characters. Unambiguous, sortable, no day/month
 *      confusion across the en-US / ru-RU split.
 *   2. The wall-clock time is **the browser's local zone**, not UTC.
 *      Backend writes are always UTC; the moment they cross to the
 *      client, JS's ``getFullYear()`` / ``getHours()`` etc. project
 *      them into whatever zone the browser is in. A timezone selector
 *      may ship later; until then, browser zone is the answer.
 *
 * # The escape hatch (for editorial / ceremonial copy only)
 *
 *   * `formatDateLong(d, options?)` — locale-aware long form via
 *      ``Intl.DateTimeFormat``. Use it for things that read as
 *      *prose*: certificate body text, marketing hero copy, the day
 *      header on the calendar. Do NOT use it for table cells or audit
 *      logs — visual consistency across locales matters more than
 *      "Mon, May 14" reading naturally for an English user.
 *
 * If you find yourself reaching for `formatDateLong` outside an
 * editorial context, you probably want `formatDate` instead.
 */
import i18n from "./config"

function pad(value: number, width = 2): string {
  return value.toString().padStart(width, "0")
}

function toDate(value: Date | string | number): Date | null {
  const d = value instanceof Date ? value : new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

/** Canonical date: ``YYYY-MM-DD`` in the browser's local timezone. */
export function formatDate(date: Date | string | number | null | undefined): string {
  if (date == null) return ""
  const d = toDate(date)
  if (!d) return ""
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** Canonical date + time: ``YYYY-MM-DD HH:mm:ss``. */
export function formatDateTime(date: Date | string | number | null | undefined): string {
  if (date == null) return ""
  const d = toDate(date)
  if (!d) return ""
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  )
}

/**
 * Canonical date + time with millisecond precision:
 * ``YYYY-MM-DD HH:mm:ss.SSS``. Reach for this only when sub-second
 * resolution actually matters (audit forensics, latency dashboards);
 * for normal UI ``formatDateTime`` reads cleaner.
 */
export function formatDateTimeMs(date: Date | string | number | null | undefined): string {
  if (date == null) return ""
  const d = toDate(date)
  if (!d) return ""
  return `${formatDateTime(d)}.${pad(d.getMilliseconds(), 3)}`
}

/**
 * Locale-aware relative time ("5m ago", "5 мин назад") for compact
 * table cells where an absolute timestamp would dominate the row.
 *
 * Pair with ``title={formatDateTime(date)}`` on the rendering element
 * so a hover (or screen reader) still surfaces the exact moment —
 * relative ts is scannable but loses precision once you cross a day
 * boundary, and an admin reading the audit log needs the exact value.
 *
 * Granularity rolls up: under a minute → "just now", under an hour →
 * "Xm ago", under a day → "Xh ago", under a month → "Xd ago", else
 * the absolute date so "3 months ago" doesn't muddy a real timeline.
 */
export function formatRelative(date: Date | string | number | null | undefined): string {
  if (date == null) return ""
  const d = toDate(date)
  if (!d) return ""
  const lang = (i18n.resolvedLanguage ?? i18n.language ?? "en").toLowerCase()
  const locale = lang.startsWith("ru") ? "ru-RU" : "en-US"
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto", style: "short" })
  const diffMs = d.getTime() - Date.now()
  const absSec = Math.abs(diffMs) / 1000

  if (absSec < 45) return rtf.format(0, "second").replace("0", "")
  if (absSec < 3600) return rtf.format(Math.round(diffMs / 60_000), "minute")
  if (absSec < 86_400) return rtf.format(Math.round(diffMs / 3_600_000), "hour")
  if (absSec < 30 * 86_400) return rtf.format(Math.round(diffMs / 86_400_000), "day")
  // For anything older, the absolute date reads more honestly than
  // ``3 months ago`` (and is sortable, which is the rest of the
  // module's promise).
  return formatDate(d)
}

/**
 * Locale-aware long form (``Intl.DateTimeFormat``). EN and RU render
 * different strings on purpose — this is the editorial / ceremonial
 * format. Use it for prose: certificate body, calendar day header,
 * "joined on…" lines, time-stamped deadlines where natural language
 * is warranted.
 *
 * Defaults to ``{ year: "numeric", month: "long", day: "numeric" }``
 * which yields ``May 14, 2026`` / ``14 мая 2026 г.``. Supply hour /
 * minute / weekday options to extend — backed by ``toLocaleString``
 * so the same call handles date-only and date+time outputs.
 */
export function formatDateLong(
  date: Date | string | number | null | undefined,
  options?: Intl.DateTimeFormatOptions,
): string {
  if (date == null) return ""
  const d = toDate(date)
  if (!d) return ""
  const lang = (i18n.resolvedLanguage ?? i18n.language ?? "en").toLowerCase()
  const locale = lang.startsWith("ru") ? "ru-RU" : "en-US"
  return d.toLocaleString(locale, {
    year: "numeric",
    month: "long",
    day: "numeric",
    ...options,
  })
}

/**
 * Convert a backend UTC ISO timestamp (or ``null``/``undefined``) into
 * the ``YYYY-MM-DDTHH:mm`` string a ``<input type="datetime-local">``
 * expects.
 *
 * The browser interprets that input value in the **local** timezone,
 * so the obvious shortcut — ``iso.slice(0, 16)`` — silently shows the
 * UTC wall-clock as if it were local. A user in UTC-7 looking at
 * ``2026-06-01T00:00:00Z`` would see ``2026-06-01 00:00`` in the
 * input, edit it (or just hit save), and have ``new Date(value)``
 * re-encode to ``2026-06-01T07:00:00Z`` — a 7-hour drift on every
 * round-trip.
 *
 * Use together with ``localInputToIso`` on save.
 */
export function isoToLocalInput(iso: string | null | undefined): string {
  if (!iso) return ""
  const d = toDate(iso)
  if (!d) return ""
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  )
}

/**
 * Convert the value from a ``<input type="datetime-local">`` (which
 * the browser interprets in the local timezone) into a UTC ISO string
 * the backend can store. Returns ``null`` for an empty input so the
 * caller can ``PATCH`` a clear without distinguishing missing from
 * empty.
 *
 * Use together with ``isoToLocalInput`` on load.
 */
export function localInputToIso(value: string): string | null {
  if (!value) return null
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return null
  return d.toISOString()
}
