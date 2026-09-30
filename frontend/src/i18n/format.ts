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
 *      confusion across locales that order day and month differently.
 *   2. The wall-clock time is **the reader's zone**, not UTC and not
 *      the author's. Backend writes are always UTC; here they are
 *      projected into `getDisplayTimeZone()` — the zone on the
 *      person's profile, else the browser's (see `timeZone.ts`). This
 *      module and the date pickers are the only places a zone is
 *      applied.
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
import i18n, { activeIntlTag } from "./config"
import { getDisplayTimeZone, timeZoneLabel, zonedParts, zonedWallTimeToUtc } from "./timeZone"

function pad(value: number, width = 2): string {
  return value.toString().padStart(width, "0")
}

function toDate(value: Date | string | number): Date | null {
  const d = value instanceof Date ? value : new Date(value)
  return Number.isNaN(d.getTime()) ? null : d
}

/** Canonical date: ``YYYY-MM-DD`` in the reader's zone. */
export function formatDate(date: Date | string | number | null | undefined): string {
  if (date == null) return ""
  const d = toDate(date)
  if (!d) return ""
  const p = zonedParts(d)
  return `${p.year}-${pad(p.month)}-${pad(p.day)}`
}

/** Canonical date + time: ``YYYY-MM-DD HH:mm:ss``. */
export function formatDateTime(date: Date | string | number | null | undefined): string {
  if (date == null) return ""
  const d = toDate(date)
  if (!d) return ""
  const p = zonedParts(d)
  return `${p.year}-${pad(p.month)}-${pad(p.day)} ${pad(p.hour)}:${pad(p.minute)}:${pad(p.second)}`
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
  const locale = activeIntlTag(i18n.resolvedLanguage ?? i18n.language)
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
  const locale = activeIntlTag(i18n.resolvedLanguage ?? i18n.language)
  return d.toLocaleString(locale, {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: getDisplayTimeZone(),
    ...options,
  })
}

/**
 * Convert a backend UTC ISO timestamp (or ``null``/``undefined``) into
 * the ``YYYY-MM-DDTHH:mm`` string a ``<input type="datetime-local">``
 * expects.
 *
 * The value is wall-clock time in the **reader's zone** (profile, else
 * browser), so the obvious shortcut — ``iso.slice(0, 16)`` — silently
 * shows the UTC wall-clock as if it were theirs. A user in UTC-7 looking at
 * ``2026-06-01T00:00:00Z`` would see ``2026-06-01 00:00`` in the
 * input, edit it (or just hit save), and have ``new Date(value)``
 * re-encode to ``2026-06-01T07:00:00Z`` — a 7-hour drift on every
 * round-trip.
 *
 * Use together with ``localInputToIso`` on save.
 */
export function isoToLocalInput(iso: string | null | undefined, tz: string = getDisplayTimeZone()): string {
  if (!iso) return ""
  const d = toDate(iso)
  if (!d) return ""
  const p = zonedParts(d, tz)
  return `${p.year}-${pad(p.month)}-${pad(p.day)}T${pad(p.hour)}:${pad(p.minute)}`
}

/**
 * Convert a ``YYYY-MM-DDTHH:mm`` wall-clock value — read in the reader's
 * zone, the same zone ``isoToLocalInput`` wrote it in — into a UTC ISO
 * string the backend can store. A teacher in Indiana typing 08:00 stores
 * 12:00Z (13:00Z in winter), whatever zone their laptop happens to be in. Returns ``null`` for an empty input so the
 * caller can ``PATCH`` a clear without distinguishing missing from
 * empty.
 *
 * Use together with ``isoToLocalInput`` on load.
 */
export function localInputToIso(value: string, tz: string = getDisplayTimeZone()): string | null {
  if (!value) return null
  const m = /^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(?::(\d{2}))?)?$/.exec(value)
  if (!m) {
    // Anything else (a full ISO string with its own offset) already names
    // its instant.
    const d = new Date(value)
    return Number.isNaN(d.getTime()) ? null : d.toISOString()
  }
  const [, y, mo, da, h = "0", mi = "0", se = "0"] = m
  const d = zonedWallTimeToUtc(Number(y), Number(mo), Number(da), Number(h), Number(mi), Number(se), tz)
  return Number.isNaN(d.getTime()) ? null : d.toISOString()
}

/**
 * A moment people plan around — a deadline, a live lesson — as
 * ``YYYY-MM-DD HH:mm`` on the reader's clock, with the zone named:
 * ``2026-10-01 23:59 EDT``. The name is what tells a student in Berlin
 * that the 23:59 is already theirs.
 */
export function formatDateTimeZoned(date: Date | string | number | null | undefined): string {
  if (date == null) return ""
  const d = toDate(date)
  if (!d) return ""
  const p = zonedParts(d)
  const locale = activeIntlTag(i18n.resolvedLanguage ?? i18n.language)
  return `${p.year}-${pad(p.month)}-${pad(p.day)} ${pad(p.hour)}:${pad(p.minute)} ${timeZoneLabel(locale, getDisplayTimeZone(), d)}`
}

/**
 * When the next Daily Challenge day begins, on the reader's clock — the day
 * turns at midnight UTC for everyone, which is 20:00 EDT in Indiana and 03:00
 * in Kyiv. ``"20:00 EDT"``; the zone named because the moment is not local.
 */
export function formatNextUtcMidnight(now: Date = new Date()): string {
  const next = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1))
  const locale = activeIntlTag(i18n.resolvedLanguage ?? i18n.language)
  const tz = getDisplayTimeZone()
  const time = next.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", timeZone: tz })
  return `${time} ${timeZoneLabel(locale, tz, next)}`
}
