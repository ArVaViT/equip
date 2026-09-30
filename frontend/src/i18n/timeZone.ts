/**
 * The zone this reader sees times in.
 *
 * Every instant the backend stores and serves is UTC. A person reads it in
 * their own zone: the one on their profile, else the one their browser
 * reports, else UTC. A live lesson a teacher sets for 8:00 in Indiana is one
 * instant, shown at 5:00 in California and 14:00 in Berlin.
 *
 * One module-level value, set once the profile loads (`AuthContext`), read by
 * every formatter in `format.ts` and every date picker. Nothing else in the
 * app should decide a zone.
 */

let profileTimeZone: string | null = null

/** The zone the browser runs in, or UTC if it cannot say. */
export function browserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"
  } catch {
    return "UTC"
  }
}

/** Whether `Intl` knows this IANA name ("Europe/Kyiv", "America/Denver"). */
export function isValidTimeZone(tz: string | null | undefined): tz is string {
  if (!tz) return false
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: tz })
    return true
  } catch {
    return false
  }
}

/** Set from the signed-in profile; `null` (signed out, or no zone yet) falls back to the browser. */
export function setDisplayTimeZone(tz: string | null | undefined): void {
  profileTimeZone = isValidTimeZone(tz) ? tz : null
}

export function getDisplayTimeZone(): string {
  return profileTimeZone ?? browserTimeZone()
}

export interface ZonedParts {
  year: number
  month: number
  day: number
  hour: number
  minute: number
  second: number
}

const partsFormatters = new Map<string, Intl.DateTimeFormat>()

function partsFormatter(tz: string): Intl.DateTimeFormat {
  let f = partsFormatters.get(tz)
  if (!f) {
    f = new Intl.DateTimeFormat("en-US", {
      timeZone: tz,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    })
    partsFormatters.set(tz, f)
  }
  return f
}

/** The wall clock an instant shows in `tz`. */
export function zonedParts(date: Date, tz: string = getDisplayTimeZone()): ZonedParts {
  const out: Record<string, number> = {}
  for (const p of partsFormatter(tz).formatToParts(date)) {
    if (p.type !== "literal") out[p.type] = Number(p.value)
  }
  return {
    year: out.year ?? 1970,
    month: out.month ?? 1,
    day: out.day ?? 1,
    // Some engines still print midnight as "24" under h23.
    hour: (out.hour ?? 0) % 24,
    minute: out.minute ?? 0,
    second: out.second ?? 0,
  }
}

/** How far `tz` is ahead of UTC at that instant, in milliseconds. */
function offsetMs(instantMs: number, tz: string): number {
  const p = zonedParts(new Date(instantMs), tz)
  const asUtc = Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second)
  return asUtc - (instantMs - (instantMs % 1000))
}

/**
 * The instant at which `tz`'s clock reads the given wall time.
 *
 * Two passes: guess with the offset at the naive instant, then correct with
 * the offset at the guess. Across a DST change a wall time can be missing
 * (spring: 02:30 does not happen) — it lands an hour later, on the clock
 * that did happen — or doubled (autumn: 01:30 happens twice) — the earlier
 * one is taken.
 */
export function zonedWallTimeToUtc(
  year: number,
  month: number,
  day: number,
  hour = 0,
  minute = 0,
  second = 0,
  tz: string = getDisplayTimeZone(),
): Date {
  const naive = Date.UTC(year, month - 1, day, hour, minute, second)
  const first = naive - offsetMs(naive, tz)
  const second_ = naive - offsetMs(first, tz)
  if (first === second_) return new Date(first)
  // The two passes disagree only at a transition: prefer the earlier
  // instant whose wall clock matches; otherwise the later guess.
  const earlier = Math.min(first, second_)
  const p = zonedParts(new Date(earlier), tz)
  const matches =
    p.year === year && p.month === month && p.day === day && p.hour === hour && p.minute === minute
  return new Date(matches ? earlier : Math.max(first, second_))
}

/** `YYYY-MM-DD` of the calendar day an instant falls on in `tz`. */
export function zonedDayKey(date: Date, tz: string = getDisplayTimeZone()): string {
  const p = zonedParts(date, tz)
  return `${p.year}-${String(p.month).padStart(2, "0")}-${String(p.day).padStart(2, "0")}`
}

/**
 * A short label for the zone, as the reader's language writes it — "EDT",
 * "GMT+3", "MESZ". Shown beside times where the zone matters (live lessons,
 * deadlines, date pickers), so nobody has to wonder whose 8:00 it is.
 */
export function timeZoneLabel(
  locale: string,
  tz: string = getDisplayTimeZone(),
  at: Date = new Date(),
): string {
  try {
    const part = new Intl.DateTimeFormat(locale, { timeZone: tz, timeZoneName: "short" })
      .formatToParts(at)
      .find((p) => p.type === "timeZoneName")
    return part?.value ?? tz
  } catch {
    return tz
  }
}

/** Every IANA zone the engine knows, for the profile's picker (empty on engines without the API). */
export function supportedTimeZones(): string[] {
  const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] }
  try {
    return intl.supportedValuesOf?.("timeZone") ?? []
  } catch {
    return []
  }
}

/**
 * The calendar day an instant falls on in `tz`, as a plain local `Date` at
 * midnight — the container the month grids work in. Grids compare these by
 * year/month/day only, so an event at 23:30 in California lands on that
 * Californian day whatever zone the browser is in.
 */
export function zonedCalendarDate(date: Date, tz: string = getDisplayTimeZone()): Date {
  const p = zonedParts(date, tz)
  return new Date(p.year, p.month - 1, p.day)
}

/** Today, on the reader's calendar. */
export function zonedToday(tz: string = getDisplayTimeZone()): Date {
  return zonedCalendarDate(new Date(), tz)
}
