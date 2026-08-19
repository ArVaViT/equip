import { activeIntlTag } from "@/i18n/config";

type EventColorPalette = {
  dot: string;
  bg: string;
  text: string;
  border: string;
};

export const EVENT_COLORS: Record<string, EventColorPalette> = {
  deadline: {
    dot: "bg-destructive",
    bg: "bg-destructive/10",
    text: "text-destructive",
    border: "border-destructive/30",
  },
  live_session: {
    dot: "bg-info",
    bg: "bg-info/10",
    text: "text-info",
    border: "border-info/30",
  },
  exam: {
    dot: "bg-warning",
    bg: "bg-warning/10",
    text: "text-warning",
    border: "border-warning/30",
  },
  other: {
    dot: "bg-ink-muted/50",
    bg: "bg-muted",
    text: "text-ink-muted",
    border: "border-edge",
  },
};

const FALLBACK_EVENT_COLOR: EventColorPalette = {
  dot: "bg-ink-muted/50",
  bg: "bg-muted",
  text: "text-ink-muted",
  border: "border-edge",
};

export function getEventColor(type: string): EventColorPalette {
  return EVENT_COLORS[type] ?? FALLBACK_EVENT_COLOR;
}

/**
 * Locale-aware month name for the calendar header. Previously this was
 * a hard-coded English array (``"January", "February", ...``) -- a real
 * i18n regression in a Russian-first bilingual app where the calendar
 * grid would read English regardless of the user's language. ``Intl``
 * gets us the localized full name without bundling per-language tables.
 *
 * The BCP-47 tag comes from ``activeIntlTag``, the app's single map of
 * language to region. This file used to keep its own —
 * ``startsWith("ru") ? "ru-RU" : "en-US"`` — written when there were two
 * languages and left behind when there were four. It did not fail loudly:
 * German and Ukrainian readers simply got an American calendar, "August"
 * and "Sat" over a page that was otherwise entirely theirs.
 */
export function getMonthName(monthIndex: number, locale: string): string {
  // Takes the language as an argument rather than reading the i18n
  // singleton, so the caller passes ``i18n.resolvedLanguage`` once for the
  // whole grid and the function stays pure enough to test directly.
  const bcp47 = activeIntlTag(locale);
  // Day 15 avoids any timezone-edge surprise; any day inside the month works.
  const ref = new Date(2000, monthIndex, 15);
  return new Intl.DateTimeFormat(bcp47, { month: "long" }).format(ref);
}

/**
 * Locale-aware short weekday name (``Sun..Sat`` / ``Вс..Сб`` / ``Sa`` /
 * ``сб``). Same reasoning as ``getMonthName``, and it carried the same
 * two-language map.
 *
 * Indices are Sun=0..Sat=6 to match ``Date.prototype.getDay`` so the
 * caller can pass values from the existing day-of-week math directly.
 */
export function getDayShortName(dayIndex: number, locale: string): string {
  const bcp47 = activeIntlTag(locale);
  // 2000-01-02 was a Sunday in every timezone, so add (dayIndex) days.
  const ref = new Date(2000, 0, 2 + dayIndex);
  return new Intl.DateTimeFormat(bcp47, { weekday: "short" }).format(ref);
}
