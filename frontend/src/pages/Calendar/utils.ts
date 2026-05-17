import { formatDateLong } from "@/i18n/format";

export function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

export function formatTime(dateStr: string): string {
  // Time-only display uses the OS locale; the only callsites are the
  // calendar agenda where the row is already grouped by day, so the date
  // separator is implicit. Keep this Intl-direct.
  return new Date(dateStr).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatShortDate(dateStr: string): string {
  // Editorial short form ("May 14" / "14 мая") for the calendar agenda —
  // chronological grouping makes year/locale-canonical ISO redundant
  // here, and natural-language reads better against the day labels.
  return formatDateLong(dateStr, {
    year: undefined,
    month: "short",
    day: "numeric",
  });
}

export function isOverdue(dateStr: string): boolean {
  return new Date(dateStr) < new Date();
}

/**
 * Stable "YYYY-M-D" key used to bucket events by day and to match the
 * currently-selected day. We intentionally don't zero-pad since the
 * same format is used on both sides.
 */
export function calendarDayKey(date: Date): string {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}
