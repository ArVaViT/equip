import i18n from "@/i18n/config";
import { formatDateLong } from "@/i18n/format";

export function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

export function formatTime(dateStr: string): string {
  // Locale-aware time display. The previous ``toLocaleTimeString(
  // undefined, ...)`` deferred to the OS locale, so a Russian-UI
  // user on an en-US Windows install saw AM/PM in their agenda
  // while every other timestamp in the app rendered as ru-RU. Wire
  // through the same i18n language the rest of the format helpers
  // already use so the calendar reads as one app.
  const lang = (i18n.resolvedLanguage ?? i18n.language ?? "en").toLowerCase();
  const locale = lang.startsWith("ru") ? "ru-RU" : "en-US";
  return new Date(dateStr).toLocaleTimeString(locale, {
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
