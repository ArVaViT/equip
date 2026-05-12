/**
 * Centralised i18n bootstrap.
 *
 * Locale resolution order:
 *   1. Explicit setting saved in the auth profile (`user.preferred_locale`).
 *      Synchronised by `LocaleSync` once the user logs in.
 *   2. Persisted choice in `localStorage` (cross-session memory for guests).
 *   3. Browser language (`navigator.language`).
 *   4. Hard-coded fallback `ru` — the project was launched in Russian and
 *      every existing course is authored in it.
 *
 * Bundles are imported eagerly: combined size is < 5 KB gzipped, and lazy-
 * loading would force a render flicker on every cold start. We can switch
 * to namespaced lazy bundles when the catalog grows.
 */

import i18n from "i18next"
import { initReactI18next } from "react-i18next"
import LanguageDetector from "i18next-browser-languagedetector"
import en from "./locales/en.json"
import ru from "./locales/ru.json"

export const SUPPORTED_LOCALES = ["ru", "en"] as const
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number]
export const DEFAULT_LOCALE: SupportedLocale = "ru"

export const LOCALE_STORAGE_KEY = "bible-school:locale"

export function isSupportedLocale(value: unknown): value is SupportedLocale {
  return typeof value === "string" && (SUPPORTED_LOCALES as readonly string[]).includes(value)
}

// Vite injects `import.meta.env.MODE` as "development" / "production" / "test"
// (vitest sets MODE="test"). Guard for non-Vite environments just in case.
const mode =
  typeof import.meta !== "undefined" && import.meta.env ? import.meta.env.MODE : "production"
const isProd = mode === "production"
const isTest = mode === "test"

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      ru: { translation: ru },
      en: { translation: en },
    },
    fallbackLng: DEFAULT_LOCALE,
    supportedLngs: SUPPORTED_LOCALES as unknown as string[],
    // Most page text is in <Trans> or t() calls. We do not ship raw HTML
    // strings through translations, so escaping is safe to keep off —
    // react-i18next's render path handles JSX escaping itself.
    interpolation: { escapeValue: false },
    detection: {
      order: ["localStorage", "navigator", "htmlTag"],
      lookupLocalStorage: LOCALE_STORAGE_KEY,
      caches: ["localStorage"],
    },
    returnNull: false,
    // Surface missing keys loudly in non-prod so bilingual drift can't sneak
    // in. In test mode we throw — a test rendering a component with a
    // missing-key lookup will fail immediately, catching the bug in CI. In
    // dev we console.error so the page still renders but the developer sees
    // it. In prod we stay silent (the key string is the fallback, which is
    // ugly but not catastrophic).
    saveMissing: !isProd,
    missingKeyHandler: isProd
      ? undefined
      : (lngs, ns, key) => {
          const locales = Array.isArray(lngs) ? lngs.join(", ") : String(lngs)
          const msg = `[i18n] missing key "${ns}:${key}" for locale(s) ${locales}`
          if (isTest) {
            throw new Error(msg)
          }
          console.error(msg)
        },
  })

// Keep <html lang> in sync with the active locale so screen readers, browser
// translation toolbars, and CSS `:lang(...)` selectors all align.
const updateHtmlLang = (lng: string) => {
  if (typeof document !== "undefined") {
    document.documentElement.lang = lng
  }
}
updateHtmlLang(i18n.language)

// HMR re-evaluates this module on every save, so guard the listener
// registration to avoid stacking duplicate handlers across hot reloads.
declare global {
  interface Window {
    __bibleSchoolLocaleListener?: boolean
  }
}
const globalScope: { __bibleSchoolLocaleListener?: boolean } =
  typeof window !== "undefined" ? window : (globalThis as { __bibleSchoolLocaleListener?: boolean })
if (!globalScope.__bibleSchoolLocaleListener) {
  i18n.on("languageChanged", updateHtmlLang)
  globalScope.__bibleSchoolLocaleListener = true
}

export default i18n
