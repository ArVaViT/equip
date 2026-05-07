/**
 * Locale-aware date / time formatting helpers.
 *
 * The app has historically had three different ways of picking a locale for
 * `toLocaleDateString`:
 *   1. Reading `user.preferred_locale` directly (skips guests entirely).
 *   2. `i18n.language?.startsWith("ru") ? "ru-RU" : "en-US"` ad hoc.
 *   3. `toLocaleDateString()` with no locale — picks up the OS locale, which
 *      is usually right by accident but breaks the "interface in 2 languages"
 *      contract whenever the user's profile and OS disagree.
 *
 * One helper, one source of truth: whatever i18next thinks the active
 * language is. Falls back to English so we never throw on an unsupported
 * locale.
 */
import i18n from "./config"

/**
 * Map i18next's two-letter language code to the regional BCP-47 tag we want
 * `toLocaleDateString` to use. Keep this small — adding a locale to the UI
 * is a deliberate decision, not an automatic one.
 */
function resolveDateLocale(): string {
  const lang = (i18n.resolvedLanguage ?? i18n.language ?? "en").toLowerCase()
  if (lang.startsWith("ru")) return "ru-RU"
  return "en-US"
}

/** Locale-aware `toLocaleDateString`. */
export function formatDate(
  date: Date | string | number | null | undefined,
  options?: Intl.DateTimeFormatOptions,
): string {
  if (date == null) return ""
  const d = date instanceof Date ? date : new Date(date)
  if (Number.isNaN(d.getTime())) return ""
  return d.toLocaleDateString(resolveDateLocale(), options)
}

/** Locale-aware `toLocaleString` for date+time strings. */
export function formatDateTime(
  date: Date | string | number | null | undefined,
  options?: Intl.DateTimeFormatOptions,
): string {
  if (date == null) return ""
  const d = date instanceof Date ? date : new Date(date)
  if (Number.isNaN(d.getTime())) return ""
  return d.toLocaleString(resolveDateLocale(), options)
}
