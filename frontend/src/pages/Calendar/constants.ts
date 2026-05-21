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
    dot: "bg-muted-foreground/50",
    bg: "bg-muted",
    text: "text-muted-foreground",
    border: "border-border",
  },
};

const FALLBACK_EVENT_COLOR: EventColorPalette = {
  dot: "bg-muted-foreground/50",
  bg: "bg-muted",
  text: "text-muted-foreground",
  border: "border-border",
};

export function getEventColor(type: string): EventColorPalette {
  return EVENT_COLORS[type] ?? FALLBACK_EVENT_COLOR;
}

/**
 * Locale-aware month name for the calendar header. Previously this was
 * a hard-coded English array (``"January", "February", ...``) -- a real
 * i18n regression in a Russian-first bilingual app where the calendar
 * grid would read English regardless of the user's language. ``Intl``
 * gets us the localized full name without bundling per-language tables,
 * and BCP-47 ``ru-RU`` / ``en-US`` are the only locales the app
 * supports today.
 */
export function getMonthName(monthIndex: number, locale: string): string {
  const bcp47 = locale.toLowerCase().startsWith("ru") ? "ru-RU" : "en-US";
  // Day 15 avoids any timezone-edge surprise; any day inside the month works.
  const ref = new Date(2000, monthIndex, 15);
  return new Intl.DateTimeFormat(bcp47, { month: "long" }).format(ref);
}

/**
 * Locale-aware short weekday name (``Sun..Sat`` / ``Вс..Сб``). Same
 * reasoning as ``getMonthName`` -- hard-coded English would only
 * render correctly for half the user base.
 *
 * Indices are Sun=0..Sat=6 to match ``Date.prototype.getDay`` so the
 * caller can pass values from the existing day-of-week math directly.
 */
export function getDayShortName(dayIndex: number, locale: string): string {
  const bcp47 = locale.toLowerCase().startsWith("ru") ? "ru-RU" : "en-US";
  // 2000-01-02 was a Sunday in every timezone, so add (dayIndex) days.
  const ref = new Date(2000, 0, 2 + dayIndex);
  return new Intl.DateTimeFormat(bcp47, { weekday: "short" }).format(ref);
}
