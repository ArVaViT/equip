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
 * Catalogs are loaded lazily, one locale per visitor (~20 KB gzip each):
 * a tiny backend plugin resolves each language through a per-locale
 * dynamic import, so only the active catalog rides the critical path.
 * `main.tsx` awaits `i18nReady` before the first React render, which
 * keeps the original no-flicker guarantee — the first paint already has
 * its translations. `i18n.changeLanguage()` awaits the backend too, so
 * a language switch never renders missing keys.
 */

import i18n, { type BackendModule, type ReadCallback } from "i18next"
import { initReactI18next } from "react-i18next"
import LanguageDetector from "i18next-browser-languagedetector"

export const SUPPORTED_LOCALES = ["ru", "en", "de", "uk"] as const
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number]
export const DEFAULT_LOCALE: SupportedLocale = "ru"

const LOCALE_STORAGE_KEY = "equip:locale"
const LEGACY_LOCALE_STORAGE_KEY = "bible-school:locale"

// One-time migration: existing users still have their locale under the old
// pre-rebrand key. Carry the value over so a returning user keeps their
// language preference instead of silently snapping back to the RU default.
if (typeof window !== "undefined") {
  try {
    const legacy = window.localStorage.getItem(LEGACY_LOCALE_STORAGE_KEY)
    if (legacy && !window.localStorage.getItem(LOCALE_STORAGE_KEY)) {
      window.localStorage.setItem(LOCALE_STORAGE_KEY, legacy)
    }
    if (legacy !== null) {
      window.localStorage.removeItem(LEGACY_LOCALE_STORAGE_KEY)
    }
  } catch {
    // localStorage may throw (private mode, quota, disabled) — degrade silently
  }
}

/**
 * Each language named in itself.
 *
 * A person hunting for their own language scans for the word they know — not
 * for its translation into whichever language the interface is currently
 * stuck in. Kept here rather than in a component because both the switcher
 * and the first-run setup screen offer the same list.
 */
export const LOCALE_NATIVE_LABELS: Record<SupportedLocale, string> = {
  ru: "Русский",
  en: "English",
  de: "Deutsch",
  uk: "Українська",
}

/**
 * BCP-47 tag per locale, for `Intl` — date and number formatting.
 *
 * `Intl` wants a region to pick a format: bare "de" works, but the tags
 * here are the ones the audience actually reads in. Before this existed
 * the code asked `lang.startsWith("ru") ? "ru-RU" : "en-US"`, so German
 * and Ukrainian readers were shown American dates — "August 15, 2026"
 * where they expect "15. August 2026" and "15 серпня 2026".
 */
export const LOCALE_INTL_TAGS: Record<SupportedLocale, string> = {
  ru: "ru-RU",
  en: "en-US",
  de: "de-DE",
  uk: "uk-UA",
}

/** The Intl tag for whatever language is active right now. */
export function activeIntlTag(language?: string): string {
  const lang = (language ?? "").toLowerCase().split("-")[0]
  return isSupportedLocale(lang) ? LOCALE_INTL_TAGS[lang] : LOCALE_INTL_TAGS[DEFAULT_LOCALE]
}

export function isSupportedLocale(value: unknown): value is SupportedLocale {
  return typeof value === "string" && (SUPPORTED_LOCALES as readonly string[]).includes(value)
}

// Per-locale dynamic imports — each catalog becomes its own lazy chunk so
// the eager i18n chunk carries only the i18next runtime, not both JSONs.
const LOCALE_LOADERS: Record<SupportedLocale, () => Promise<{ default: object }>> = {
  ru: () => import("./locales/ru.json"),
  en: () => import("./locales/en.json"),
  de: () => import("./locales/de.json"),
  uk: () => import("./locales/uk.json"),
}

/**
 * Minimal i18next backend that resolves catalogs through the dynamic
 * imports above. Going through the backend API (instead of manual
 * `addResourceBundle` calls) means i18next itself awaits the catalog
 * inside `init()` and `changeLanguage()` — callers that `await` those
 * never observe a missing-key render.
 */
const lazyLocaleBackend: BackendModule = {
  type: "backend",
  init() {
    /* no-op — loaders are statically known */
  },
  read(language: string, _namespace: string, callback: ReadCallback) {
    if (!isSupportedLocale(language)) {
      // `supportedLngs` should make this unreachable; respond with an
      // empty catalog rather than an error so a weird detector value
      // can't wedge initialisation.
      callback(null, {})
      return
    }
    LOCALE_LOADERS[language]().then(
      (mod) => callback(null, mod.default as Parameters<ReadCallback>[1]),
      (err) => callback(err as Error, null),
    )
  },
}

// Vite injects `import.meta.env.MODE` as "development" / "production" / "test"
// (vitest sets MODE="test"). Guard for non-Vite environments just in case.
const mode =
  typeof import.meta !== "undefined" && import.meta.env ? import.meta.env.MODE : "production"
const isProd = mode === "production"
const isTest = mode === "test"

/**
 * Resolves once the detected locale's catalog (plus the `ru` fallback when
 * they differ) is registered. `main.tsx` gates the first render on this;
 * the vitest setup awaits it (plus `loadLanguages`) so tests keep their
 * synchronous-resources assumption.
 */
export const i18nReady: Promise<unknown> = i18n
  .use(lazyLocaleBackend)
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
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
// translation toolbars, and CSS `:lang(...)` selectors all align. With the
// async backend, `i18n.language` is only settled once init resolves — the
// `languageChanged` event i18next emits at that point (and on every
// subsequent switch) drives the update.
const updateHtmlLang = (lng: string) => {
  if (typeof document !== "undefined" && lng) {
    document.documentElement.lang = lng
  }
}

// HMR re-evaluates this module on every save, so guard the listener
// registration to avoid stacking duplicate handlers across hot reloads.
declare global {
  interface Window {
    __equipLocaleListener?: boolean
  }
}
const globalScope: { __equipLocaleListener?: boolean } =
  typeof window !== "undefined" ? window : (globalThis as { __equipLocaleListener?: boolean })
if (!globalScope.__equipLocaleListener) {
  i18n.on("languageChanged", updateHtmlLang)
  globalScope.__equipLocaleListener = true
}

export default i18n
